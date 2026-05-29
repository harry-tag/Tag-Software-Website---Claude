#!/usr/bin/env python3
"""
Fetch job listings from the Workable board and update careers.html.

Run locally:   python scripts/update_jobs.py
Also runs via: .github/workflows/update-jobs.yml  (weekly, Monday 6 am UTC)

To update LinkedIn TAG roles when job IDs change, edit LINKEDIN_TAG_ROLES below.
To add/remove portfolio companies from the page, edit FEATURED_PORTCOS below.
"""

import json
import re
import urllib.request
from html import escape
from datetime import datetime, timezone

# ── Configuration ──────────────────────────────────────────────────────────────

WORKABLE_BOARD_URL = (
    "https://jobs.workable.com/company/"
    "i7bvgtD9zMBw8pksaJ6inV/jobs-at-valsoft-corporation"
)
CAREERS_HTML_PATH = "careers.html"

# Workable department names that get the TAG badge
TAG_COMPANIES = {
    "TAG Software Group",
    "TAG Software",
}

# Workable department names to feature as Portfolio roles.
# Add/remove companies here to control what appears on the page.
FEATURED_PORTCOS = {
    "Quorum",
    "OASES Commsoft",
    "ScholarChip",
    "ScholarChip Corporation",
    "MPS Monitor",
    "MPS Monitor - NEXERA",
    "NEXERA",
    "Unionware",
    "BluSynq",
}

# LinkedIn-sourced TAG roles — update when LinkedIn job IDs change.
# These are merged with any TAG roles found on Workable (no duplicates).
LINKEDIN_TAG_ROLES = [
    {
        "title": "M&A Internship — Fall Semester",
        "company": "TAG Software Group",
        "location": "Toronto, ON",
        "url": "https://www.linkedin.com/jobs/view/4416980815/",
    },
    {
        "title": "Managing Director (NAM)",
        "company": "TAG Software Group",
        "location": "Canada",
        "url": "https://www.linkedin.com/jobs/view/4409440814/",
    },
    {
        "title": "AI Customer Success Manager",
        "company": "TAG Software Group",
        "location": "Montreal, QC",
        "url": "https://www.linkedin.com/jobs/view/4419555312/",
    },
    {
        "title": "M&A Business Development Analyst",
        "company": "TAG Software Group",
        "location": "Brazil",
        "url": "https://www.linkedin.com/jobs/view/4369927863/",
    },
]


# ── Fetch ──────────────────────────────────────────────────────────────────────

def fetch_workable_jobs():
    """Fetch the Workable board page and extract the embedded jobs JSON."""
    req = urllib.request.Request(
        WORKABLE_BOARD_URL,
        headers={"User-Agent": "Mozilla/5.0 (compatible; TAG-Jobs-Bot/1.0)"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        html = resp.read().decode("utf-8")

    # The page embeds jobs as: "jobs":[{...},{...}]
    # Use a bracket-balanced extractor so HTML in description strings doesn't break it.
    idx = html.find('"jobs":[')
    if idx == -1:
        raise RuntimeError("Could not find jobs array in Workable page HTML")

    start = html.index("[", idx)
    depth, in_string, escape_next = 0, False, False
    end = start

    for i, ch in enumerate(html[start:], start):
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if not in_string:
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break

    return json.loads(html[start:end])


# ── Classify ───────────────────────────────────────────────────────────────────

def classify(job):
    dept = job.get("department", "")
    if dept in TAG_COMPANIES:
        return "tag"
    if dept in FEATURED_PORTCOS:
        return "portco"
    return None


def first_location(job):
    locs = job.get("locations", [])
    return locs[0] if locs else ""


# ── HTML generation ────────────────────────────────────────────────────────────

def role_row(title, company_display, location, url, role_type):
    badge = (
        '<span class="role-badge role-badge--tag">TAG</span>'
        if role_type == "tag"
        else '<span class="role-badge role-badge--portco">Portfolio</span>'
    )
    return (
        f'      <div class="role-item" data-type="{role_type}">\n'
        f'        <div class="role-main">\n'
        f'          <div class="role-title">{escape(title)}</div>\n'
        f'          <div class="role-co">{escape(company_display)}</div>\n'
        f'        </div>\n'
        f'        <div class="role-meta">\n'
        f'          <span class="role-loc">{escape(location)}</span>\n'
        f'          {badge}\n'
        f'          <a href="{url}" target="_blank" rel="noopener" class="role-apply">Apply →</a>\n'
        f'        </div>\n'
        f'      </div>'
    )


# ── Update careers.html ────────────────────────────────────────────────────────

def update_careers_html(roles_html):
    with open(CAREERS_HTML_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    updated, n = re.subn(
        r"(<!-- JOBS-START -->).*?(<!-- JOBS-END -->)",
        f"\\1\n\n{roles_html}\n\n",
        content,
        count=1,
        flags=re.DOTALL,
    )

    if n == 0:
        raise RuntimeError(
            "JOBS-START / JOBS-END markers not found in careers.html. "
            "The markers may have been removed."
        )

    with open(CAREERS_HTML_PATH, "w", encoding="utf-8") as f:
        f.write(updated)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print(f"[{datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}] Fetching Workable board...")
    all_jobs = fetch_workable_jobs()
    print(f"  Total jobs on board: {len(all_jobs)}")

    workable_tag_rows = []
    portco_rows = []
    seen_titles = set()

    for job in all_jobs:
        if job.get("state") != "published":
            continue
        jtype = classify(job)
        if not jtype:
            continue

        title = job["title"]
        dept = job.get("department", "")
        loc = first_location(job)
        url = job.get("url", "#")

        if jtype == "tag":
            workable_tag_rows.append(
                role_row(title, "TAG Software Group", loc, url, "tag")
            )
            seen_titles.add(title.lower())
        else:
            portco_rows.append(
                role_row(title, f"{dept} · {loc}", loc, url, "portco")
            )

    # Prepend LinkedIn TAG roles, skipping any already found on Workable
    linkedin_rows = [
        role_row(r["title"], r["company"], r["location"], r["url"], "tag")
        for r in LINKEDIN_TAG_ROLES
        if r["title"].lower() not in seen_titles
    ]
    tag_rows = linkedin_rows + workable_tag_rows

    print(f"  TAG roles: {len(tag_rows)}  |  Portfolio roles: {len(portco_rows)}")

    lines = (
        ["      <!-- TAG roles -->"]
        + tag_rows
        + ["", "      <!-- Portfolio roles -->"]
        + portco_rows
    )

    update_careers_html("\n".join(lines))
    print("  careers.html updated.")


if __name__ == "__main__":
    main()

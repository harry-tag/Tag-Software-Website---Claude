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
import urllib.parse
import urllib.request
from html import escape
from datetime import datetime, timezone

# ── Configuration ──────────────────────────────────────────────────────────────

WORKABLE_COMPANY_ID = "i7bvgtD9zMBw8pksaJ6inV"
WORKABLE_BOARD_URL = (
    "https://jobs.workable.com/company/"
    f"{WORKABLE_COMPANY_ID}/jobs-at-valsoft-corporation"
)
CAREERS_HTML_PATH = "careers.html"

# Workable department names that get the TAG badge
TAG_COMPANIES = {
    "TAG Software Group",
    "TAG Software",
    "Tag Software Group",  # alternate capitalisation seen on Workable
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
    "UnionWare",          # alternate capitalisation seen on Workable
    "BluSynq",
    "Celtrino",
    "Forms Express",
    "Freicon Software",   # Filaks Plus on Workable
    "INPLAN",
    "VHL Sistemas",
    "Viova",
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
    """Fetch all jobs from the Workable company API, paginating until complete."""
    base_url = f"https://jobs.workable.com/api/v1/companies/{WORKABLE_COMPANY_ID}"
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; TAG-Jobs-Bot/1.0)",
        "Accept": "application/json",
        "Referer": WORKABLE_BOARD_URL,
    }
    all_jobs, page_token = [], None
    while True:
        url = base_url + (f"?pageToken={urllib.parse.quote(page_token)}" if page_token else "")
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        jobs = data.get("jobs", [])
        all_jobs.extend(jobs)
        page_token = data.get("nextPageToken")
        if not page_token or not jobs:
            break
    return all_jobs


# ── Classify & normalise ───────────────────────────────────────────────────────

def exp_level(title):
    t = title.lower()
    if any(k in t for k in ("intern", "internship", "co-op", "coop", "practicum", "student")):
        return "intern"
    if any(k in t for k in ("managing director", "vice president", " vp", "vp ", "chief", "svp", "evp", "head of", "c.t.o", "cto", "cfo", "coo", "ceo")):
        return "senior"
    if any(k in t for k in ("director", "senior", "sr.", "sr ", "principal", "lead ")):
        return "senior"
    if any(k in t for k in ("manager", "controller", "specialist", "consultant", "supervisor", "advisor")):
        return "mid"
    return "entry"


def geo_key(location):
    loc = location.lower()
    if any(k in loc for k in ("telecommute", "remote", "télétravail", "work from home")):
        return "remote"
    if any(k in loc for k in ("canada", "toronto", "montreal", "montréal", "vancouver", "calgary", "ottawa", "winnipeg", ", on", ", qc", ", bc", ", ab", ", ns", ", nb", ", sk", "nova scotia", "st. john", "st john", "saskatoon", "new brunswick", "fredericton", "halifax", "moncton", "regina", "edmonton", "quebec", "ontario", "british columbia", "alberta", "manitoba", "saskatchewan")):
        return "canada"
    if any(k in loc for k in ("brazil", "brasil", "são paulo", "sao paulo", "rio de janeiro")):
        return "brazil"
    if any(k in loc for k in ("usa", "united states", ", ny", ", ca", ", tx", ", fl", ", il", ", wa", ", mi", ", oh", ", ga")):
        return "usa"
    if any(k in loc for k in ("uk", "united kingdom", "england", "london", "manchester", "birmingham", "scotland", "wales")):
        return "uk"
    if any(k in loc for k in ("germany", "deutschland", "berlin", "munich", "münchen", "hamburg")):
        return "germany"
    return re.sub(r"[^a-z0-9]+", "-", loc.split(",")[0].strip()).strip("-") or "other"


def co_key(dept):
    d = re.sub(r"\s*·.*$", "", dept).strip().lower()
    if "tag software" in d:
        return "tag"
    return re.sub(r"[^a-z0-9]+", "-", d).strip("-")


def classify(job):
    dept = job.get("department", "")
    if dept in TAG_COMPANIES:
        return "tag"
    if dept in FEATURED_PORTCOS:
        return "portco"
    return None


def first_location(job):
    """Return the most useful location string for a job.
    Prefers a non-TELECOMMUTE entry; falls back to countryName from the location object."""
    locs = job.get("locations", [])
    non_remote = [l for l in locs if l.upper() != "TELECOMMUTE"]
    if non_remote:
        return non_remote[0]
    loc_obj = job.get("location", {})
    if loc_obj.get("countryName"):
        return loc_obj["countryName"]
    return locs[0] if locs else ""


def city_from_workable_url(url):
    """Extract a readable city name from the Workable job URL slug."""
    m = re.search(r"-in-(.+?)-at-valsoft", url, re.IGNORECASE)
    if not m:
        return None
    slug = m.group(1)

    def cap(word):
        if "'" in word:
            a, _, b = word.partition("'")
            return a.capitalize() + "'" + b
        return word.capitalize()

    return " ".join(cap(p) for p in slug.split("-") if p)


# ── HTML generation ────────────────────────────────────────────────────────────

def role_row(title, company_display, location, url, role_type, dept=None, display_location=None, all_locations=None):
    exp = exp_level(title)
    geo = geo_key(location)
    co  = co_key(dept if dept is not None else company_display)
    loc_text = display_location if display_location is not None else location
    locs_attr = f' data-locs="{escape(loc_text)}"' if all_locations and len(all_locations) > 1 else ""
    badge = (
        '<span class="role-badge role-badge--tag">TAG</span>'
        if role_type == "tag"
        else '<span class="role-badge role-badge--portco">Portfolio</span>'
    )
    return (
        f'      <div class="role-item" data-type="{role_type}" data-exp="{exp}" data-geo="{geo}" data-co="{co}">\n'
        f'        <div class="role-main">\n'
        f'          <div class="role-title">{escape(title)}</div>\n'
        f'          <div class="role-co">{escape(company_display)}</div>\n'
        f'        </div>\n'
        f'        <div class="role-meta">\n'
        f'          <span class="role-loc"{locs_attr}>{escape(loc_text)}</span>\n'
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
        f"\\1\n\n{roles_html}\n\n\\2",
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
            portco_rows.append((title, dept, loc, url))

    # Deduplicate portco jobs: group same (title, dept) into one listing with all cities
    from collections import defaultdict
    portco_groups = defaultdict(list)
    for title, dept, loc, url in portco_rows:
        portco_groups[(title, dept)].append((loc, url))

    deduped_portco_rows = []
    for (title, dept), entries in portco_groups.items():
        first_loc, first_url = entries[0]
        # Prefer city names extracted from URL slugs; fall back to raw location strings
        cities = list(dict.fromkeys(
            city_from_workable_url(url) or loc
            for loc, url in entries
        ))
        loc_display = " · ".join(cities)
        # Use the first extracted city name (not "TELECOMMUTE") so geo_key classifies correctly
        geo_loc = cities[0] if cities else first_loc
        deduped_portco_rows.append(
            role_row(title, dept, geo_loc, first_url, "portco",
                     dept=dept, display_location=loc_display, all_locations=cities)
        )
    portco_rows = deduped_portco_rows

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

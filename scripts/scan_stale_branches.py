#!/usr/bin/env python3
"""
Enterprise GitHub Stale Branch Scanner
Read-only | Audit-safe | Calendar-month based
"""

import argparse
import csv
import datetime
import os
import requests
from zoneinfo import ZoneInfo

PROTECTED_BRANCHES = {"main", "master", "develop", "prod"}
RELEASE_PREFIX = "release/"
ET = ZoneInfo("America/New_York")
UTC = datetime.timezone.utc

def github_get(url, headers):
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--org", required=True)
    p.add_argument("--itaps", required=True)
    p.add_argument("--months", type=int, required=True)
    p.add_argument("--out", required=True)
    return p.parse_args()

def main():
    args = parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN not set")

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json"
    }

    itaps = [i.strip() for i in args.itaps.split(",")]
    now_et = datetime.datetime.now(ET)

    cutoff_month = now_et.month - args.months
    cutoff_year = now_et.year
    while cutoff_month <= 0:
        cutoff_month += 12
        cutoff_year -= 1
    cutoff = datetime.datetime(cutoff_year, cutoff_month, 1, tzinfo=ET)

    repos, page = [], 1
    while True:
        data = github_get(
            f"https://api.github.com/orgs/{args.org}/repos?per_page=100&page={page}",
            headers
        )
        if not data:
            break
        repos.extend(data)
        page += 1

    stale = []

    for repo in repos:
        if not any(i in repo["name"] for i in itaps):
            continue

        branches = github_get(repo["branches_url"].replace("{/branch}", ""), headers)

        for br in branches:
            name = br["name"]

            if br.get("protected"):
                continue
            if name in PROTECTED_BRANCHES or name.startswith(RELEASE_PREFIX):
                continue

            commit = github_get(br["commit"]["url"], headers)["commit"]
            commit_utc = datetime.datetime.strptime(
                commit["author"]["date"], "%Y-%m-%dT%H:%M:%SZ"
            ).replace(tzinfo=UTC)
            commit_et = commit_utc.astimezone(ET)

            if commit_et <= cutoff:
                age = (now_et.year - commit_et.year) * 12 + (now_et.month - commit_et.month)
                stale.append([
                    repo["name"],
                    name,
                    commit_et.strftime("%Y-%m-%d %I:%M %p %Z"),
                    age,
                    commit["author"]["name"] or "unknown",
                    commit["author"]["email"] or "unknown"
                ])

    if not stale:
        return

    os.makedirs(args.out, exist_ok=True)

    # CSV
    with open(f"{args.out}/stale_report.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Repo", "Branch", "Last Commit", "Age (Months)", "Author", "Email"])
        w.writerows(stale)

    scan_time = now_et.strftime("%a %b %d %H:%M:%S %Z %Y")

    # TXT
    with open(f"{args.out}/stale_report.txt", "w") as f:
        f.write(
            f"Stale GitHub Branch Report\n"
            f"Organization: {args.org}\n\n"
            f"Scan Date: {scan_time}\n\n"
            f"Branches inactive for ≥ {args.months} calendar months (US Eastern Time).\n\n"
        )
        for s in stale:
            f.write(
                f"Repo: {s[0]}\n"
                f"Branch: {s[1]}\n"
                f"Last Commit: {s[2]}\n"
                f"Age (Months): {s[3]}\n"
                f"Author: {s[4]}\n"
                f"Email: {s[5]}\n"
                + "-" * 60 + "\n"
            )

    # HTML Email
    with open(f"{args.out}/email.html", "w") as f:
        f.write(f"""
<h2>Stale GitHub Branch Report</h2>

<p><b>Organization:</b> {args.org}</p>
<p><b>Scan Date:</b> {scan_time}</p>
<p>Branches inactive for <b>≥ {args.months} calendar months</b> (US Eastern Time).</p>

<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;">
<tr style="background:#f2f2f2;">
  <th>Repo</th>
  <th>Branch</th>
  <th>Last Commit</th>
  <th>Age (Months)</th>
  <th>Author</th>
  <th>Email</th>
</tr>
""")
        for s in stale:
            f.write(f"""
<tr>
  <td>{s[0]}</td>
  <td>{s[1]}</td>
  <td>{s[2]}</td>
  <td align="center">{s[3]}</td>
  <td>{s[4]}</td>
  <td>{s[5]}</td>
</tr>
""")
        f.write("""
</table>

<br/>
<b>Notes:</b>
<ul>
  <li>Protected branches (main, master, develop, release/*, prod) are excluded</li>
  <li>No branches were deleted by this job</li>
  <li>Deletion requires explicit approval via cleanup pipeline</li>
</ul>
""")

if __name__ == "__main__":
    main()

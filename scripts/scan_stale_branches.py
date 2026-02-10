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
GITHUB_API = "https://api.github.com"

BASE_HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "enterprise-github-audit"
}

def github_get(url, headers, params=None):
    r = requests.get(url, headers=headers, params=params, timeout=30)
    r.raise_for_status()
    return r.json()

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--org", required=True)
    p.add_argument("--itaps", required=True)
    p.add_argument("--months", type=int, required=True)
    p.add_argument("--out", required=True)
    return p.parse_args()

def calculate_cutoff(now_et, months):
    month = now_et.month - months
    year = now_et.year
    while month <= 0:
        month += 12
        year -= 1
    return datetime.datetime(year, month, 1, tzinfo=ET)

def main():
    args = parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN not set")

    headers = {**BASE_HEADERS, "Authorization": f"token {token}"}

    itaps = [i.strip() for i in args.itaps.split(",")]
    now_et = datetime.datetime.now(ET)
    cutoff = calculate_cutoff(now_et, args.months)

    repos = []
    page = 1
    while True:
        data = github_get(
            f"{GITHUB_API}/orgs/{args.org}/repos",
            headers,
            {"per_page": 100, "page": page}
        )
        if not data:
            break
        repos.extend(data)
        page += 1

    stale = []

    for repo in repos:
        if not any(itap in repo["name"] for itap in itaps):
            continue

        branch_page = 1
        while True:
            branches = github_get(
                f"{GITHUB_API}/repos/{args.org}/{repo['name']}/branches",
                headers,
                {"per_page": 100, "page": branch_page}
            )
            if not branches:
                break

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
                    age = (
                        (now_et.year - commit_et.year) * 12 +
                        (now_et.month - commit_et.month)
                    )
                    stale.append([
                        repo["name"],
                        name,
                        commit_et.strftime("%Y-%m-%d %I:%M %p %Z"),
                        age,
                        commit["author"]["name"] or "unknown",
                        commit["author"]["email"] or "unknown"
                    ])

            branch_page += 1

    if not stale:
        return

    os.makedirs(args.out, exist_ok=True)

    with open(f"{args.out}/stale_report.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Repo", "Branch", "Last Commit", "Age (Months)", "Author", "Email"])
        writer.writerows(stale)

    scan_time = now_et.strftime("%a %b %d %H:%M:%S %Z %Y")

    with open(f"{args.out}/email.html", "w") as f:
        f.write(f"""
<h2>Stale GitHub Branch Audit Report</h2>
<p><b>Organization:</b> {args.org}</p>
<p><b>Scan Date:</b> {scan_time}</p>
<p>Branches inactive for <b>≥ {args.months} calendar months</b>.</p>

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
        for r in stale:
            f.write(f"""
<tr>
  <td>{r[0]}</td>
  <td>{r[1]}</td>
  <td>{r[2]}</td>
  <td align="center">{r[3]}</td>
  <td>{r[4]}</td>
  <td>{r[5]}</td>
</tr>
""")
        f.write("""
</table>

<br/>
<b>Compliance Notes:</b>
<ul>
  <li>Protected branches are excluded</li>
  <li>No branches were modified or deleted</li>
  <li>Deletion requires a separate, approval-gated pipeline</li>
</ul>
""")

if __name__ == "__main__":
    main()

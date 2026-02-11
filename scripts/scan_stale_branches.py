#!/usr/bin/env python3
"""
Enterprise GitHub Stale Branch Scanner
PRODUCTION VERSION

Features:
- Read-only audit safe
- Calendar-month based aging
- Case-insensitive ITAP matching
- GitHub rate limit awareness
- API retry with exponential backoff
- Defensive null handling
- Sorted output
"""

import argparse
import csv
import datetime
import os
import sys
import time
import requests
from zoneinfo import ZoneInfo

# ==============================
# CONFIGURATION
# ==============================

PROTECTED_BRANCHES = {"main", "master", "develop", "prod"}
RELEASE_PREFIX = "release/"
ET = ZoneInfo("America/New_York")
UTC = datetime.timezone.utc
GITHUB_API = "https://api.github.com"

BASE_HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "enterprise-github-audit-prod"
}

MAX_RETRIES = 3
RETRY_BACKOFF = 2  # seconds


# ==============================
# UTILITY FUNCTIONS
# ==============================

def github_get(url, headers, params=None):
    """GET wrapper with retry + rate-limit awareness"""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(url, headers=headers, params=params, timeout=30)

            # Rate limit handling
            if r.status_code == 403 and "rate limit" in r.text.lower():
                reset_time = int(r.headers.get("X-RateLimit-Reset", 0))
                sleep_time = max(reset_time - int(time.time()), 5)
                print(f"[WARN] Rate limit reached. Sleeping {sleep_time}s...", flush=True)
                time.sleep(sleep_time)
                continue

            r.raise_for_status()
            return r.json()

        except requests.RequestException as e:
            if attempt == MAX_RETRIES:
                print(f"[ERROR] GitHub API call failed after retries: {e}", file=sys.stderr)
                raise
            sleep = RETRY_BACKOFF ** attempt
            print(f"[WARN] API call failed (attempt {attempt}). Retrying in {sleep}s...")
            time.sleep(sleep)


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


# ==============================
# MAIN LOGIC
# ==============================

def main():
    args = parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN not set")

    headers = {**BASE_HEADERS, "Authorization": f"token {token}"}

    # Case-insensitive ITAP normalization
    itaps = [i.strip().upper() for i in args.itaps.split(",")]

    now_et = datetime.datetime.now(ET)
    cutoff = calculate_cutoff(now_et, args.months)

    print(f"[INFO] Scan started for org: {args.org}")
    print(f"[INFO] Cutoff date: {cutoff.strftime('%Y-%m-%d %Z')}")

    # ==============================
    # Fetch Repositories
    # ==============================

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

    print(f"[INFO] Total repos fetched: {len(repos)}")

    stale = []

    # ==============================
    # Scan Branches
    # ==============================

    for repo in repos:
        repo_name = repo.get("name", "")
        repo_upper = repo_name.upper()

        if not any(itap in repo_upper for itap in itaps):
            continue

        print(f"[INFO] Scanning repo: {repo_name}")

        branch_page = 1

        while True:
            branches = github_get(
                f"{GITHUB_API}/repos/{args.org}/{repo_name}/branches",
                headers,
                {"per_page": 100, "page": branch_page}
            )

            if not branches:
                break

            for br in branches:
                name = br.get("name", "")

                if br.get("protected"):
                    continue
                if name in PROTECTED_BRANCHES or name.startswith(RELEASE_PREFIX):
                    continue

                commit_data = github_get(br["commit"]["url"], headers)
                commit = commit_data.get("commit", {})

                author_info = commit.get("author") or {}
                date_str = author_info.get("date")

                if not date_str:
                    continue

                commit_utc = datetime.datetime.strptime(
                    date_str, "%Y-%m-%dT%H:%M:%SZ"
                ).replace(tzinfo=UTC)

                commit_et = commit_utc.astimezone(ET)

                if commit_et <= cutoff:
                    age = (
                        (now_et.year - commit_et.year) * 12 +
                        (now_et.month - commit_et.month)
                    )

                    author_name = author_info.get("name") or "unknown"
                    author_email = author_info.get("email") or "unknown"

                    stale.append([
                        repo_name,
                        name,
                        commit_et.strftime("%Y-%m-%d %I:%M %p %Z"),
                        age,
                        author_name,
                        author_email
                    ])

            branch_page += 1

    if not stale:
        print("[INFO] No stale branches found.")
        return

    # Sort by age descending
    stale.sort(key=lambda x: x[3], reverse=True)

    os.makedirs(args.out, exist_ok=True)

    # ==============================
    # CSV Output
    # ==============================

    with open(f"{args.out}/stale_report.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Repo", "Branch", "Last Commit", "Age (Months)", "Author", "Email"])
        writer.writerows(stale)

    # ==============================
    # HTML Email Output
    # ==============================

    scan_time = now_et.strftime("%a %b %d %H:%M:%S %Z %Y")

    with open(f"{args.out}/email.html", "w") as f:
        f.write(f"""
<h2>Stale GitHub Branch Audit Report</h2>
<p><b>Organization:</b> {args.org}</p>
<p><b>Scan Date:</b> {scan_time}</p>
<p>Branches inactive for <b>≥ {args.months} calendar months</b>.</p>
<p><b>Total Stale Branches Found:</b> {len(stale)}</p>

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
  <li>Deletion requires a separate approval-gated pipeline</li>
</ul>
""")

    print(f"[INFO] Stale branch report generated. Count: {len(stale)}")


if __name__ == "__main__":
    main()

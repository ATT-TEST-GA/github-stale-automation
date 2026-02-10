#!/usr/bin/env python3
"""
Enterprise GitHub stale branch scanner
Read-only, audit-safe, calendar-month based
"""

import argparse
import csv
import datetime
import os
import requests
from zoneinfo import ZoneInfo

# ---- Constants (Governance Approved) ----
PROTECTED_BRANCHES = {"main", "master", "develop", "prod"}
RELEASE_PREFIX = "release/"
ET = ZoneInfo("America/New_York")
UTC = datetime.timezone.utc

# ---- Helpers ----
def github_get(url: str, headers: dict):
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()

def parse_args():
    parser = argparse.ArgumentParser(description="Scan GitHub org for stale branches")
    parser.add_argument("--org", required=True)
    parser.add_argument("--itaps", required=True)
    parser.add_argument("--months", type=int, required=True)
    parser.add_argument("--out", required=True)
    return parser.parse_args()

# ---- Main Logic ----
def main():
    args = parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN not set")

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json"
    }

    itap_ids = [i.strip() for i in args.itaps.split(",")]

    now_et = datetime.datetime.now(ET)

    # Calendar month cutoff
    cutoff_month = now_et.month - args.months
    cutoff_year = now_et.year
    while cutoff_month <= 0:
        cutoff_month += 12
        cutoff_year -= 1
    cutoff = datetime.datetime(cutoff_year, cutoff_month, 1, tzinfo=ET)

    repos = []
    page = 1
    while True:
        batch = github_get(
            f"https://api.github.com/orgs/{args.org}/repos?per_page=100&page={page}",
            headers
        )
        if not batch:
            break
        repos.extend(batch)
        page += 1

    stale_records = []

    for repo in repos:
        if not any(itap in repo["name"] for itap in itap_ids):
            continue

        branches = github_get(repo["branches_url"].replace("{/branch}", ""), headers)

        for branch in branches:
            name = branch["name"]

            if branch.get("protected"):
                continue
            if name in PROTECTED_BRANCHES or name.startswith(RELEASE_PREFIX):
                continue

            commit_info = github_get(branch["commit"]["url"], headers)["commit"]
            commit_utc = datetime.datetime.strptime(
                commit_info["author"]["date"],
                "%Y-%m-%dT%H:%M:%SZ"
            ).replace(tzinfo=UTC)

            commit_et = commit_utc.astimezone(ET)

            if commit_et <= cutoff:
                age_months = (
                    (now_et.year - commit_et.year) * 12
                    + (now_et.month - commit_et.month)
                )

                stale_records.append([
                    repo["name"],
                    name,
                    commit_et.strftime("%Y-%m-%d %I:%M %p %Z"),
                    age_months,
                    commit_info["author"]["name"] or "unknown",
                    commit_info["author"]["email"] or "unknown"
                ])

    if not stale_records:
        return

    os.makedirs(args.out, exist_ok=True)

    # CSV (machine-readable)
    csv_path = f"{args.out}/stale_report.csv"
    with open(csv_path, "w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow([
            "Repository", "Branch", "LastCommit(ET)",
            "AgeMonths", "Author", "Email"
        ])
        writer.writerows(stale_records)

    # TXT (human-readable)
    txt_path = f"{args.out}/stale_report.txt"
    with open(txt_path, "w") as txtfile:
        for r in stale_records:
            txtfile.write(
                f"Repo: {r[0]}\n"
                f"Branch: {r[1]}\n"
                f"Last Commit: {r[2]}\n"
                f"Age: {r[3]} months\n"
                f"Author: {r[4]}\n"
                f"Email: {r[5]}\n"
                + "-" * 60 + "\n"
            )

    # Email HTML
    html_path = f"{args.out}/email.html"
    with open(html_path, "w") as html:
        html.write("<h3>Stale Git Branch Report</h3>")
        html.write("<table border='1' cellpadding='6'>")
        html.write(
            "<tr><th>Repo</th><th>Branch</th><th>Last Commit</th>"
            "<th>Age (Months)</th><th>Author</th><th>Email</th></tr>"
        )
        for r in stale_records:
            html.write("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>")
        html.write("</table>")

if __name__ == "__main__":
    main()


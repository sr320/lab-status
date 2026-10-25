"""Count the last month of Claude Code commits across lab GitHub repos and write them to JSON.

The lab is on a claude.ai Team plan, which has no usage API, so commits carrying
Claude Code's "Co-Authored-By: Claude" trailer are the public signal we can see.

Usage: python scripts/claude_activity.py OUT.json   (reads GITHUB_TOKEN if set)
"""
import collections
import datetime as dt
import json
import os
import sys
import time
import urllib.parse
import urllib.request

# GitHub search qualifiers; add a lab member's "user:<login>" to include their own repos.
SCOPES = ["org:RobertsLab", "user:sr320"]
# GitHub logins whose profile has no display name
ALIASES = {"kubu4": "Sam"}
DAYS = 30
TRAILER = "co-authored-by: claude"
API = "https://api.github.com"


def get(path, params=None):
    url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "lab-status"})
    if os.environ.get("GITHUB_TOKEN"):
        req.add_header("Authorization", "Bearer " + os.environ["GITHUB_TOKEN"])
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def search(scope, since):
    q = f'{scope} "Co-Authored-By: Claude" committer-date:>={since}'
    for page in range(1, 11):  # search returns at most 1000 results
        d = get("/search/commits", {"q": q, "per_page": 100, "page": page, "sort": "committer-date"})
        yield from d["items"]
        if len(d["items"]) < 100:
            return
        time.sleep(2)


names = {}
def first_name(login, fallback):
    if login in ALIASES:
        return ALIASES[login]
    if login and login not in names:
        try:
            names[login] = (get(f"/users/{login}").get("name") or "").strip()
        except Exception:
            names[login] = ""
    full = (names.get(login) if login else "") or fallback or login or "unknown"
    return full.split()[0].capitalize() if full.lower() != "claude" else "Claude (cloud)"


def main(out):
    today = dt.datetime.now(dt.timezone.utc).date()
    since = today - dt.timedelta(days=DAYS - 1)
    commits = {}
    for scope in SCOPES:
        for c in search(scope, since.isoformat()):
            if TRAILER in c["commit"]["message"].lower() or c["commit"]["author"]["name"].lower() == "claude":
                commits[c["sha"]] = c

    daily = collections.Counter()
    people = collections.defaultdict(lambda: {"commits": 0, "commits_7d": 0, "repos": collections.Counter()})
    repos = collections.Counter()
    for c in commits.values():
        day = dt.date.fromisoformat(c["commit"]["committer"]["date"][:10])
        login = (c.get("author") or {}).get("login")
        p = people[first_name(login, c["commit"]["author"]["name"])]
        p["commits"] += 1
        p["commits_7d"] += (today - day).days < 7
        repo = c["repository"]["full_name"]
        p["repos"][repo] += 1
        repos[repo] += 1
        daily[day.isoformat()] += 1

    doc = {
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "days": DAYS, "scopes": SCOPES, "total": len(commits),
        "daily": [[(since + dt.timedelta(days=i)).isoformat(), daily[(since + dt.timedelta(days=i)).isoformat()]] for i in range(DAYS)],
        "people": sorted(({"name": n, "commits": p["commits"], "commits_7d": p["commits_7d"],
                           "top_repo": p["repos"].most_common(1)[0][0], "repos": len(p["repos"])}
                          for n, p in people.items()), key=lambda x: -x["commits"]),
        "repos": [{"repo": r, "commits": n} for r, n in repos.most_common(8)],
    }
    with open(out, "w") as f:
        json.dump(doc, f, indent=1)
    print(f"{len(commits)} Claude commits from {len(people)} people written to {out}")


if __name__ == "__main__":
    main(*sys.argv[1:])

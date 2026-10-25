"""Summarise the last week of commits to RobertsLab repos and write them to JSON.

Only each repo's default branch is counted, so data branches that bots push to
every few minutes (seneye-data, server-status) stay out; bot and merge commits are skipped.

Usage: python scripts/github_activity.py OUT.json   (reads GITHUB_TOKEN if set)
"""
import collections
import datetime as dt
import json
import sys

from claude_activity import first_name, get

ORG = "RobertsLab"
DAYS = 7
RECENT = 12


def main(out):
    now = dt.datetime.now(dt.timezone.utc)
    since = now - dt.timedelta(days=DAYS)
    repos = []
    for page in range(1, 4):
        batch = get(f"/orgs/{ORG}/repos", {"sort": "pushed", "per_page": 100, "page": page})
        repos += batch
        if len(batch) < 100 or batch[-1]["pushed_at"] < since.isoformat():
            break

    rows, recent, people = [], [], set()
    for r in repos:
        if r["archived"] or not r["pushed_at"] or r["pushed_at"] < since.isoformat():
            continue
        commits = []
        for page in range(1, 6):
            batch = get(f"/repos/{r['full_name']}/commits",
                        {"sha": r["default_branch"], "since": since.isoformat(), "per_page": 100, "page": page})
            commits += batch
            if len(batch) < 100:
                break
        who = collections.Counter()
        kept = []
        for c in commits:
            login = (c.get("author") or {}).get("login") or ""
            if (login.endswith("[bot]") or login in ("web-flow", "actions") or len(c["parents"]) > 1
                    or c["commit"]["author"]["name"].lower().endswith(("[bot]", "-bot"))):
                continue
            name = first_name(login, c["commit"]["author"]["name"])
            who[name] += 1
            kept.append(c)
            recent.append({"repo": r["name"], "who": name, "at": c["commit"]["committer"]["date"],
                           "msg": c["commit"]["message"].split("\n")[0][:120], "url": c["html_url"]})
        if not kept:
            continue
        people.update(who)
        rows.append({"repo": r["name"], "url": r["html_url"], "commits": len(kept),
                     "people": [n for n, _ in who.most_common()], "last_at": kept[0]["commit"]["committer"]["date"]})

    rows.sort(key=lambda x: x["last_at"], reverse=True)
    recent.sort(key=lambda x: x["at"], reverse=True)
    doc = {
        "updated_at": now.isoformat(timespec="seconds"), "org": ORG, "days": DAYS,
        "total": sum(x["commits"] for x in rows), "people": sorted(people),
        "repos": rows, "recent": recent[:RECENT],
    }
    with open(out, "w") as f:
        json.dump(doc, f, indent=1)
    print(f"{doc['total']} commits in {len(rows)} {ORG} repos written to {out}")


if __name__ == "__main__":
    main(*sys.argv[1:])

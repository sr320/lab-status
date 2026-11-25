"""Latest post in each lab notebook listed on robertslab.info/notebooks.html.

Usage: python scripts/notebooks.py OUT.json

The list of notebooks is read from the `var notebooks = [...]` array on that
page, so adding someone there adds them here. For each one:
  gh + feed  newest item in its RSS/Atom feed (title and date)
  gh         latest commit to its repo (date only)
  wp         newest post by that author on genefish.wordpress.com
GITHUB_TOKEN, when set, is used for the commits API.
"""
import datetime as dt
import email.utils
import html
import json
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET

PAGE = "https://robertslab.info/notebooks.html"
WP_POSTS = "https://public-api.wordpress.com/rest/v1.1/sites/genefish.wordpress.com/posts/?number=100&fields=date,title,author,URL"
UA = {"User-Agent": "lab-status-dashboard"}


def get(url, headers=None):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def parse_date(s):
    if not s:
        return None
    s = s.strip()
    try:
        d = email.utils.parsedate_to_datetime(s)
    except (TypeError, ValueError):
        try:
            d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc)


def notebook_list():
    page = get(PAGE).decode("utf-8", "replace")
    block = re.search(r"var notebooks = \[(.*?)\];", page, re.S)
    if not block:
        raise SystemExit("notebook list not found on " + PAGE)
    out = []
    for obj in re.findall(r"\{([^{}]*)\}", block.group(1)):
        nb = dict(re.findall(r'(\w+)\s*:\s*"([^"]*)"', obj))
        if nb.get("name") and nb.get("url"):
            out.append(nb)
    return out


def local(tag):
    return tag.rsplit("}", 1)[-1]


def newest_in_feed(url):
    root = ET.fromstring(get(url))
    best = None
    for item in root.iter():
        if local(item.tag) not in ("item", "entry"):
            continue
        title = date = link = None
        for c in item:
            n = local(c.tag)
            if n == "title":
                title = (c.text or "").strip()
            elif n in ("pubDate", "published") or (n == "updated" and date is None):
                date = parse_date(c.text)
            elif n == "link":
                link = (c.text or "").strip() or c.get("href")
        if date and (best is None or date > best[0]):
            best = (date, title, link)
    return best


def last_commit(repo):
    headers = {"Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    commits = json.loads(get(f"https://api.github.com/repos/{repo}/commits?per_page=1", headers))
    return parse_date(commits[0]["commit"]["committer"]["date"]) if commits else None


def main(out):
    nbs = notebook_list()
    wp = {}
    if any(nb.get("type") == "wp" for nb in nbs):
        try:
            for p in json.loads(get(WP_POSTS)).get("posts", []):
                login, d = (p.get("author") or {}).get("login"), parse_date(p.get("date"))
                if login and d and (login not in wp or d > wp[login][0]):
                    wp[login] = (d, p.get("title"), p.get("URL"))
        except Exception as e:  # one source failing shouldn't drop everyone else
            print("genefish.wordpress.com:", e, file=sys.stderr)
    rows = []
    for nb in nbs:
        row = {"name": nb["name"], "url": nb["url"], "last_post": None, "title": None, "post_url": None, "via": None}
        try:
            if nb.get("type") == "wp":
                hit, via = wp.get(nb.get("login")), "wordpress"
            else:
                hit, via = (newest_in_feed(nb["feed"]), "feed") if nb.get("feed") else (None, None)
                if not hit and nb.get("repo"):
                    d = last_commit(nb["repo"])
                    hit, via = ((d, None, None), "commit") if d else (None, None)
            if hit:
                row.update(last_post=hit[0].isoformat(timespec="seconds"), title=html.unescape(hit[1]) if hit[1] else None, post_url=hit[2] or None, via=via)
        except Exception as e:
            row["error"] = str(e)[:200]
            print(nb["name"], e, file=sys.stderr)
        rows.append(row)
    rows.sort(key=lambda r: r["last_post"] or "", reverse=True)
    doc = {"updated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "source": PAGE, "notebooks": rows}
    with open(out, "w") as f:
        json.dump(doc, f, indent=1)
    print(f"{sum(1 for r in rows if r['last_post'])} of {len(rows)} notebooks dated, written to {out}")


if __name__ == "__main__":
    main(*sys.argv[1:])

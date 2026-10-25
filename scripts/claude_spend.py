"""Total this month's Claude API spend from the Admin API cost report and write it to JSON.

Needs an Admin API key (sk-ant-admin...) in ANTHROPIC_ADMIN_KEY. Covers the Console
(API) organization only; claude.ai Team plan seats and credit balances have no API.

Usage: python scripts/claude_spend.py OUT.json
"""
import datetime as dt
import json
import os
import sys
import urllib.parse
import urllib.request

API = "https://api.anthropic.com/v1/organizations/cost_report"


def get(params):
    req = urllib.request.Request(API + "?" + urllib.parse.urlencode(params, doseq=True), headers={
        "x-api-key": os.environ["ANTHROPIC_ADMIN_KEY"], "anthropic-version": "2023-06-01",
        "User-Agent": "lab-status (https://github.com/sr320/lab-status)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def main(out):
    if not os.environ.get("ANTHROPIC_ADMIN_KEY"):
        sys.exit("ANTHROPIC_ADMIN_KEY not set; skipping")
    now = dt.datetime.now(dt.timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    params = {"starting_at": start.isoformat().replace("+00:00", "Z"), "bucket_width": "1d", "limit": 31}
    daily = {}
    while True:
        d = get(params)
        for b in d["data"]:
            # amounts are decimal strings in cents
            daily[b["starting_at"][:10]] = sum(float(x["amount"]) for x in b["results"]) / 100
        if not d.get("has_more"):
            break
        params["page"] = d["next_page"]

    days = [(start + dt.timedelta(days=i)).date().isoformat() for i in range((now - start).days + 1)]
    doc = {
        "updated_at": now.isoformat(timespec="seconds"), "month": start.strftime("%Y-%m"), "currency": "USD",
        "total": round(sum(daily.values()), 2),
        "daily": [[day, round(daily.get(day, 0), 2)] for day in days],
    }
    with open(out, "w") as f:
        json.dump(doc, f, indent=1)
    print(f"${doc['total']:.2f} spent in {doc['month']} written to {out}")


if __name__ == "__main__":
    main(*sys.argv[1:])

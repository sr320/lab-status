"""Total this month's Claude API spend from the Admin API cost report and write it to JSON.

Spend is split by model straight from the cost report. The cost report can't group by
API key, so per-key spend is an estimate: each model's cost for each token type is shared
out across keys by their share of those tokens in the usage report.

Needs an Admin API key (sk-ant-admin...) in ANTHROPIC_ADMIN_KEY. Covers the Console
(API) organization only; claude.ai Team plan seats and credit balances have no API.

Usage: python scripts/claude_spend.py OUT.json
"""
import collections
import datetime as dt
import json
import os
import sys
import urllib.parse
import urllib.request

API = "https://api.anthropic.com/v1/organizations/"
# cost report token_type -> how to read that count from a usage report row
TOKEN_FIELDS = {
    "uncached_input_tokens": lambda r: r["uncached_input_tokens"],
    "cache_read_input_tokens": lambda r: r["cache_read_input_tokens"],
    "cache_creation.ephemeral_5m_input_tokens": lambda r: r["cache_creation"]["ephemeral_5m_input_tokens"],
    "cache_creation.ephemeral_1h_input_tokens": lambda r: r["cache_creation"]["ephemeral_1h_input_tokens"],
    "output_tokens": lambda r: r["output_tokens"],
}
OTHER = {"web_search": "Web search", "code_execution": "Code execution", "session_usage": "Managed Agents sessions"}


def get(path, params):
    req = urllib.request.Request(API + path + "?" + urllib.parse.urlencode(params, doseq=True), headers={
        "x-api-key": os.environ["ANTHROPIC_ADMIN_KEY"], "anthropic-version": "2023-06-01",
        "User-Agent": "lab-status (https://github.com/sr320/lab-status)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def buckets(path, params):
    params = dict(params)
    while True:
        d = get(path, params)
        yield from d["data"]
        if not d.get("has_more"):
            return
        params["page"] = d["next_page"]


def key_names():
    names, params = {}, {"limit": 1000}
    while True:
        d = get("api_keys", params)
        names.update((k["id"], k["name"]) for k in d["data"])
        if not d.get("has_more"):
            return names
        params["after_id"] = d["last_id"]


def by_key(start, token_cost):
    """Estimate each API key's share of the token cost from its share of each token type."""
    tokens = collections.defaultdict(lambda: collections.Counter())  # (model, token_type) -> key -> tokens
    use = collections.Counter()
    for b in buckets("usage_report/messages", {"starting_at": start, "bucket_width": "1d", "limit": 31,
                                                "group_by[]": ["api_key_id", "model"]}):
        for r in b["results"]:
            for tt, f in TOKEN_FIELDS.items():
                tokens[(r["model"], tt)][r["api_key_id"]] += f(r)
            use[r["api_key_id"]] += r["uncached_input_tokens"] + r["output_tokens"]
    spend = collections.Counter()
    for k, cost in token_cost.items():
        n = sum(tokens[k].values())
        for key, t in tokens[k].items():
            spend[key] += cost * t / n if n else 0
    names = key_names()
    return sorted(({"key": names.get(k, k) if k else "Console Workbench (no key)", "usd": round(v, 2), "tokens": use[k]}
                   for k, v in spend.items() if v >= 0.005), key=lambda x: -x["usd"])


def main(out):
    if not os.environ.get("ANTHROPIC_ADMIN_KEY"):
        sys.exit("ANTHROPIC_ADMIN_KEY not set; skipping")
    now = dt.datetime.now(dt.timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    start_s = start.isoformat().replace("+00:00", "Z")
    daily, models, token_cost = collections.Counter(), collections.Counter(), collections.Counter()
    for b in buckets("cost_report", {"starting_at": start_s, "bucket_width": "1d", "limit": 31, "group_by[]": ["description"]}):
        for x in b["results"]:
            usd = float(x["amount"]) / 100  # amounts are decimal strings in cents
            daily[b["starting_at"][:10]] += usd
            models[x["model"] or OTHER.get(x["cost_type"], x["description"] or "Other")] += usd
            if x["cost_type"] == "tokens" and x["token_type"]:
                token_cost[(x["model"], x["token_type"])] += usd

    days = [(start + dt.timedelta(days=i)).date().isoformat() for i in range((now - start).days + 1)]
    doc = {
        "updated_at": now.isoformat(timespec="seconds"), "month": start.strftime("%Y-%m"), "currency": "USD",
        "total": round(sum(daily.values()), 2),
        "daily": [[day, round(daily.get(day, 0), 2)] for day in days],
        "models": [{"model": m, "usd": round(v, 2)} for m, v in models.most_common() if v >= 0.005],
    }
    try:
        doc["keys"] = by_key(start_s, token_cost)
    except Exception as e:  # keep the totals even if the per-key estimate fails
        print(f"per-key estimate skipped: {e}")
    with open(out, "w") as f:
        json.dump(doc, f, indent=1)
    print(f"${doc['total']:.2f} spent in {doc['month']} across {len(doc['models'])} models and "
          f"{len(doc.get('keys', []))} keys written to {out}")


if __name__ == "__main__":
    main(*sys.argv[1:])

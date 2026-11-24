"""Per-user Slurm usage on klone for the lab's accounts (stdlib only).

Runs on klone (see klone_usage.sh). One `sacct` call covers the last WINDOW_D
days plus everything running or pending now; `squeue` adds why pending jobs
are waiting. Only usernames, partitions, states and resource counts are
recorded -- never job names, paths or command lines.

Accounts like coenv are shared with other labs, so only lab members are named:
anyone in LAB_USERS (env KLONE_USERS, comma-separated), plus anyone who ran a
job under a LAB_ACCOUNTS account (env, default "srlab") in the window. Everyone
else is folded into one "other <account>" row.

Usage: python3 klone_usage.py OUT.json
"""
import datetime as dt
import json
import os
import subprocess
import sys
from collections import defaultdict

ACCOUNTS = os.environ.get("KLONE_ACCOUNTS", "srlab,coenv").split(",")
LAB_ACCOUNTS = set(os.environ.get("KLONE_LAB_ACCOUNTS", "srlab").split(","))
LAB_USERS = {u for u in os.environ.get("KLONE_USERS", "").split(",") if u}
WINDOW_D = int(os.environ.get("KLONE_WINDOW_D", "7"))

SACCT_FIELDS = ["User", "Account", "Partition", "State", "AllocCPUS", "ReqCPUS",
                "AllocTRES", "ReqMem", "Start", "End", "Submit"]
BAD_STATES = {"FAILED", "TIMEOUT", "OUT_OF_MEMORY", "NODE_FAIL", "PREEMPTED", "CANCELLED", "BOOT_FAIL", "DEADLINE"}


def run(cmd):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300).stdout


def parse_time(s):
    if not s or s in ("Unknown", "None", "N/A"):
        return None
    try:
        return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None


def mem_gb(s):
    """'480G', '4000M', '1.5T' -> GB. Returns None for anything else."""
    if not s:
        return None
    s = s.rstrip("nc")  # old ReqMem suffixes: per node / per cpu
    scale = {"K": 1 / 1024 ** 2, "M": 1 / 1024, "G": 1, "T": 1024}
    try:
        return float(s[:-1]) * scale[s[-1]] if s[-1] in scale else float(s) / 1024
    except (ValueError, IndexError):
        return None


def tres(s, key):
    for part in (s or "").split(","):
        k, _, v = part.partition("=")
        if k == key:
            return v
    return None


def is_ckpt(partition):
    return partition.split(",")[0].startswith("ckpt")


def main(out_path):
    now = dt.datetime.now()  # sacct prints local time
    # whole days: today so far plus the WINDOW_D - 1 days before it
    start = dt.datetime.combine(now.date() - dt.timedelta(days=WINDOW_D - 1), dt.time())
    raw = run(["sacct", "-a", "-X", "-n", "--parsable2", "-A", ",".join(ACCOUNTS),
               "-S", start.strftime("%Y-%m-%dT%H:%M:%S"), "-E", "now",
               "--format=" + ",".join(SACCT_FIELDS)])
    jobs = []
    for line in raw.splitlines():
        cells = line.split("|")
        if len(cells) != len(SACCT_FIELDS):
            continue
        j = dict(zip(SACCT_FIELDS, cells))
        j["State"] = j["State"].split()[0]  # "CANCELLED by 123" -> "CANCELLED"
        jobs.append(j)

    lab = set(LAB_USERS) | {j["User"] for j in jobs if j["Account"] in LAB_ACCOUNTS}

    def who(j):
        return j["User"] if j["User"] in lab else "other " + j["Account"]

    # pending reasons from squeue (optional; sacct doesn't carry them everywhere)
    reasons = defaultdict(lambda: defaultdict(int))
    try:
        for line in run(["squeue", "-h", "-t", "PD", "-A", ",".join(ACCOUNTS), "-o", "%u|%a|%r"]).splitlines():
            u, a, r = (line.split("|") + ["", "", ""])[:3]
            reasons[u if u in lab else "other " + a][r or "unknown"] += 1
    except (subprocess.SubprocessError, OSError):
        pass

    days = [start.date() + dt.timedelta(days=i) for i in range(WINDOW_D)]
    day_idx = {d: i for i, d in enumerate(days)}
    per_day = [{"date": d.isoformat(), "own": 0.0, "ckpt": 0.0} for d in days]

    users = {}
    for j in jobs:
        name = who(j)
        u = users.setdefault(name, {
            "user": name, "lab": name in lab,
            "now": {"running": 0, "pending": 0, "cpus": 0, "mem_gb": 0.0, "pending_cpus": 0, "partitions": {}},
            "window": {"cpu_hours": 0.0, "ckpt_cpu_hours": 0.0, "jobs": 0, "completed": 0, "problems": {}}})
        ckpt = is_ckpt(j["Partition"])
        st = j["State"]
        if st == "RUNNING":
            n = u["now"]
            n["running"] += 1
            cpus = int(j["AllocCPUS"] or 0)
            n["cpus"] += cpus
            n["mem_gb"] += mem_gb(tres(j["AllocTRES"], "mem")) or 0
            key = j["Account"] + "/" + j["Partition"]
            n["partitions"][key] = n["partitions"].get(key, 0) + cpus
        elif st == "PENDING":
            u["now"]["pending"] += 1
            u["now"]["pending_cpus"] += int(j["ReqCPUS"] or 0)
            continue

        # CPU-hours inside the window, clipped to it and split by day
        t0, t1 = parse_time(j["Start"]), parse_time(j["End"]) or now
        if not t0 or t1 <= start:
            continue
        t0 = max(t0, start)
        cpus = int(j["AllocCPUS"] or 0)
        hours = cpus * (t1 - t0).total_seconds() / 3600
        w = u["window"]
        w["cpu_hours"] += hours
        if ckpt:
            w["ckpt_cpu_hours"] += hours
        if st != "RUNNING":
            w["jobs"] += 1
            if st == "COMPLETED":
                w["completed"] += 1
            elif st in BAD_STATES:
                w["problems"][st] = w["problems"].get(st, 0) + 1
        t = t0
        while t < t1:
            nxt = min(t1, dt.datetime.combine(t.date() + dt.timedelta(days=1), dt.time()))
            i = day_idx.get(t.date())
            if i is not None and u["lab"]:
                per_day[i]["ckpt" if ckpt else "own"] += cpus * (nxt - t).total_seconds() / 3600
            t = nxt

    for name, rs in reasons.items():
        if name in users:
            users[name]["now"]["pending_reasons"] = dict(rs)

    rows = sorted(users.values(), key=lambda u: (not u["lab"], -u["now"]["cpus"], -u["window"]["cpu_hours"]))
    for u in rows:
        u["now"]["mem_gb"] = round(u["now"]["mem_gb"], 1)
        u["window"]["cpu_hours"] = round(u["window"]["cpu_hours"], 1)
        u["window"]["ckpt_cpu_hours"] = round(u["window"]["ckpt_cpu_hours"], 1)
    for d in per_day:
        d["own"], d["ckpt"] = round(d["own"], 1), round(d["ckpt"], 1)

    doc = {
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "accounts": ACCOUNTS,
        "window_days": WINDOW_D,
        "users": rows,
        "days": per_day,  # lab members only
    }
    with open(out_path, "w") as f:
        json.dump(doc, f, indent=1)


if __name__ == "__main__":
    main(sys.argv[1])

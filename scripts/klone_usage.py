"""Per-user Slurm usage on klone for the lab's accounts (stdlib only).

Runs on klone (see klone_usage.sh). One `sacct` call covers the last WINDOW_D
days plus everything running or pending now; `squeue` adds why pending jobs
are waiting and lists lab members' current jobs. Usernames, partitions,
states, nodes and resource counts are recorded. Job names are kept only for
lab members' current jobs, cut to the last path part and NAME_MAX characters;
paths and command lines are never recorded.

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
NAME_MAX = 24
JOBS_MAX = 200

SACCT_FIELDS = ["JobIDRaw", "User", "Account", "Partition", "State", "AllocCPUS", "ReqCPUS",
                "AllocTRES", "ReqMem", "Start", "End", "Submit"]
BAD_STATES = {"FAILED", "TIMEOUT", "OUT_OF_MEMORY", "NODE_FAIL", "PREEMPTED", "CANCELLED", "BOOT_FAIL", "DEADLINE"}


def run(cmd):
    # klone's system python is 3.6: no capture_output= or text=
    return subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          universal_newlines=True, timeout=300).stdout


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


def base_account(account, names):
    """Klone's Slurm accounts can carry a partition prefix, e.g. cpu-g2-coenv
    for coenv. Return the configured name the account belongs to, or None."""
    parts = account.split("-")
    for n in names:
        if account == n or n in parts:
            return n
    return None


def tidy_name(name):
    """'$HOME/bin/hyakalloc_snapshot.sh' -> 'hyakalloc_snapshot.sh', then shorten."""
    name = name.rstrip("/").split("/")[-1] or "?"
    return name if len(name) <= NAME_MAX else name[:NAME_MAX - 1] + "\u2026"


def seconds(t):
    """squeue %M: 'M:SS', 'H:MM:SS' or 'D-HH:MM:SS' -> seconds; None otherwise."""
    try:
        d, _, hms = t.rpartition("-")
        parts = [int(x) for x in hms.split(":")]
        while len(parts) < 3:
            parts.insert(0, 0)
        return (int(d) if d else 0) * 86400 + parts[0] * 3600 + parts[1] * 60 + parts[2]
    except ValueError:
        return None


def is_ckpt(partition):
    return partition.split(",")[0].startswith("ckpt")


def main(out_path):
    now = dt.datetime.now()  # sacct prints local time
    # whole days: today so far plus the WINDOW_D - 1 days before it
    start = dt.datetime.combine(now.date() - dt.timedelta(days=WINDOW_D - 1), dt.time())
    seen = set()

    def sacct(select):
        out = []
        raw = run(["sacct", "-X", "-n", "--parsable2"] + select +
                  ["-S", start.strftime("%Y-%m-%dT%H:%M:%S"), "-E", "now",
                   "--format=" + ",".join(SACCT_FIELDS)])
        for line in raw.splitlines():
            cells = line.split("|")
            if len(cells) != len(SACCT_FIELDS):
                continue
            j = dict(zip(SACCT_FIELDS, cells))
            if j["JobIDRaw"] in seen:
                continue
            seen.add(j["JobIDRaw"])
            j["State"] = j["State"].split()[0]  # "CANCELLED by 123" -> "CANCELLED"
            out.append(j)
        return out

    # Everyone on the lab's accounts, then every other job lab members ran on
    # any account -- checkpoint jobs are charged to accounts not in ACCOUNTS.
    jobs = sacct(["-a", "-A", ",".join(ACCOUNTS)])
    lab = set(LAB_USERS) | {j["User"] for j in jobs if base_account(j["Account"], LAB_ACCOUNTS)}
    if lab:
        jobs += sacct(["-u", ",".join(sorted(lab))])

    def other(account):
        return "other " + (base_account(account, ACCOUNTS) or account)

    def group(j):
        """Where the CPUs came from: "ckpt", or the lab account (srlab, coenv)."""
        return "ckpt" if is_ckpt(j["Partition"]) else (base_account(j["Account"], ACCOUNTS) or j["Account"])

    def add(d, k, v):
        d[k] = d.get(k, 0) + v

    def who(j):
        return j["User"] if j["User"] in lab else other(j["Account"])

    # pending reasons from squeue (optional; sacct doesn't carry them everywhere)
    reasons = defaultdict(lambda: defaultdict(int))
    pend_seen = set()
    queries = [["-A", ",".join(ACCOUNTS)]] + ([["-u", ",".join(sorted(lab))]] if lab else [])
    for q in queries:
        try:
            out = run(["squeue", "-h", "-t", "PD"] + q + ["-o", "%i|%u|%a|%r"])
        except (subprocess.SubprocessError, OSError):
            continue
        for line in out.splitlines():
            i, u, a, r = (line.split("|") + ["", "", "", ""])[:4]
            if i in pend_seen:
                continue
            pend_seen.add(i)
            reasons[u if u in lab else other(a)][r or "unknown"] += 1

    # lab members' running and pending jobs, one row each
    job_rows = []
    if lab:
        try:
            out = run(["squeue", "-h", "-u", ",".join(sorted(lab)), "-o", "%i|%u|%a|%P|%j|%T|%M|%C|%R"])
        except (subprocess.SubprocessError, OSError):
            out = ""
        for line in out.splitlines():
            cells = line.split("|", 8)
            if len(cells) != 9:
                continue
            i, u, a, part, name, state, elapsed, cpus, where = cells
            running = state == "RUNNING"
            job_rows.append({
                "id": i, "user": u, "partition": part,
                "group": "ckpt" if is_ckpt(part) else (base_account(a, ACCOUNTS) or a),
                "name": tidy_name(name), "state": state,
                "elapsed_s": seconds(elapsed) if running else None,
                "cpus": int(cpus) if cpus.isdigit() else None,
                "nodes": where if running else None,
                "reason": None if running else where.strip("()"),
            })
        job_rows.sort(key=lambda j: (j["state"] != "RUNNING", -(j["elapsed_s"] or 0), j["id"]))

    days = [start.date() + dt.timedelta(days=i) for i in range(WINDOW_D)]
    day_idx = {d: i for i, d in enumerate(days)}
    per_day = [{"date": d.isoformat(), "own": 0.0, "ckpt": 0.0, "groups": {}} for d in days]

    users = {}
    for j in jobs:
        name = who(j)
        u = users.setdefault(name, {
            "user": name, "lab": name in lab,
            "now": {"running": 0, "pending": 0, "cpus": 0, "mem_gb": 0.0, "pending_cpus": 0, "partitions": {}, "groups": {}},
            "window": {"cpu_hours": 0.0, "ckpt_cpu_hours": 0.0, "groups": {}, "jobs": 0, "completed": 0, "problems": {}}})
        ckpt = is_ckpt(j["Partition"])
        g = group(j)
        st = j["State"]
        if st == "RUNNING":
            n = u["now"]
            n["running"] += 1
            cpus = int(j["AllocCPUS"] or 0)
            n["cpus"] += cpus
            n["mem_gb"] += mem_gb(tres(j["AllocTRES"], "mem")) or 0
            key = j["Account"] + "/" + j["Partition"]
            add(n["partitions"], key, cpus)
            add(n["groups"], g, cpus)
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
        add(w["groups"], g, hours)
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
                h = cpus * (nxt - t).total_seconds() / 3600
                per_day[i]["ckpt" if ckpt else "own"] += h
                add(per_day[i]["groups"], g, h)
            t = nxt

    for name, rs in reasons.items():
        if name in users:
            users[name]["now"]["pending_reasons"] = dict(rs)

    rows = sorted(users.values(), key=lambda u: (not u["lab"], -u["now"]["cpus"], -u["window"]["cpu_hours"]))
    for u in rows:
        u["now"]["mem_gb"] = round(u["now"]["mem_gb"], 1)
        u["window"]["cpu_hours"] = round(u["window"]["cpu_hours"], 1)
        u["window"]["ckpt_cpu_hours"] = round(u["window"]["ckpt_cpu_hours"], 1)
        u["window"]["groups"] = {k: round(v, 1) for k, v in u["window"]["groups"].items()}
    for d in per_day:
        d["own"], d["ckpt"] = round(d["own"], 1), round(d["ckpt"], 1)
        d["groups"] = {k: round(v, 1) for k, v in d["groups"].items()}

    doc = {
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "accounts": ACCOUNTS,
        "window_days": WINDOW_D,
        "users": rows,
        "days": per_day,  # lab members only
        "jobs": job_rows[:JOBS_MAX],
        "jobs_total": len(job_rows),
    }
    with open(out_path, "w") as f:
        json.dump(doc, f, indent=1)


if __name__ == "__main__":
    main(sys.argv[1])

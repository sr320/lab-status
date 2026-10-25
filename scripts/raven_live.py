"""htop-style snapshot of raven, read straight from /proc (stdlib only).

Samples CPU for a couple of seconds so per-core and per-process numbers are
current, not lifetime averages like `ps %cpu`. Only the process name (comm) is
recorded, never the full command line.

Usage: python3 raven_live.py OUT.json
"""
import datetime as dt
import json
import os
import pwd
import sys
import time

SAMPLE_S = 2.0
TOP_N = 15
CLK = os.sysconf("SC_CLK_TCK")
PAGE = os.sysconf("SC_PAGE_SIZE")


def cpu_times():
    cores = {}
    with open("/proc/stat") as f:
        for line in f:
            if not line.startswith("cpu"):
                break
            name, *vals = line.split()
            vals = [int(v) for v in vals[:8]]
            idle = vals[3] + vals[4]
            cores[name] = (sum(vals) - idle, sum(vals))
    return cores


def proc_ticks():
    out = {}
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/stat") as f:
                raw = f.read()
            # comm can contain spaces and parens; it sits between the first "(" and the last ")".
            comm = raw[raw.index("(") + 1:raw.rindex(")")]
            rest = raw[raw.rindex(")") + 2:].split()
            ticks = int(rest[11]) + int(rest[12])
            start = int(rest[19])
            rss = int(rest[21]) * PAGE
            uid = os.stat(f"/proc/{pid}").st_uid
            out[int(pid)] = (comm, ticks, start, rss, uid)
        except (FileNotFoundError, ProcessLookupError, ValueError, IndexError, PermissionError):
            continue
    return out


def meminfo():
    m = {}
    with open("/proc/meminfo") as f:
        for line in f:
            k, v = line.split(":")
            m[k] = int(v.split()[0]) * 1024
    return m


def user_name(uid, cache={}):
    if uid not in cache:
        try:
            cache[uid] = pwd.getpwuid(uid).pw_name
        except KeyError:
            cache[uid] = str(uid)
    return cache[uid]


def main(out):
    c0, p0, t0 = cpu_times(), proc_ticks(), time.monotonic()
    time.sleep(SAMPLE_S)
    c1, p1, t1 = cpu_times(), proc_ticks(), time.monotonic()
    elapsed = t1 - t0

    def pct(a, b):
        busy, total = b[0] - a[0], b[1] - a[1]
        return round(100 * busy / total, 1) if total else 0.0

    cores = [pct(c0[k], c1[k]) for k in sorted(c1, key=lambda k: int(k[3:]) if k[3:] else -1) if k != "cpu"]
    mem = meminfo()
    mem_total = mem["MemTotal"]
    with open("/proc/uptime") as f:
        uptime_s = float(f.read().split()[0])
    boot = time.time() - uptime_s

    procs, users = [], {}
    for pid, (comm, ticks, start, rss, uid) in p1.items():
        prev = p0.get(pid)
        d = ticks - prev[1] if prev and prev[2] == start else ticks
        cpu = 100 * d / CLK / elapsed
        user = user_name(uid)
        u = users.setdefault(user, {"user": user, "cpu": 0.0, "mem_bytes": 0, "procs": 0})
        u["cpu"] += cpu
        u["mem_bytes"] += rss
        u["procs"] += 1
        if cpu >= 0.5 or rss > 1 << 30:
            procs.append({"pid": pid, "user": user, "name": comm, "cpu": round(cpu, 1),
                          "mem_percent": round(100 * rss / mem_total, 1), "rss_bytes": rss,
                          "running_s": int(time.time() - (boot + start / CLK))})
    procs.sort(key=lambda p: (-p["cpu"], -p["rss_bytes"]))
    user_rows = sorted((u for u in users.values() if u["cpu"] >= 1 or u["mem_bytes"] > 1 << 30),
                       key=lambda u: -u["cpu"])
    for u in user_rows:
        u["cpu"] = round(u["cpu"], 1)
        u["mem_percent"] = round(100 * u["mem_bytes"] / mem_total, 1)

    doc = {
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "host": os.uname().nodename,
        "uptime_s": int(uptime_s),
        "load": [round(x, 2) for x in os.getloadavg()],
        "cpu_percent": pct(c0["cpu"], c1["cpu"]),
        "cores": cores,
        "memory": {"total": mem_total, "available": mem["MemAvailable"],
                   "used": mem_total - mem["MemAvailable"],
                   "swap_total": mem["SwapTotal"], "swap_used": mem["SwapTotal"] - mem["SwapFree"]},
        "tasks": len(p1),
        "users": user_rows[:10],
        "processes": procs[:TOP_N],
    }
    with open(out, "w") as f:
        json.dump(doc, f, separators=(",", ":"))


if __name__ == "__main__":
    main(sys.argv[1])

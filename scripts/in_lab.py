"""Pull the lab Google Calendar and write the next week's "in lab" events to JSON.

Usage: python scripts/in_lab.py OUT.json [ICS_PATH_OR_URL]
"""
import datetime as dt
import json
import re
import sys
import urllib.request
from zoneinfo import ZoneInfo

import icalendar
import recurring_ical_events

ICS_URL = "https://calendar.google.com/calendar/ical/mrc305%40gmail.com/public/basic.ics"
TZ = ZoneInfo("America/Los_Angeles")
DAYS_AHEAD = 7
# "Sam in lab", "Derek @ lab", "Yaamini in FTR 134", "Grace In", "Aakriti - lab in"
IN_LAB = re.compile(r"^\s*(?P<name>.+?)\s*(?:-\s*)?(?:(?:(?<=[\s-])in|@)\s*(?:the\s+)?(?:lab|ftr\b.*)|(?<=[\s-])(?:lab\s+)?in)\s*$", re.I)
NOT_PRESENCE = re.compile(r"\b(not|check|meeting|talk|seminar|alarm|test|defense|call)\b", re.I)
# trailing phrases between the name and "in lab": "will be", "is", "'s working", "available"
NAME_TAIL = re.compile(r"(?:'s|\s+(?:will be|is|working|available|comes|lab work|qpcr|protein extractions|last day|helping \w+))+$", re.I)


def presence_name(title):
    m = IN_LAB.match(title)
    if not m or NOT_PRESENCE.search(title):
        return None
    return NAME_TAIL.sub("", m.group("name")).strip(" -") or None


def load(src):
    if src.startswith("http"):
        with urllib.request.urlopen(src, timeout=60) as r:
            return r.read()
    with open(src, "rb") as f:
        return f.read()


def as_dt(v):
    if isinstance(v, dt.datetime):
        return (v if v.tzinfo else v.replace(tzinfo=TZ)).astimezone(TZ), False
    return dt.datetime.combine(v, dt.time(), TZ), True


def main(out, src=ICS_URL):
    cal = icalendar.Calendar.from_ical(load(src))
    today = dt.datetime.now(TZ).date()
    window = recurring_ical_events.of(cal).between(today, today + dt.timedelta(days=DAYS_AHEAD))
    events = []
    for e in window:
        title = str(e.get("SUMMARY", "")).strip()
        name = presence_name(title)
        if not name:
            continue
        start, all_day = as_dt(e["DTSTART"].dt)
        end = as_dt(e["DTEND"].dt)[0] if "DTEND" in e else start + dt.timedelta(days=1 if all_day else 0, hours=0 if all_day else 1)
        events.append({"name": name, "title": title, "start": start.isoformat(),
                       "end": end.isoformat(), "all_day": all_day})
    events.sort(key=lambda x: (x["start"], x["name"].lower()))
    doc = {"updated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "timezone": str(TZ), "days_ahead": DAYS_AHEAD, "events": events}
    with open(out, "w") as f:
        json.dump(doc, f, indent=1)
    print(f"{len(events)} in-lab events written to {out}")


if __name__ == "__main__":
    main(*sys.argv[1:])

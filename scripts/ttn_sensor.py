"""Fetch the last day of uplinks from a TTN sensor and write them to JSON.

Readings come from the application's Storage Integration, which TTN's Sandbox keeps
for 24 hours, so it has to be turned on for the application. The API key
(TTN_APP_API_KEY) needs only "Read application traffic (uplink and downlink)".

Each reading keeps the decoded payload fields plus RSSI and SNR at each gateway that
heard it. Gateway locations and any location fields in the payload are left out,
because the output lands on a public branch.

Usage: python scripts/ttn_sensor.py OUT.json   (reads TTN_APP_API_KEY)
"""
import datetime as dt
import json
import os
import sys
import urllib.parse
import urllib.request

AS = "https://nam1.cloud.thethings.network/api/v3/as"
APP = "my-tracker-320"
DEVICE = "little-dragon-01"
FIELDS = ["up.uplink_message.decoded_payload", "up.uplink_message.rx_metadata", "up.uplink_message.f_cnt",
          "up.uplink_message.received_at"]
DROP = ("lat", "lon", "lng", "latitude", "longitude", "altitude", "location", "gps")


def uplinks():
    q = urllib.parse.urlencode({"last": "24h", "field_mask": ",".join(FIELDS)})
    url = f"{AS}/applications/{APP}/devices/{DEVICE}/packages/storage/uplink_message?{q}"
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + os.environ["TTN_APP_API_KEY"],
                                               "Accept": "text/event-stream", "User-Agent": "lab-status"})
    with urllib.request.urlopen(req, timeout=60) as r:
        # the storage API streams one {"result": {...}} object per line
        for line in r:
            line = line.strip()
            if line:
                yield json.loads(line)["result"]


def clean(payload):
    out = {}
    for k, v in (payload or {}).items():
        if any(d in k.lower() for d in DROP):
            continue
        if isinstance(v, (int, float, str, bool)) and not (isinstance(v, str) and len(v) > 40):
            out[k] = v
    return out


def main(out):
    if not os.environ.get("TTN_APP_API_KEY"):
        sys.exit("TTN_APP_API_KEY is not set; add it as a repository secret")
    readings = []
    for u in uplinks():
        m = u.get("uplink_message") or {}
        rx = [{"gateway": (g.get("gateway_ids") or {}).get("gateway_id"), "rssi": g.get("rssi"), "snr": g.get("snr")}
              for g in m.get("rx_metadata") or []]
        readings.append({"at": m.get("received_at") or u.get("received_at"), "f_cnt": m.get("f_cnt"),
                         "fields": clean(m.get("decoded_payload")), "rx": rx})
    readings.sort(key=lambda x: x["at"] or "")
    doc = {
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "application": APP, "device": DEVICE, "model": "Dragino LSN50v2-D20",
        "readings": readings,
    }
    with open(out, "w") as f:
        json.dump(doc, f, indent=1)
    print(f"{DEVICE}: {len(readings)} uplinks in the last 24 h written to {out}")


if __name__ == "__main__":
    main(*sys.argv[1:])

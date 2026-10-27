"""Fetch the TTN gateway's console stats and write them to JSON.

The connection stats come from the Gateway Server on nam1; the gateway's name and
model come from The Things Network's Identity Server, which lives on eu1 for every
cluster. Both take the same API key (TTN_API_KEY), which needs only the rights
"View gateway information" and "View gateway status".

The output lands on a public branch, so the gateway's location and IP addresses
(last_status.antenna_locations, last_status.ip, gateway_remote_address) are left out.

Usage: python scripts/ttn_gateway.py OUT.json   (reads TTN_API_KEY)
"""
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request

GATEWAY = "sr320-indoor-01"
GS = "https://nam1.cloud.thethings.network/api/v3"
IS = "https://eu1.cloud.thethings.network/api/v3"
INFO_FIELDS = "name,description,version_ids,frequency_plan_ids,created_at,updated_at"


def get(url):
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + os.environ["TTN_API_KEY"],
                                               "Accept": "application/json", "User-Agent": "lab-status"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def main(out):
    if not os.environ.get("TTN_API_KEY"):
        sys.exit("TTN_API_KEY is not set; add it as a repository secret")
    now = dt.datetime.now(dt.timezone.utc)
    info = get(f"{IS}/gateways/{GATEWAY}?field_mask={INFO_FIELDS}")
    try:
        s = get(f"{GS}/gs/gateways/{GATEWAY}/connection/stats")
        connected = True
    except urllib.error.HTTPError as e:
        # the Gateway Server answers 404 "not_connected" while the gateway is offline
        if e.code != 404:
            raise
        s, connected = {}, False

    status = s.get("last_status") or {}
    v = info.get("version_ids") or {}
    doc = {
        "updated_at": now.isoformat(timespec="seconds"),
        "gateway": GATEWAY,
        "name": info.get("name"),
        "description": info.get("description"),
        "model": {k: v.get(k) for k in ("brand_id", "model_id", "hardware_version", "firmware_version") if v.get(k)},
        "frequency_plans": info.get("frequency_plan_ids") or [],
        "connected": connected,
        "connected_at": s.get("connected_at"),
        "disconnected_at": s.get("disconnected_at"),
        "protocol": s.get("protocol"),
        "last_status_at": s.get("last_status_received_at"),
        "versions": status.get("versions") or {},
        "metrics": status.get("metrics") or {},
        "uplink_count": int(s.get("uplink_count") or 0),
        "last_uplink_at": s.get("last_uplink_received_at"),
        "downlink_count": int(s.get("downlink_count") or 0),
        "last_downlink_at": s.get("last_downlink_received_at"),
        "tx_ack_count": int(s.get("tx_acknowledgment_count") or 0),
        "round_trip_times": s.get("round_trip_times"),
        "sub_bands": s.get("sub_bands") or [],
    }
    with open(out, "w") as f:
        json.dump(doc, f, indent=1)
    print(f"{GATEWAY}: {'connected' if connected else 'not connected'}, {doc['uplink_count']} uplinks, written to {out}")


if __name__ == "__main__":
    main(*sys.argv[1:])

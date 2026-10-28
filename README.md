# lab-status

One-page status dashboard for the Roberts Lab: SHORE tank room (Seneye, tankcam, water quality, logbook) and computing (raven, gannet, klone).

Live: https://sr320.github.io/lab-status/

Everything is client-side in `index.html`. It pulls JSON at load and every 5 minutes from:

- `RobertsLab/resources` `server-status` branch (`status/external.json`, `status/internal.json`)
- `RobertsLab/shore-line` `seneye-data` branch (`seneye.json`)
- the SHORE site build (`/data/*.json` on ftr210.online or robertslab.github.io/shore-line)
- status.claude.com's public Statuspage API (`/api/v2/summary.json`) for Claude service status
- the AREE site's dashboard data (https://sr320.github.io/AREE/dashboard/data.json): the `kpis` block for study, evidence, candidate and harmonized-contrast counts, plus `commit` and `generated_at`.
- the Conditioning Atlas page itself (https://sr320.github.io/conditioning-atlas/, which allows cross-origin reads): the embedded `DATA` array for experiment, paper, species and stressor counts, the "built <date>" footer, and the `Last-Modified` header for when GitHub Pages last deployed it; plus the latest commit on `main` from the GitHub commits API.
- the Project White Whale dashboard's `data.json` (https://robertslab.github.io/project-white-whale/data.json), rebuilt every 3 hours; the light turns amber if it's more than 8 hours old or reports that branch claims or the gannet mirror couldn't be read.
- Packet Broker's public mapper record for the TTN gateway `sr320-indoor-01` (https://mapper.packetbroker.net/api/v2/gateways/netID=000013,tenantID=ttn,id=sr320-indoor-01): online flag, last update and packet rates per hour. No key is needed because the gateway's status is public in the TTN console. The record also holds the gateway's coordinates, which the page doesn't show. The console stats underneath it come from `ttn-gateway.json` (see "TTN gateway" below).

Thresholds (disk %, staleness hours) are constants near the top of the script.

## Who's in lab

`.github/workflows/in-lab.yml` runs every 15 minutes. It reads the lab Google Calendar's public iCal feed, keeps the next 7 days of events titled like "Sam in lab", "Derek @ lab" or "Yaamini in FTR 134" (`scripts/in_lab.py`), and force-pushes `in-lab.json` to the `calendar-data` branch, which the page reads. The browser can't fetch the calendar directly (no CORS), which is why this runs as an Action.

GitHub delays scheduled runs by hours, so raven also starts the workflow every 15 minutes. A cron in sr320's crontab on raven runs `~/lab-status-live/trigger_scrape.sh` (a copy of `scripts/trigger_scrape.sh`), which calls the workflow dispatch API with a fine-grained token stored in `~/.config/lab-status/dispatch_token`. The token is limited to this repo and has only "Actions: Read and write". The workflow's own schedule stays on as a fallback.

To stop it: remove the `trigger_scrape.sh` line from the crontab on raven and revoke the "lab-status dispatch" token under GitHub Settings → Developer settings → Fine-grained tokens.

## raven right now

Raven isn't reachable from outside UW, so it pushes its own numbers. A cron in sr320's crontab on raven runs `~/lab-status-live/raven_live.sh` every 5 minutes (copies of `scripts/raven_live.sh` and `scripts/raven_live.py`). It samples `/proc` for 2 seconds (per-core CPU, load, memory, per-user totals, top processes by name only) and force-pushes `raven-live.json` as the only commit on the `raven-live` branch, using a deploy key (`~/.ssh/lab_status_deploy`) that can write to this repo only. The page reads it through the GitHub contents API, which caches for 60 seconds.

To stop it: remove the `raven_live.sh` line from the crontab on raven and delete the "raven live stats" deploy key in the repo settings.

## Claude

The lab is on a claude.ai Team plan, which has no usage API (Anthropic's usage and analytics APIs need a Console org or Enterprise), so token and spend numbers stay on the admin page at claude.ai/analytics/claude-code. The panel instead counts public commits carrying Claude Code's `Co-Authored-By: Claude` trailer over the last 30 days. `scripts/claude_activity.py` runs in the same Action as the calendar scrape, searches the GitHub scopes in its `SCOPES` list (`org:RobertsLab`, `user:sr320`; add `user:<login>` for others), and writes `claude.json` to the `calendar-data` branch with first names only.

## TTN gateway

Uplink and downlink counts, last uplink, connection time, model and firmware for `sr320-indoor-01` need a TTN API key, so `scripts/ttn_gateway.py` runs in the same 15-minute Action and writes `ttn-gateway.json` to the `calendar-data` branch. It reads the key from the `TTN_API_KEY` repository secret. The key belongs to the gateway and has only "View gateway information" and "View gateway status". Because that branch is public, the script leaves out the gateway's location and IP addresses. Until the secret exists, that step fails without stopping the job, and the panel shows only the Packet Broker fields. The panel warns if the gateway is connected but hasn't heard an uplink in 6 hours (`TTN_QUIET_H`).

To stop it: delete the key under the gateway's API keys in the TTN console and remove the `TTN_API_KEY` secret.

## TTN sensor

`little-dragon-01`, a Dragino LSN50v2-D20 temperature probe in the TTN application `my-tracker-320`, is read by `scripts/ttn_sensor.py` in the same Action. The script asks the application's Storage Integration for the last 24 hours of uplinks (the most TTN's Sandbox keeps) and writes `ttn-sensor.json` to `calendar-data`. Each reading has the decoded payload fields and the RSSI and SNR at each gateway that heard it. Gateway locations and any location fields are left out. It needs:

- the Storage Integration turned on for `my-tracker-320` (Integrations → Storage Integration in the console),
- a payload formatter on the device, so readings arrive as named fields,
- an application API key with only "Read application traffic (uplink and downlink)", saved as the `TTN_APP_API_KEY` repository secret.

The panel shows the latest numeric fields and a 24-hour temperature line. Units are guessed from the field names. It warns if the sensor hasn't reported in 2 hours (`SENSOR_QUIET_H`).

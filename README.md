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
- the CpG O/E Atlas dashboard data (https://sr320.github.io/project-cpg-me/data/dashboard.json): species counts by group, bimodal gene body fits, GO Slim housekeeping vs. inducible support, WGBS validation count, plus `generated` and `git_commit`.
- the Project White Whale dashboard's `data.json` (https://robertslab.github.io/project-white-whale/data.json), rebuilt every 3 hours; the light turns amber if it's more than 8 hours old or reports that branch claims or the gannet mirror couldn't be read.
- the Project Herring Copy dashboard's `data.json` (https://sr320.github.io/project-herring-copy/data.json), rebuilt on every push and every 3 hours: BioProjects and runs, how much of the planned FASTQ is mirrored to gannet, the phase in progress, and the projects already on gannet; the light turns amber if it's more than 12 hours old or reports that the gannet mirror couldn't be read.
- the AREC home page (https://sr320.github.io/AREE-co/), which has no JSON feed: the page reads the count tiles (`.stats .stat`), the "Last updated from commit" line and the Real-study progress table, and shows contrasts harmonized and any still waiting. The light goes grey if the page's layout changes and the counts can't be found.
- Packet Broker's public mapper record for the TTN gateway `sr320-indoor-01` (https://mapper.packetbroker.net/api/v2/gateways/netID=000013,tenantID=ttn,id=sr320-indoor-01): online flag, last update and packet rates per hour. No key is needed because the gateway's status is public in the TTN console. The record also holds the gateway's coordinates, which the page doesn't show. The console stats underneath it come from `ttn-gateway.json` (see "TTN gateway" below).

Thresholds (disk %, staleness hours) are constants near the top of the script.

## Who's in lab

`.github/workflows/in-lab.yml` runs every 15 minutes, at :07, :22, :37 and :52 to stay off the busy quarter-hours. It reads the lab Google Calendar's public iCal feed, keeps the next 7 days of events titled like "Sam in lab", "Derek @ lab" or "Yaamini in FTR 134" (`scripts/in_lab.py`), and force-pushes `in-lab.json` to the `calendar-data` branch, which the page reads. The browser can't fetch the calendar directly (no CORS), which is why this runs as an Action.

GitHub delays scheduled runs by hours, so raven also starts the workflow every 15 minutes. A cron in sr320's crontab on raven runs `~/lab-status-live/trigger_scrape.sh` (a copy of `scripts/trigger_scrape.sh`) at :03, :18, :33 and :48. It force-pushes an empty commit on top of `main` to the `scrape-trigger` branch with the same deploy key `raven_live.sh` uses (`~/.ssh/lab_status_deploy`), and the workflow runs on pushes to that branch. The workflow's own schedule stays on as a fallback.

To stop it: remove the `trigger_scrape.sh` line from the crontab on raven and delete the `scrape-trigger` branch.

## Lab notebooks

`scripts/notebooks.py` runs in the same workflow as the calendar scrape and writes `notebooks.json` to the `calendar-data` branch. It reads the notebook list from the `var notebooks = [...]` array on [robertslab.info/notebooks.html](https://robertslab.info/notebooks.html), so adding someone there adds them to the dashboard. For each notebook it takes the newest item in its RSS/Atom feed, the newest post by that author on genefish.wordpress.com, or (with no feed) the last commit to its repo.

## raven right now

Raven isn't reachable from outside UW, so it pushes its own numbers. A cron in sr320's crontab on raven runs `~/lab-status-live/raven_live.sh` every 5 minutes (copies of `scripts/raven_live.sh` and `scripts/raven_live.py`). It samples `/proc` for 2 seconds (per-core CPU, load, memory, per-user totals, top processes by name only) and force-pushes `raven-live.json` as the only commit on the `raven-live` branch, using a deploy key (`~/.ssh/lab_status_deploy`) that can write to this repo only. The page reads it through the GitHub contents API, which caches for 60 seconds.

To stop it: remove the `raven_live.sh` line from the crontab on raven and delete the "raven live stats" deploy key in the repo settings.

## klone by person

The klone allocation panel comes from the daily `hyakalloc` snapshot in `RobertsLab/resources`, which only shows totals per account and partition. "klone by person" adds per-user detail. Klone needs Duo for SSH, so it pushes the data itself. A `scrontab` job runs `~/lab-status-live/klone_usage.sh` every hour (copies of `scripts/klone_usage.sh` and `scripts/klone_usage.py`). It calls `sacct` once for the last 7 days and `squeue` for the reasons pending jobs are waiting, then force-pushes `klone-usage.json` as the only commit on the `klone-usage` branch. The push uses a deploy key (`~/.ssh/lab_status_klone_deploy`) that can write to this repo only.

For each person the panel shows running and pending jobs, CPUs and memory in use now, CPU-hours over the last 7 days, each split by where they ran (srlab, coenv or ckpt; klone's prefixed account names like `cpu-g2-mem2x-srlab` are folded into these), and how many jobs failed, timed out, ran out of memory, were preempted or were cancelled. Below that is a daily bar chart of lab CPU-hours stacked by the same groups, then a "Jobs now" table of lab members' running and waiting jobs (the first 15, running first): job name, ID, CPUs, partition, how long it has run, and its node or why it's waiting. Job names are cut to the last part of any path (`$HOME/bin/x.sh` → `x.sh`) and to 24 characters; paths and command lines are never recorded, and other labs' jobs aren't listed.

`coenv` is shared with other labs, so only lab members are named: anyone in `KLONE_USERS` (comma-separated NetIDs, set in `klone_usage.sh`) plus anyone who ran a job under `srlab` in the window. Everyone else is one "other coenv" row. `KLONE_ACCOUNTS` (default `srlab,coenv`), `KLONE_LAB_ACCOUNTS` (default `srlab`) and `KLONE_WINDOW_D` (default 7) are also read from the environment. Like `hyakalloc`, it only sees accounts sr320 can query. The light turns amber if the snapshot is more than 3 hours old (`KLONE_USAGE_STALE_H`).

Setup, on klone:

1. `mkdir -p ~/lab-status-live` and copy both scripts there; `chmod +x ~/lab-status-live/klone_usage.sh`.
2. `ssh-keygen -t ed25519 -N "" -f ~/.ssh/lab_status_klone_deploy`, then add the `.pub` as a deploy key named "klone usage" with write access under this repo's Settings → Deploy keys.
3. Fill in `KLONE_USERS` in `klone_usage.sh`, run it once by hand, and check that the `klone-usage` branch appears.
4. `scrontab -e` and add:

   ```
   #SCRON --account=srlab --partition=ckpt --time=00:10:00 --mem=1G
   7 * * * * $HOME/lab-status-live/klone_usage.sh >> $HOME/lab-status-live/klone_usage.log 2>&1
   ```

Until the branch exists, the panel says it isn't set up yet and doesn't raise a warning.

To stop it: remove the line from `scrontab -e` on klone and delete the "klone usage" deploy key in the repo settings.

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

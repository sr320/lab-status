# lab-status

One-page status dashboard for the Roberts Lab: SHORE tank room (Seneye, tankcam, water quality, Puget Sound water, logbook) and computing (raven, gannet, klone).

Live: https://sr320.github.io/lab-status/

Everything is client-side in `index.html`. It pulls JSON at load and every 5 minutes from:

- `RobertsLab/resources` `server-status` branch (`status/external.json`, `status/internal.json`)
- `RobertsLab/shore-line` `seneye-data` branch (`seneye.json`)
- the SHORE site build (`/data/*.json` on ftr210.online or robertslab.github.io/shore-line)
- status.claude.com's public Statuspage API (`/api/v2/summary.json`) for Claude service status
- the AREE results page (https://sr320.github.io/AREE-co/), fetched as HTML and parsed for its stat tiles and the "Real-study progress" table (GitHub Pages allows cross-origin reads). If that page's layout changes, the panel says so instead of guessing.

Thresholds (disk %, staleness hours) are constants near the top of the script.

## Who's in lab

`.github/workflows/in-lab.yml` runs every 15 minutes. It reads the lab Google Calendar's public iCal feed, keeps the next 7 days of events titled like "Sam in lab", "Derek @ lab" or "Yaamini in FTR 134" (`scripts/in_lab.py`), and force-pushes `in-lab.json` to the `calendar-data` branch, which the page reads. The browser can't fetch the calendar directly (no CORS), which is why this runs as an Action.

## raven right now

Raven isn't reachable from outside UW, so it pushes its own numbers. A cron in sr320's crontab on raven runs `~/lab-status-live/raven_live.sh` every 5 minutes (copies of `scripts/raven_live.sh` and `scripts/raven_live.py`). It samples `/proc` for 2 seconds (per-core CPU, load, memory, per-user totals, top processes by name only) and force-pushes `raven-live.json` as the only commit on the `raven-live` branch, using a deploy key (`~/.ssh/lab_status_deploy`) that can write to this repo only. The page reads it through the GitHub contents API, which caches for 60 seconds.

To stop it: remove the `raven_live.sh` line from the crontab on raven and delete the "raven live stats" deploy key in the repo settings.

## Claude

The lab is on a claude.ai Team plan, which has no usage API (Anthropic's usage and analytics APIs need a Console org or Enterprise), so token and spend numbers stay on the admin page at claude.ai/analytics/claude-code. The panel instead counts public commits carrying Claude Code's `Co-Authored-By: Claude` trailer over the last 30 days. `scripts/claude_activity.py` runs in the same Action as the calendar scrape, searches the GitHub scopes in its `SCOPES` list (`org:RobertsLab`, `user:sr320`; add `user:<login>` for others), and writes `claude.json` to the `calendar-data` branch with first names only.

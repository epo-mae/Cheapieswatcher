# Cheapies.nz Keyword Watcher

Watches the [cheapies.nz](https://www.cheapies.nz/) deal feed for new deals
matching keywords you choose (e.g. `protein`, `KFC`, `McDonald's`), and
alerts you only when something **new** shows up — it won't repeat deals
you've already been told about.

It works off the site's built-in RSS feed (`/deals/feed`), which is far more
reliable than scraping search-result pages, and covers every new deal
posted to the site.

## Setup

1. Requires only Python 3 (no packages needed for the core script).
   Optional: `pip install plyer` if you want desktop pop-up notifications.

2. Edit `config.json`:
   ```json
   {
     "keywords": ["protein", "KFC", "McDonald's"],
     "notify": {
       "console": true,
       "desktop": true,
       "email": { "enabled": false, ... }
     }
   }
   ```
   - Add/remove as many keywords as you like — matching is
     case-insensitive and checks both the deal title and description.
   - Set `"desktop": true` for OS notification pop-ups (needs `plyer`).
   - **Discord (recommended)**: set `discord.enabled: true` and paste in a
     webhook URL. To get one: open your Discord server → the channel you
     want alerts in → Edit Channel → Integrations → Webhooks → New Webhook
     → Copy Webhook URL. Each new deal shows up as an embed with the title
     and a link straight to the deal. `username` just controls the name
     the bot posts under.
   - Email is still supported as a fallback — set `email.enabled: true`
     and fill in your SMTP details. For Gmail, use an
     [app password](https://myaccount.google.com/apppasswords), not your
     normal password.

3. Run it:
   ```bash
   python3 cheapies_watcher.py
   ```
   First run will report every current match (since nothing's been "seen"
   yet) and save that to `state.json`. From then on, only genuinely new
   matches will trigger an alert.

   To just preview everything currently on the site matching your
   keywords without touching the saved state, run:
   ```bash
   python3 cheapies_watcher.py --list-only
   ```

## Going deeper: scanning multiple pages, not just the newest deals

By default the script checks the site's **RSS feed**, which always contains
the most recently posted deals — new deals always show up there first, so a
daily run never "misses a page," it just needs to run at least as often as
the feed refreshes.

If you also want to sweep further back through the site's **archive**
(e.g. the very first time you set this up, to catch keyword matches posted
before you started watching), run a deep scan instead:

```bash
python3 cheapies_watcher.py --deep-scan --max-pages 20
```

This walks the site's paginated deal listing (`/?page=0`, `/?page=1`, ...)
page by page, up to `--max-pages` pages (default 20), and stops early once
it reaches deals it's already recorded — so a first run does a full sweep,
and subsequent deep-scans are quick. There's a small `--delay` (default 1.5s)
between page requests so it doesn't hammer the server.

**Ping even when nothing new is found:** since a deep scan is slow, the
script pings Discord with a short "ran, checked N deals, nothing new"
message by default whenever a deep scan finds no new matches — so you know
it actually ran rather than silently doing nothing. Regular feed runs stay
quiet on empty results by default (you'd get spammed on every hourly cron
run otherwise). You can override this in `config.json`:
```json
"discord": {
  "always_notify": true   // or false — force the behaviour either way,
                           // for both deep-scan and regular runs
}
```

**Most recent deal per keyword, even on empty runs:** whenever there are no
*new* matches, the script also prints (and, if the ping above fires,
includes in the Discord message) the most recent *currently listed* deal
for each keyword — so an empty run still tells you what's out there right
now, not just "nothing changed." Note: on a plain feed run this is only as
complete as the RSS feed itself (recent site-wide deals), so a keyword with
no recent activity may show "no current match on this page" even though an
older matching deal exists further back in the archive — run `--deep-scan`
for full coverage.

Recommended pattern:
- Run `--deep-scan` once (or occasionally) for thorough historical coverage.
- Run the plain (feed-based) mode daily/hourly for fast ongoing alerts.

Note: this deep-scan parser is a lightweight, dependency-free scraper keyed
off the site's deal-permalink URLs (`/node/<id>`). If cheapies.nz changes
its page layout significantly, the parsing may need a small tweak — if a
deep scan run ever returns 0 items or garbled titles, let me know and I can
adjust it.

## Scheduling it to run automatically

### macOS / Linux (cron)

Run daily at 8am:
```bash
crontab -e
```
Add:
```
0 8 * * * /usr/bin/python3 /path/to/cheapies_watcher/cheapies_watcher.py >> /path/to/cheapies_watcher/log.txt 2>&1
```

### Windows (Task Scheduler)

1. Open Task Scheduler → Create Basic Task.
2. Trigger: Daily, pick a time.
3. Action: "Start a program" →
   - Program: `python`
   - Arguments: `cheapies_watcher.py`
   - Start in: the folder containing the script.

You can run it more often than daily (e.g. every hour) if you want faster
alerts — just adjust the schedule.

## Files

- `cheapies_watcher.py` — the script.
- `config.json` — your keywords and notification settings.
- `state.json` — auto-created; tracks which matching deals you've already
  been alerted about, so re-runs don't repeat old news.

## Notes

- If cheapies.nz changes its feed URL or format, update `feed_url` in
  `config.json` accordingly.
- `state.json` keeps the last 1000 matched deal IDs, which is more than
  enough headroom given the site's posting volume.
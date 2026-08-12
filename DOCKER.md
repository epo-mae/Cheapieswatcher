# Running cheapies_watcher.py 24/7 with Docker

## 1. Regenerate your Discord webhook (do this once, now)

Your current `config.json` has a live webhook URL in it. Before pushing
anything to GitHub, regenerate it: Discord → your server → the channel →
Edit Channel → Integrations → Webhooks → delete the old one → New Webhook
→ Copy Webhook URL. Use the new one going forward.

## 2. Add these files to your repo

Copy `Dockerfile`, `entrypoint.sh`, `docker-compose.yml`,
`config.example.json`, and `.gitignore` into the root of
`Cheapieswatcher`, alongside your existing `cheapies_watcher.py` and
`README.md`. Do **not** add your real `config.json` or `state.json` —
`.gitignore` already excludes them.

Then, on the machine that will run it (a home server, a Raspberry Pi, a
VPS — anything with Docker):

```bash
git clone https://github.com/epo-mae/Cheapieswatcher.git
cd Cheapieswatcher
mkdir -p data
cp config.example.json data/config.json
# edit data/config.json: paste in your real (new) webhook URL and keywords
nano data/config.json
```

`data/state.json` doesn't need to exist yet — the container creates it on
first run.

## 3. Build and run

```bash
docker compose up -d --build
```

That's it — it's now running continuously in the background and will
restart automatically if the machine reboots (`restart: unless-stopped`
in `docker-compose.yml`).

Check on it:
```bash
docker compose logs -f
```

Stop it:
```bash
docker compose down
```

## 4. How the schedule works

Instead of cron, the container runs a simple loop (`entrypoint.sh`): run
the watcher, sleep for `INTERVAL_SECONDS`, repeat — forever, as long as
the container is up. Default is hourly (`3600`). Change it in
`docker-compose.yml`:

```yaml
environment:
  - INTERVAL_SECONDS=1800   # every 30 minutes
```

then `docker compose up -d --build` again to apply it.

If `RUN_DEEP_SCAN_ON_FIRST_RUN=true` (the default in the compose file),
the very first time it runs — when `data/state.json` doesn't exist yet —
it does one `--deep-scan` for full historical coverage before switching
to fast RSS-feed polling from then on, matching the workflow your README
already recommends.

## 5. Updating later

When you change `cheapies_watcher.py` or `config.example.json` in the
repo:

```bash
git pull
docker compose up -d --build
```

Your `data/config.json` and `data/state.json` are untouched by this —
they live outside the image.

## 6. Notes specific to running in Docker

- `desktop` notifications (`plyer`) won't do anything in a container —
  there's no desktop to pop a notification on. `config.example.json`
  already sets `"desktop": false`. Discord is the right channel for a
  headless setup like this.
- If you'd rather build directly from GitHub without cloning first, once
  it's pushed you can run:
  ```bash
  docker build -t cheapies-watcher https://github.com/epo-mae/Cheapieswatcher.git
  ```
  You'd still need to supply `config.json`/`state.json` via a volume mount
  at runtime the same way, e.g.:
  ```bash
  docker run -d --restart unless-stopped \
    -v $(pwd)/data/config.json:/app/data/config.json:ro \
    -v $(pwd)/data/state.json:/app/data/state.json \
    -e INTERVAL_SECONDS=3600 \
    cheapies-watcher
  ```

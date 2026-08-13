#!/usr/bin/env bash
# Runs cheapies_watcher.py on a loop, forever, inside the container.
#
# Env vars (all optional, set via docker-compose.yml or `docker run -e`):
#   INTERVAL_SECONDS   Seconds between runs (default 3600 = hourly)
#   ALWAYS_DEEP_SCAN   "true" to run --deep-scan on every single run, not
#                       just the first one (default false = feed-only after
#                       the first run). Slower per run, but checks multiple
#                       pages every time instead of just the newest deals.
#   MAX_PAGES          Max pages per deep scan (default 20). Deep scans stop
#                       early once they hit already-seen deals, so repeat
#                       scans are quick even with a high max-pages.

set -euo pipefail

CONFIG=/app/data/config.json
STATE=/app/data/state.json

if [ ! -f "$CONFIG" ]; then
  echo "ERROR: $CONFIG not found. Mount your real config.json into /app/data/ (see docker-compose.yml)."
  exit 1
fi

if [ "${ALWAYS_DEEP_SCAN:-false}" != "true" ] && [ ! -f "$STATE" ]; then
  echo "[$(date -Is)] No state.json yet — running one-off --deep-scan (max-pages=${MAX_PAGES:-20}) for historical coverage..."
  python3 cheapies_watcher.py --config "$CONFIG" --state "$STATE" --deep-scan --max-pages "${MAX_PAGES:-20}" || true
fi

echo "[$(date -Is)] Starting watcher loop, checking every ${INTERVAL_SECONDS:-3600}s (deep-scan every run: ${ALWAYS_DEEP_SCAN:-false})."

while true; do
  echo "[$(date -Is)] Running watcher..."
  if [ "${ALWAYS_DEEP_SCAN:-false}" = "true" ]; then
    python3 cheapies_watcher.py --config "$CONFIG" --state "$STATE" --deep-scan --max-pages "${MAX_PAGES:-20}" || echo "[$(date -Is)] Run failed, will retry next interval."
  else
    python3 cheapies_watcher.py --config "$CONFIG" --state "$STATE" || echo "[$(date -Is)] Run failed, will retry next interval."
  fi
  sleep "${INTERVAL_SECONDS:-3600}"
done

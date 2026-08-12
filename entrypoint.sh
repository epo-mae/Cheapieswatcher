#!/usr/bin/env bash
# Runs cheapies_watcher.py on a loop, forever, inside the container.
#
# Env vars (all optional, set via docker-compose.yml or `docker run -e`):
#   INTERVAL_SECONDS            Seconds between runs (default 3600 = hourly)
#   RUN_DEEP_SCAN_ON_FIRST_RUN  "true" to do one --deep-scan before settling
#                                into normal feed-polling (default false)
#   MAX_PAGES                   Max pages for that initial deep scan (default 20)

set -euo pipefail

CONFIG=/app/data/config.json
STATE=/app/data/state.json

if [ ! -f "$CONFIG" ]; then
  echo "ERROR: $CONFIG not found. Mount your real config.json into /app/data/ (see docker-compose.yml)."
  exit 1
fi

if [ "${RUN_DEEP_SCAN_ON_FIRST_RUN:-false}" = "true" ] && [ ! -f "$STATE" ]; then
  echo "[$(date -Is)] No state.json yet — running one-off --deep-scan (max-pages=${MAX_PAGES:-20}) for historical coverage..."
  python3 cheapies_watcher.py --config "$CONFIG" --state "$STATE" --deep-scan --max-pages "${MAX_PAGES:-20}" || true
fi

echo "[$(date -Is)] Starting watcher loop, checking every ${INTERVAL_SECONDS:-3600}s."

while true; do
  echo "[$(date -Is)] Running watcher..."
  python3 cheapies_watcher.py --config "$CONFIG" --state "$STATE" || echo "[$(date -Is)] Run failed, will retry next interval."
  sleep "${INTERVAL_SECONDS:-3600}"
done

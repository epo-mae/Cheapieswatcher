FROM python:3.12-slim

# No third-party packages are required for the core script.
# (plyer / desktop notifications are pointless inside a container anyway,
# since there's no desktop to pop a notification on — Discord is the way.)

WORKDIR /app

COPY cheapies_watcher.py .
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

# config.json and state.json are NOT copied in here — they're mounted at
# runtime via docker-compose (or `docker run -v ...`) so your webhook URL
# never ends up baked into the image, and state.json persists across
# container restarts/rebuilds.

ENV INTERVAL_SECONDS=3600
ENV RUN_DEEP_SCAN_ON_FIRST_RUN=false
ENV MAX_PAGES=20

ENTRYPOINT ["./entrypoint.sh"]

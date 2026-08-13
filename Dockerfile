FROM python:3.12-slim

# No third-party packages are required for the core script itself.
# (plyer / desktop notifications are pointless inside a container anyway,
# since there's no desktop to pop a notification on — Discord is the way.)
# tzdata is installed so Python's zoneinfo can correctly convert to NZT
# (including daylight saving transitions) for message timestamps.
RUN pip install --no-cache-dir --break-system-packages tzdata

WORKDIR /app

COPY cheapies_watcher.py .
COPY entrypoint.sh .
# Windows checkouts can save this with CRLF line endings, which breaks the
# shebang (`env: 'bash\r': No such file or directory`). Strip any \r just
# in case, regardless of how it was checked out.
RUN sed -i 's/\r$//' entrypoint.sh && chmod +x entrypoint.sh

# config.json and state.json are NOT copied in here — they're mounted at
# runtime via docker-compose (or `docker run -v ...`) so your webhook URL
# never ends up baked into the image, and state.json persists across
# container restarts/rebuilds.

ENV INTERVAL_SECONDS=3600
ENV ALWAYS_DEEP_SCAN=false
ENV MAX_PAGES=20

ENTRYPOINT ["./entrypoint.sh"]
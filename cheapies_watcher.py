#!/usr/bin/env python3
"""
cheapies_watcher.py

Watches the ChoiceCheapies (cheapies.nz) deal feed for new deals that match
a list of keywords you configure (e.g. "protein", "KFC", "McDonald's").

Each time it runs it:
  1. Downloads the site's RSS feed of deals.
  2. Filters items whose title/description contain any of your keywords.
  3. Compares against the matches it saw last time (stored in state.json).
  4. Alerts you (console / desktop notification / email) about anything NEW.

Run it manually, or schedule it (cron / Task Scheduler) to run e.g. once a
day or once an hour -- see README.md for setup instructions.

No third-party packages are required. Desktop notifications will use
'plyer' if it's installed, otherwise that channel is silently skipped.
"""

import argparse
import json
import re
import smtplib
import sys
import urllib.request
import xml.etree.ElementTree as ET
from email.mime.text import MIMEText
from html import unescape
from pathlib import Path

DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.json"
DEFAULT_STATE_PATH = Path(__file__).parent / "state.json"
USER_AGENT = "Mozilla/5.0 (compatible; CheapiesKeywordWatcher/1.0)"

# Matches deal-title links in the listing pages, e.g.
#   <a href="https://www.cheapies.nz/node/56744">Some Deal Title</a>
# (also matches relative /node/56744 hrefs, just in case)
NODE_LINK_RE = re.compile(
    r'<a[^>]+href="(?:https://www\.cheapies\.nz)?/node/(\d+)"[^>]*>([^<]{5,300})</a>'
)


# --------------------------------------------------------------------------
# Config / state
# --------------------------------------------------------------------------

def load_config(path: Path) -> dict:
    if not path.exists():
        sys.exit(f"Config file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_state(path: Path) -> dict:
    if not path.exists():
        return {"seen_ids": []}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(path: Path, state: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


# --------------------------------------------------------------------------
# Feed fetching / parsing
# --------------------------------------------------------------------------

def fetch_feed(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return unescape(re.sub(r"\s+", " ", text)).strip()


def parse_items(raw_xml: bytes) -> list:
    """Parse an RSS 2.0 feed into a list of dicts: id, title, link, description."""
    root = ET.fromstring(raw_xml)
    items = []
    for item in root.iter("item"):
        title = item.findtext("title", default="").strip()
        link = item.findtext("link", default="").strip()
        guid = item.findtext("guid", default="").strip() or link
        description = strip_html(item.findtext("description", default=""))
        pub_date = item.findtext("pubDate", default="").strip()
        items.append(
            {
                "id": guid,
                "title": unescape(title),
                "link": link,
                "description": description,
                "pub_date": pub_date,
            }
        )
    return items


# --------------------------------------------------------------------------
# Paginated listing scraping (for deep/historical scans)
# --------------------------------------------------------------------------

def fetch_page(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def parse_listing_page(html: str) -> list:
    """
    Best-effort parse of a cheapies.nz deal-listing page (front page or
    /?page=N). Finds each deal via its title link (/node/<id>), and takes
    the text between one deal's title link and the next as that deal's
    'description' (covers the summary text, store name, category, etc.
    the listing page shows for each deal).

    This is a lightweight, dependency-free scraper. It is deliberately
    generic (keyed off /node/<id> links, which are stable identifiers on
    this site) rather than tied to exact CSS classes, since front-end
    markup is more likely to shift over time than the URL scheme.
    """
    matches = list(NODE_LINK_RE.finditer(html))
    items = []
    seen_this_page = set()
    for i, m in enumerate(matches):
        node_id = m.group(1)
        if node_id in seen_this_page:
            continue  # a node can be linked twice (image + title); keep first
        seen_this_page.add(node_id)

        title = unescape(m.group(2)).strip()
        block_end = matches[i + 1].start() if i + 1 < len(matches) else min(
            m.end() + 2000, len(html)
        )
        block = html[m.end():block_end]
        description = strip_html(block)[:600]

        items.append(
            {
                "id": f"node/{node_id}",
                "title": title,
                "link": f"https://www.cheapies.nz/node/{node_id}",
                "description": description,
            }
        )
    return items


def deep_scan(base_url: str, max_pages: int, delay_seconds: float, seen_ids: set):
    """
    Walk /?page=0, /?page=1, ... up to max_pages, collecting deal items.
    Stops early if a page contains zero not-already-seen items (i.e. we've
    caught up to deals we already know about), which keeps a routine deep
    scan fast while still doing a full walk the very first time it's run.
    """
    import time

    all_items = []
    for page_num in range(max_pages):
        url = base_url if page_num == 0 else f"{base_url}?page={page_num}"
        try:
            html = fetch_page(url)
        except Exception as e:
            print(f"  Warning: failed to fetch page {page_num} ({url}): {e}")
            break

        page_items = parse_listing_page(html)
        if not page_items:
            break  # no more deals found; probably past the last page

        new_on_page = [it for it in page_items if it["id"] not in seen_ids]
        all_items.extend(page_items)
        print(f"  Page {page_num}: {len(page_items)} deals, {len(new_on_page)} not previously seen")

        if not new_on_page and page_num > 0:
            break  # caught up to already-seen territory; no need to go deeper

        if page_num + 1 < max_pages:
            time.sleep(delay_seconds)  # be polite to the server

    return all_items


# --------------------------------------------------------------------------
# Keyword matching
# --------------------------------------------------------------------------

def matching_keywords(item: dict, keywords: list) -> list:
    haystack = f"{item['title']} {item['description']}".lower()
    return [kw for kw in keywords if kw.lower() in haystack]


def most_recent_per_keyword(items: list, keywords: list) -> dict:
    """
    For each keyword, return the first (i.e. most recent -- both the RSS
    feed and the listing pages are newest-first) item whose title/
    description contains it. Keywords with no current match are omitted.
    """
    latest = {}
    for item in items:
        for kw in matching_keywords(item, keywords):
            if kw not in latest:
                latest[kw] = item
        if len(latest) == len(keywords):
            break  # found a hit for every keyword, no need to scan further
    return latest


# --------------------------------------------------------------------------
# Alerting
# --------------------------------------------------------------------------

def alert_console(new_matches: list) -> None:
    print(f"\n=== {len(new_matches)} new deal(s) matching your keywords ===")
    for item, kws in new_matches:
        print(f"- [{', '.join(kws)}] {item['title']}")
        print(f"    {item['link']}")


def print_latest_per_keyword(latest: dict, keywords: list) -> None:
    print("\n=== Most recent current deal per keyword ===")
    for kw in keywords:
        item = latest.get(kw)
        if item:
            print(f"- [{kw}] {item['title']}")
            print(f"    {item['link']}")
        else:
            print(f"- [{kw}] (no current match on this page)")


def alert_desktop(new_matches: list) -> None:
    try:
        from plyer import notification
    except ImportError:
        return  # optional dependency not installed; skip silently
    for item, kws in new_matches[:5]:  # avoid spamming dozens of popups
        notification.notify(
            title=f"Cheapies deal: {', '.join(kws)}",
            message=item["title"][:200],
            timeout=10,
        )


def alert_discord(new_matches: list, discord_cfg: dict) -> None:
    if not discord_cfg.get("enabled"):
        return
    webhook_url = discord_cfg.get("webhook_url")
    if not webhook_url:
        print("  Warning: Discord notify enabled but no webhook_url set in config.json")
        return

    # Discord embeds are capped at 25 per message and have field/description
    # limits, so batch in chunks of 10 to stay well within those and keep
    # each message readable.
    chunk_size = 10
    for i in range(0, len(new_matches), chunk_size):
        chunk = new_matches[i:i + chunk_size]
        embeds = []
        for item, kws in chunk:
            embeds.append(
                {
                    "title": item["title"][:256],
                    "url": item["link"],
                    "description": f"Matched: {', '.join(kws)}",
                }
            )
        payload = {
            "username": discord_cfg.get("username", "Cheapies Watcher"),
            "content": (
                f"**{len(new_matches)} new deal(s) matching your keywords**"
                if i == 0
                else None
            ),
            "embeds": embeds,
        }
        payload = {k: v for k, v in payload.items() if v is not None}

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp.read()
        except Exception as e:
            print(f"  Warning: Discord webhook post failed: {e}")


def alert_discord_heartbeat(discord_cfg: dict, scan_kind: str, items_checked: int, latest: dict = None) -> None:
    """Send a plain 'ran, found nothing new' ping to Discord, optionally
    followed by an embed showing the most recent current deal per keyword."""
    if not discord_cfg.get("enabled"):
        return
    webhook_url = discord_cfg.get("webhook_url")
    if not webhook_url:
        return

    content = f"✅ {scan_kind} ran, checked {items_checked} deal(s), no new keyword matches."
    payload = {
        "username": discord_cfg.get("username", "Cheapies Watcher"),
        "content": content,
    }

    if latest:
        embeds = []
        for kw, item in latest.items():
            embeds.append(
                {
                    "title": item["title"][:256],
                    "url": item["link"],
                    "description": f"Most recent for: {kw}",
                }
            )
        # Discord caps embeds per message at 10; unlikely to hit that with
        # a realistic keyword list, but chunk just in case.
        payload["embeds"] = embeds[:10]

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
    except Exception as e:
        print(f"  Warning: Discord heartbeat post failed: {e}")


def alert_email(new_matches: list, email_cfg: dict) -> None:
    if not email_cfg.get("enabled"):
        return
    lines = []
    for item, kws in new_matches:
        lines.append(f"[{', '.join(kws)}] {item['title']}\n{item['link']}\n")
    body = "\n".join(lines)

    msg = MIMEText(body)
    msg["Subject"] = f"Cheapies.nz: {len(new_matches)} new matching deal(s)"
    msg["From"] = email_cfg["from_addr"]
    msg["To"] = email_cfg["to_addr"]

    with smtplib.SMTP(email_cfg["smtp_host"], email_cfg["smtp_port"]) as server:
        server.starttls()
        server.login(email_cfg["username"], email_cfg["password"])
        server.sendmail(email_cfg["from_addr"], [email_cfg["to_addr"]], msg.as_string())


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Watch cheapies.nz for keyword matches.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="Just print all current matches (ignoring seen-state), don't update state.",
    )
    parser.add_argument(
        "--deep-scan",
        action="store_true",
        help="Walk multiple listing pages (not just the RSS feed) -- use this for a "
        "thorough historical sweep, e.g. the first time you run the tool.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=20,
        help="Max listing pages to walk in --deep-scan mode (default: 20).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.5,
        help="Seconds to wait between page requests in --deep-scan mode (default: 1.5).",
    )
    parser.add_argument(
        "--test-discord",
        action="store_true",
        help="Send a test message + a fake 'new deal' embed to your configured Discord "
        "webhook, then exit immediately -- doesn't touch the feed or state.json. Use "
        "this to check your webhook_url is correct and see what alerts look like.",
    )
    args = parser.parse_args()

    config = load_config(args.config)

    if args.test_discord:
        discord_cfg = config.get("notify", {}).get("discord", {})
        if not discord_cfg.get("enabled"):
            sys.exit("discord.enabled is false in config.json -- set it to true first.")
        if not discord_cfg.get("webhook_url") or "your-webhook" in discord_cfg["webhook_url"]:
            sys.exit("discord.webhook_url in config.json still looks like the placeholder "
                      "-- paste in your real webhook URL first.")

        print("Sending heartbeat-style test message...")
        alert_discord_heartbeat(discord_cfg, "Test run", 0)

        print("Sending a fake match embed...")
        fake_item = {
            "title": "TEST: 50% off Fake Widget (this is not a real deal)",
            "link": "https://www.cheapies.nz/",
            "description": "This is a test alert from cheapies_watcher.py --test-discord.",
        }
        alert_discord([(fake_item, ["test"])], discord_cfg)

        print("Sent. Check your Discord channel for two messages.")
        return

    keywords = config.get("keywords", [])
    if not keywords:
        sys.exit("No keywords configured in config.json -> 'keywords' list.")

    state = load_state(args.state)
    seen_ids = set(state.get("seen_ids", []))

    if args.deep_scan:
        site_url = config.get("site_url", "https://www.cheapies.nz/")
        print(f"Deep-scanning up to {args.max_pages} listing page(s)...")
        items = deep_scan(site_url, args.max_pages, args.delay, seen_ids)
    else:
        raw = fetch_feed(config["feed_url"])
        items = parse_items(raw)

    all_matches = []
    for item in items:
        kws = matching_keywords(item, keywords)
        if kws:
            all_matches.append((item, kws))

    if args.list_only:
        alert_console(all_matches)
        return

    new_matches = [(item, kws) for item, kws in all_matches if item["id"] not in seen_ids]

    if new_matches:
        if config.get("notify", {}).get("console", True):
            alert_console(new_matches)
        if config.get("notify", {}).get("desktop", False):
            alert_desktop(new_matches)
        discord_cfg = config.get("notify", {}).get("discord", {})
        alert_discord(new_matches, discord_cfg)
        email_cfg = config.get("notify", {}).get("email", {})
        alert_email(new_matches, email_cfg)
    else:
        print("No new keyword matches this run.")
        latest = most_recent_per_keyword(items, keywords)
        print_latest_per_keyword(latest, keywords)

        discord_cfg = config.get("notify", {}).get("discord", {})
        # Default: always ping on deep-scans (they're slow, so a confirmation
        # is useful), but stay quiet on routine feed runs unless the user has
        # explicitly opted in via "always_notify": true.
        default_always = args.deep_scan
        if discord_cfg.get("always_notify", default_always):
            scan_kind = "Deep scan" if args.deep_scan else "Feed check"
            alert_discord_heartbeat(discord_cfg, scan_kind, len(items), latest)

    # Update state: keep the ids we currently matched on (bounded to last 1000)
    updated_seen = list(seen_ids | {item["id"] for item, _ in all_matches})
    state["seen_ids"] = updated_seen[-1000:]
    save_state(args.state, state)


if __name__ == "__main__":
    main()
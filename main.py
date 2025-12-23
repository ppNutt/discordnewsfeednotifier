import os
import json
import time
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    print("Error: 'requests' module not found. Install it with: pip install requests")
    exit(1)

try:
    from dotenv import load_dotenv
except ImportError:
    print("Error: 'python-dotenv' module not found. Install it with: pip install python-dotenv")
    exit(1)
try:
    import feedparser
except ImportError:
    print("Error: 'feedparser' module not found. Install it with: pip install feedparser")
    exit(1)

import re
# Load environment variables
load_dotenv()

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
FEED_URL = os.getenv("FEED_URL")

# File to store the last seen tweet ID
LAST_ID_FILE = "last_id.json"
# Default interval in seconds; can be overridden by env var CHECK_INTERVAL
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "60"))


def load_last_tweet_id():
    """Load the last seen tweet ID from JSON file."""
    if Path(LAST_ID_FILE).exists():
        with open(LAST_ID_FILE, "r") as f:
            data = json.load(f)
            return data.get("last_id")
    return None


def save_last_tweet_id(tweet_id):
    """Save the tweet ID to JSON file."""
    with open(LAST_ID_FILE, "w") as f:
        json.dump({"last_id": tweet_id}, f)


def fetch_latest_feed_entry(feed_url):
    """Fetch the latest entry from an RSS/Atom feed using feedparser."""
    if not feed_url:
        print("❌ FEED_URL is not configured. Set FEED_URL in your .env file.")
        return None

    try:
        feed = feedparser.parse(feed_url)
    except Exception as e:
        print(f"❌ Error parsing feed: {e}")
        return None

    if getattr(feed, "bozo", False):
        # bozo indicates a problem parsing the feed; still may contain entries
        print(f"⚠️  Feed parser reported an issue: {getattr(feed, 'bozo_exception', '')}")

    entries = feed.entries if hasattr(feed, "entries") else []
    if not entries:
        print("⚠️  No entries found in feed")
        return None

    entry = entries[0]

    # Build a stable entry id
    entry_id = entry.get("id") or entry.get("guid") or entry.get("link") or (entry.get("title", "") + entry.get("published", ""))

    # Published timestamp
    published = None
    if entry.get("published_parsed"):
        published = datetime.fromtimestamp(time.mktime(entry.published_parsed))
    elif entry.get("published"):
        try:
            published = datetime.fromisoformat(entry.get("published"))
        except Exception:
            published = None

    # Extract summary/content and strip HTML tags. Prefer common fields in this order:
    # summary -> description -> content[0].value
    raw_summary = entry.get("summary") or entry.get("description")
    if not raw_summary and entry.get("content"):
        try:
            raw_summary = entry.content[0].get("value")
        except Exception:
            raw_summary = raw_summary

    raw_summary = raw_summary or ""
    # Remove HTML tags for Discord description
    summary_text = re.sub(r"<[^>]+>", "", raw_summary).strip()

    # If feed provides no summary/description, try fetching the article page and
    # extract meta description or the first paragraph as a fallback.
    if not summary_text and entry.get("link"):
        try:
            summary_text = fetch_article_description(entry.get("link")) or ""
        except Exception:
            summary_text = summary_text

    # Extract media (images) from media_content, enclosures, and links
    media_urls = []
    if entry.get("media_content"):
        for m in entry.media_content:
            if m.get("url"):
                media_urls.append(m["url"])

    for link in entry.get("links", []):
        href = link.get("href")
        if not href:
            continue
        rel = link.get("rel", "")
        ltype = link.get("type", "")
        if rel == "enclosure":
            media_urls.append(href)
        elif ltype.startswith("image"):
            media_urls.append(href)

    # Extract author information (prefer author, then author_detail, then authors list)
    author_name = None
    if entry.get("author"):
        author_name = entry.get("author")
    elif entry.get("author_detail") and isinstance(entry.get("author_detail"), dict):
        author_name = entry.get("author_detail").get("name")
    elif entry.get("authors") and isinstance(entry.get("authors"), list) and entry.get("authors"):
        first = entry.get("authors")[0]
        if isinstance(first, dict):
            author_name = first.get("name")
        else:
            author_name = str(first)

    return {
        "id": entry_id,
        "title": entry.get("title", ""),
        "link": entry.get("link", ""),
        "published": published,
        "summary": summary_text,
        "author": author_name,
        "media_urls": media_urls,
    }


def fetch_article_description(url):
    """Fetch article HTML and try to extract a useful description.

    Prefer <meta property="og:description">, then <meta name="description">,
    then first <p> inside the <article> or the whole page as a last resort.
    """
    if not url:
        return None

    headers = {"User-Agent": "FeedMonitor/1.0 (+https://github.com)"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return None
        html = resp.text
    except Exception:
        return None

    # Try og:description or meta description
    m = re.search(r"<meta[^>]+property=[\'\"]og:description[\'\"][^>]+content=[\'\"](.*?)[\'\"]", html, flags=re.I | re.S)
    if not m:
        m = re.search(r"<meta[^>]+name=[\'\"]description[\'\"][^>]+content=[\'\"](.*?)[\'\"]", html, flags=re.I | re.S)
    if m:
        desc = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        return desc

    # Try first <article> ... </article> and get first <p>
    a = re.search(r"<article[^>]*>(.*?)</article>", html, flags=re.I | re.S)
    if a:
        p = re.search(r"<p[^>]*>(.*?)</p>", a.group(1), flags=re.I | re.S)
        if p:
            return re.sub(r"<[^>]+>", "", p.group(1)).strip()

    # Last resort: first <p> on the page
    p = re.search(r"<p[^>]*>(.*?)</p>", html, flags=re.I | re.S)
    if p:
        return re.sub(r"<[^>]+>", "", p.group(1)).strip()

    return None


def format_discord_message(entry_data):
    """Format feed entry data into a Discord embed message."""
    title = entry_data.get("title")
    link = entry_data.get("link")
    published = entry_data.get("published")
    summary = entry_data.get("summary")
    media_urls = entry_data.get("media_urls", [])

    timestamp = published.isoformat() if published else None

    # Truncate description to Discord embed limits (2048 chars)
    description = (summary or "(No description available)").strip()
    if len(description) > 2000:
        description = description[:1997].rsplit(" ", 1)[0] + "..."

    embed = {
        "title": title or "New feed entry",
        "url": link,
        "description": description,
        "color": 4886754,  # a neutral blue
        "timestamp": timestamp,
        "footer": {"text": "Anti-Matrix Feed"},
    }

    # Attach author if provided by the feed
    author_name = entry_data.get("author")
    if author_name:
        embed["author"] = {"name": author_name}

    embeds = [embed]

    # If there are media images, add image to the first embed and additional embeds for others
    if media_urls:
        # Attach first image to main embed
        embed["image"] = {"url": media_urls[0]}
        # Additional images as separate embeds (up to 3 more)
        for url in media_urls[1:4]:
            embeds.append({"image": {"url": url}})

    return {"embeds": embeds}


def send_to_discord(message_data):
    """Send the formatted message to Discord webhook."""
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=message_data)
        if response.status_code == 204:
            print("✅ Message sent to Discord successfully")
            return True
        else:
            print(f"❌ Failed to send to Discord: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error sending to Discord: {e}")
        return False


def initialize_client():
    """No-op placeholder for compatibility (RSS feed doesn't need a client)."""
    return None


def main():
    """Main monitoring loop."""
    print("🚀 Starting Feed Monitor Bot...")
    print(f"📍 Monitoring feed: {FEED_URL}")
    print(f"⏱️  Check interval: {CHECK_INTERVAL} seconds")
    print("-" * 50)

    if not FEED_URL:
        print("❌ FEED_URL not configured. Please set FEED_URL in your .env file and restart.")
        return

    last_id = load_last_tweet_id()
    if last_id:
        print(f"📝 Last seen tweet ID: {last_id}")
    else:
        print("📝 No previous tweet ID found. Starting fresh.")

    print("-" * 50)
    print("🔄 Starting monitoring loop...\n")

    try:
        while True:
            # Fetch the latest feed entry
            result = fetch_latest_feed_entry(FEED_URL)
            if result is None:
                time.sleep(CHECK_INTERVAL)
                continue

            entry_id = result.get("id")

            # Check if it's a new entry
            if last_id is None or entry_id != last_id:
                print(f"🆕 New feed entry detected! (ID: {entry_id})")

                # Format and send to Discord
                message = format_discord_message(result)
                if send_to_discord(message):
                    # Save the entry ID
                    save_last_tweet_id(entry_id)
                    last_id = entry_id
                    print(f"💾 Saved entry ID: {last_id}\n")
                else:
                    print("⚠️  Discord message failed, retrying next cycle\n")
            else:
                print(f"⏸️  No new entries. Last ID: {last_id}")

            # Wait before checking again
            time.sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:
        print("\n⛔ Monitor stopped by user")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")


if __name__ == "__main__":
    main()

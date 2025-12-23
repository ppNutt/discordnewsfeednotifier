# Discord Feed Monitor Bot

A Python bot that monitors a specified RSS/Atom feed (e.g., Coindesk) and sends notifications to Discord whenever a new post is published.

## Features

✅ Monitors an RSS/Atom feed (no scraping)  
✅ Uses feedparser to parse feed entries  
✅ Extracts title, publication date, summary, and media URLs  
✅ Compares entry IDs to avoid duplicate notifications  
✅ Saves last seen entry ID in JSON file  
✅ Sends rich Discord embeds with post content  
✅ Continuous monitoring loop (default 60-second interval)  

## Setup

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure the Feed & Discord Webhook

#### Feed URL
Provide the RSS/Atom feed URL you want to monitor (e.g., `https://www.coindesk.com/arc/outboundfeeds/rss/`).

#### Discord Webhook URL
1. Go to your Discord server settings
2. Navigate to "Integrations" > "Webhooks"
3. Click "New Webhook"
4. Name it and select the channel
5. Click "Copy Webhook URL"

### 3. Configure Environment Variables
1. Copy `.env.example` to `.env`:
   ```bash
   copy .env.example .env
   ```
2. Edit `.env` with your configuration:
   ```
   FEED_URL=https://www.coindesk.com/arc/outboundfeeds/rss/
   DISCORD_WEBHOOK_URL=your_discord_webhook_url_here
   CHECK_INTERVAL=60  # optional
   ```

## Running the Bot

```bash
python main.py
```

The bot will:
- Start monitoring the specified feed
- Check for new posts every CHECK_INTERVAL seconds (default 60)
- Send a Discord embed when a new post is detected
- Save the entry ID to avoid duplicate notifications
- Continue running indefinitely until stopped (Ctrl+C)

## File Structure

```
├── main.py              # Main bot script
├── send_test_embed.py   # Helper to post the latest feed entry as an embed once
├── requirements.txt     # Python dependencies
├── .env.example         # Environment variable template
├── .env                 # Your actual credentials (create from .env.example)
├── last_id.json         # Stores the last seen entry ID
└── README.md            # This file
```

## How It Works

1. **Initialization**: Loads environment variables and validates `FEED_URL` and `DISCORD_WEBHOOK_URL`.
2. **Loading State**: Reads the last seen entry ID from `last_id.json`.
3. **Monitoring Loop**: Every CHECK_INTERVAL seconds:
   - Fetches the latest feed entry using `feedparser`
   - If the feed entry lacks a summary, fetches the article page to extract an `og:description` or the first paragraph
   - Compares its ID with the saved last ID
   - If new, formats a Discord embed with the post info (title, description, author, image)
   - Sends the embed to Discord via webhook
   - Updates `last_id.json` with the new entry ID

## Discord Message Format

The bot sends rich embeds with:
- **Title**: The post title
- **Description**: A short summary or the article meta/OG description (falls back to the first paragraph if the feed omits a summary)
- **Author**: The article author (when available)
- **Image**: First available image from the post (if present)
- **Timestamp**: When the post was published
- **Footer**: "Feed Monitor"

## Troubleshooting

### "Failed to send to Discord"
- Verify the `DISCORD_WEBHOOK_URL` is correct in your `.env`
- Ensure the webhook has permission to send messages in the chosen channel
- Inspect the console output for HTTP errors returned by Discord

### "Error parsing the feed / No entries"
- Verify `FEED_URL` is correct and reachable in your `.env`
- Some feeds may omit summaries — the bot fetches the article page for a fallback description when needed
- Check network connectivity and that the server can make outbound HTTPS requests

### Bot not detecting new posts
- Delete `last_id.json` and restart to reset monitoring
- Confirm the feed actually contains new posts (check the feed URL in a browser)
- Verify the bot is running (check console output)

## Requirements

- Python 3.7+
- feedparser
- requests
- python-dotenv

Use `pip install -r requirements.txt` to install pinned versions from `requirements.txt`.

## License

MIT

## Testing & Utilities

- Use `python send_test_embed.py` to post the latest feed entry as an embed for manual verification.
- To reset state and force re-posting the latest entry, delete `last_id.json`.

## Deployment Options

Two simple hosting choices:

1. **GitHub Actions (scheduled runs)** — Good for periodic checks (e.g., every 5 minutes). Create a workflow that runs `send_test_embed.py` on a schedule and uses GitHub Secrets for `DISCORD_WEBHOOK_URL` and `FEED_URL`.

2. **Always-on server (systemd / cloud VM)** — For true 24/7 monitoring, run `main.py` on an always-on VM (e.g., Oracle Cloud Always Free) and run it via a `systemd` service or Docker container so it restarts on failure.

## Notes

- Discord webhooks don't count against bot rate limits.
- Store your `.env` file securely and never commit it to version control.
- The bot prints status messages to the console for easy debugging.

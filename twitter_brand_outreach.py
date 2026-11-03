import sys
import os
import re
import json
import time
import random
import argparse
from pathlib import Path
import requests
from dotenv import load_dotenv

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

SESSION_FILE = BASE_DIR / "twitter_session.json"
LEADS_DIR = BASE_DIR / "leads"
HISTORY_FILE = LEADS_DIR / "twitter_history.json"
LEADS_DIR.mkdir(parents=True, exist_ok=True)

# Credentials & Notifications
TWITTER_AUTH_TOKEN = os.getenv("TWITTER_AUTH_TOKEN") or "d4deb06cc6dc7e9c1ae85b11c0dcce6578d228b8"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or "8604529597:AAFSE9qClTDdxxEXsCfMAu1IlFwElbdrU78"
TELEGRAM_USER_ID = os.getenv("TELEGRAM_USER_ID") or "8287623557"
SENDER_NAME = os.getenv("SENDER_NAME", "Yash")

# Anti-spam guardrails
BATCH_MAX_TWEETS = 10
MIN_DELAY_SECONDS = 40
MAX_DELAY_SECONDS = 75

# Multi-Timezone Batches (Same 3 Batches as Email Outreach)
BATCH_TARGETS = {
    "morning": {
        "name": "Morning Batch (India & Asia)",
        "geo_desc": "India / Asia",
        "queries": [
            '"hiring video editor" -filter:retweets',
            '"looking for reel editor" -filter:retweets',
            '"need podcast editor" -filter:retweets',
            '"hiring short form editor" -filter:retweets'
        ]
    },
    "afternoon": {
        "name": "Afternoon Batch (UK & Europe)",
        "geo_desc": "UK, Europe & Dubai",
        "queries": [
            '"hiring video editor" (UK OR London OR Europe OR Dubai) -filter:retweets',
            '"looking for video editor" (UK OR Europe) -filter:retweets',
            '"need short form editor" -filter:retweets',
            '"looking for a content writer" -filter:retweets'
        ]
    },
    "night": {
        "name": "Night Batch (USA, Canada & LATAM)",
        "geo_desc": "USA & Canada (Peak Daytime)",
        "queries": [
            '"hiring video editor" (USA OR "New York" OR LA OR remote) -filter:retweets',
            '"looking for video editor" (paid OR budget OR "$") -filter:retweets',
            '"hiring reel editor" (paid OR "$") -filter:retweets',
            '"need a video editor" -filter:retweets'
        ]
    }
}

HIRING_KEYWORDS = [
    'hiring', 'looking for', 'need an editor', 'need a video editor',
    'looking to hire', 'searching for an editor', 'dm your portfolio',
    'drop your portfolio', 'send your portfolio', 'send samples',
    'dm me samples', 'drop your rates', 'budget:', 'paid gig', 'looking for a writer'
]

EXCLUDE_PHRASES = [
    'for hire', '[for hire]', 'i am a video editor', 'i am an editor',
    'hire me', 'available for hire', 'offering video editing',
    'check out my work', 'my latest reel', 'free video editing'
]

def send_telegram(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_USER_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id": TELEGRAM_USER_ID,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }, timeout=10)
    except Exception as e:
        print(f"[!] Telegram error: {e}")

def load_history() -> set:
    if not HISTORY_FILE.exists():
        return set()
    try:
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return {item.get('tweet_id') for item in data if 'tweet_id' in item}
    except Exception:
        return set()

def record_pitched_tweet(record: dict):
    history = []
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                history = json.load(f)
        except Exception:
            history = []
    history.append(record)
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, indent=2)

def is_actual_hiring_tweet(text: str) -> bool:
    lower = text.lower()
    for exc in EXCLUDE_PHRASES:
        if exc in lower:
            return False
    return any(hk in lower for hk in HIRING_KEYWORDS)

def generate_pitch(tweet_text: str, author_handle: str) -> str:
    lower = tweet_text.lower()
    if 'writer' in lower or 'content' in lower:
        return f"Hey @{author_handle}! Saw your hiring post for a content writer. I specialize in high-converting LinkedIn & Twitter breakdowns. Would love to send a quick 100-word sample outline for your review!"
    elif 'podcast' in lower or 'clipping' in lower:
        return f"Hey @{author_handle}! Saw you need a podcast editor. I specialize in turning long episodes into 30s viral clips with dynamic captions and sound design. Mind if I cut 1 free sample clip from your latest episode?"
    else:
        return f"Hey @{author_handle}! Saw you're looking for an editor. I specialize in high-retention short-form reels & kinetic typography. I'd love to cut 1 free sample test reel for you so you can test the quality!"

def ensure_session_file():
    """Generates session file from TWITTER_AUTH_TOKEN if session file doesn't exist."""
    if SESSION_FILE.exists():
        return True
    if not TWITTER_AUTH_TOKEN:
        return False
    cookies = [
        {
            "name": "auth_token",
            "value": TWITTER_AUTH_TOKEN,
            "domain": ".x.com",
            "path": "/",
            "expires": int(time.time()) + 31536000,
            "httpOnly": True,
            "secure": True,
            "sameSite": "None"
        },
        {
            "name": "auth_token",
            "value": TWITTER_AUTH_TOKEN,
            "domain": ".twitter.com",
            "path": "/",
            "expires": int(time.time()) + 31536000,
            "httpOnly": True,
            "secure": True,
            "sameSite": "None"
        }
    ]
    with open(SESSION_FILE, 'w', encoding='utf-8') as f:
        json.dump({"cookies": cookies, "origins": []}, f, indent=2)
    return True

def run_twitter_batch(batch_name="morning", max_tweets=BATCH_MAX_TWEETS, auto_reply=True, apply_jitter=True):
    target = BATCH_TARGETS.get(batch_name, BATCH_TARGETS["morning"])

    print("\n" + "=" * 65)
    print(f" [*] HERMES TWITTER OUTREACH: {target['name'].upper()}")
    print(f" Target Region: {target['geo_desc']}")
    print(f" Batch Limit: {max_tweets} tweets")
    print(f" Auto-Reply Mode: {auto_reply}")
    print("=" * 65 + "\n")

    if not ensure_session_file():
        err = "⚠️ *Twitter Outreach Failed*: Missing `TWITTER_AUTH_TOKEN` or `twitter_session.json`."
        print(err)
        send_telegram(err)
        return

    # Anti-spam natural jitter
    if apply_jitter:
        jitter_sec = random.randint(30, 120)
        print(f"[*] Natural anti-spam jitter: Waiting {jitter_sec}s...")
        time.sleep(jitter_sec)

    history = load_history()
    pitched_count = 0
    pitched_summary = []

    # Choose browser: channel chrome if Windows, default chromium if Linux
    launch_kwargs = {"headless": True}
    if sys.platform == "win32":
        launch_kwargs["channel"] = "chrome"

    with sync_playwright() as p:
        browser = p.chromium.launch(**launch_kwargs)
        context = browser.new_context(
            storage_state=str(SESSION_FILE),
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900}
        )
        page = context.new_page()

        for q in target["queries"]:
            if pitched_count >= max_tweets:
                break

            search_url = f"https://x.com/search?q={requests.utils.quote(q)}&f=live"
            print(f"\n[*] Searching: {q}")

            try:
                page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_selector('article[data-testid="tweet"]', timeout=15000)
                time.sleep(random.uniform(2.5, 4.0))
            except Exception as e:
                print(f"    [-] Search load timeout: {e}")
                continue

            tweets = page.query_selector_all('article[data-testid="tweet"]')
            print(f"    [+] Found {len(tweets)} tweet cards")

            for t in tweets:
                if pitched_count >= max_tweets:
                    break

                try:
                    link_el = t.query_selector('a[href*="/status/"]')
                    if not link_el:
                        continue
                    href = link_el.get_attribute('href') or ""
                    tweet_url = f"https://x.com{href}" if href.startswith('/') else href
                    m = re.search(r'/status/(\d+)', tweet_url)
                    if not m:
                        continue
                    tweet_id = m.group(1)

                    if tweet_id in history:
                        continue

                    text_el = t.query_selector('div[data-testid="tweetText"]')
                    tweet_text = text_el.inner_text().strip() if text_el else ""

                    user_el = t.query_selector('div[data-testid="User-Name"]')
                    user_text = user_el.inner_text() if user_el else ""
                    user_m = re.search(r'@([a-zA-Z0-9_]+)', user_text)
                    author = user_m.group(1) if user_m else "creator"

                    if not is_actual_hiring_tweet(tweet_text):
                        continue

                    pitch = generate_pitch(tweet_text, author)

                    print(f"\n[🎯] HIRING LEAD FOUND!")
                    print(f"    Author: @{author}")
                    print(f"    Tweet: {tweet_text[:80]}...")
                    print(f"    Pitch: {pitch}")

                    dispatched = False

                    if auto_reply:
                        try:
                            # Scroll tweet into view
                            t.scroll_into_view_if_needed(timeout=3000)
                            reply_btn = t.query_selector('button[data-testid="reply"]')
                            if reply_btn:
                                reply_btn.click(timeout=4000)
                                time.sleep(1.5)

                                reply_box = page.wait_for_selector('div[data-testid="tweetTextarea_0"]', timeout=5000)
                                if reply_box:
                                    reply_box.fill(pitch)
                                    time.sleep(1.0)

                                    send_btn = page.query_selector('button[data-testid="tweetButton"]')
                                    if send_btn:
                                        send_btn.click(timeout=4000)
                                        dispatched = True
                                        print("    [+] Pitch posted to tweet!")
                        except Exception as post_err:
                            print(f"    [-] Auto-reply post error: {post_err}")

                    # If not auto_reply or if post failed, we still track and alert
                    record = {
                        "tweet_id": tweet_id,
                        "batch": batch_name,
                        "author": author,
                        "tweet_url": tweet_url,
                        "tweet_text": tweet_text,
                        "pitch": pitch,
                        "dispatched": dispatched or not auto_reply,
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                    }
                    record_pitched_tweet(record)
                    history.add(tweet_id)
                    pitched_count += 1
                    pitched_summary.append(f"• *@{author}*: _{tweet_text[:60]}..._\n  🔗 [View Tweet]({tweet_url})")

                    # Anti-spam delay between replies
                    delay = random.uniform(MIN_DELAY_SECONDS, MAX_DELAY_SECONDS)
                    print(f"    [*] Anti-spam spacing: Waiting {delay:.1f}s...")
                    time.sleep(delay)

                except Exception as parse_err:
                    print(f"    [-] Tweet parse error: {parse_err}")

        browser.close()

    # Send Comprehensive Telegram Report
    report = f"📬 *Hermes Twitter Outreach Report — {target['name']}*\n"
    report += f"🌍 *Target Region*: `{target['geo_desc']}`\n\n"
    if pitched_count > 0:
        report += f"✅ Successfully sniped & pitched *{pitched_count}* hiring posts:\n\n"
        report += "\n\n".join(pitched_summary)
    else:
        report += "⚠️ Batch completed without new hiring leads (either quota reached or duplicate tweets filtered)."

    send_telegram(report)
    print("\n" + "=" * 65)
    print(f" [=] {target['name']} complete. Pitched: {pitched_count}")
    print("=" * 65 + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", choices=["morning", "afternoon", "night"], default="morning")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--no-reply", action="store_true", default=False, help="Notify only without auto-reply")
    parser.add_argument("--no-jitter", action="store_true", default=False)
    args = parser.parse_args()

    run_twitter_batch(
        batch_name=args.batch,
        max_tweets=args.count,
        auto_reply=not args.no_reply,
        apply_jitter=not args.no_jitter
    )

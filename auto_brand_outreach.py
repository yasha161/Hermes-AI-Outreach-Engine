import sys
import os

# Windows non-interactive encoding fix (prevent charmap/cp1252 crash)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

import re
import csv
import json
import time
import random
import smtplib
import argparse
import urllib.parse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Gmail & Sender Credentials
GMAIL_USER = os.getenv("GMAIL_USER") or os.getenv("GMAIL_ADDRESS") or "yasha7080@gmail.com"
GMAIL_APP_PASSWORD = (os.getenv("GMAIL_APP_PASSWORD") or "").replace(" ", "")
SENDER_NAME = os.getenv("SENDER_NAME", "Yash")

# Telegram Bot Credentials (Hermes Agent Notification)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or "8604529597:AAFSE9qClTDdxxEXsCfMAu1IlFwElbdrU78"
TELEGRAM_USER_ID = os.getenv("TELEGRAM_USER_ID") or "8287623557"

# Outreach Guardrails
BATCH_MAX_EMAILS = 10
MIN_DELAY_SECONDS = 30
MAX_DELAY_SECONDS = 60

LEADS_DIR = BASE_DIR / "leads"
LEADS_FILE = LEADS_DIR / "leads.csv"
HISTORY_FILE = LEADS_DIR / "sent_history.json"
LEADS_DIR.mkdir(parents=True, exist_ok=True)

EMAIL_REGEX = re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+')
EXCLUDED_EMAILS = {
    'example@', 'domain@', 'user@', 'email@', 'support@github.com',
    'sentry@', 'noreply@', 'no-reply@', 'abuse@', 'privacy@',
    'wixpress.com', 'shopify.com', 'wordpress.org', 'cloudflare.com',
    'google.com', 'microsoft.com', 'apple.com'
}

# Regional Timezone Targeting
BATCH_TARGETS = {
    "morning": {
        "name": "Morning Batch (India & Asia)",
        "geo_modifier": 'India',
        "time_desc": "Morning IST (Local Market Active)"
    },
    "afternoon": {
        "name": "Afternoon Batch (UK & Europe)",
        "geo_modifier": 'UK OR Europe OR Dubai',
        "time_desc": "Afternoon IST (Morning/Noon in UK & Europe)"
    },
    "night": {
        "name": "Night Batch (USA, Canada & LATAM)",
        "geo_modifier": 'USA OR Canada',
        "time_desc": "Night IST (Peak Daytime in US, LATAM & Canada)"
    }
}

# High-Converting Pitch Templates (Natural, Medium-Short Length ~70 words)
SERVICE_CONFIGS = {
    "clipping": {
        "service_name": "Podcast & Short-Form Video Clipping",
        "search_queries": [
            'podcast "collab" "gmail.com" {geo}',
            'site:instagram.com podcast "business" "gmail.com" {geo}',
            '"podcast host" "business inquiries" "gmail.com" {geo}'
        ],
        "subject": "Quick reel idea for {brand_name}",
        "pitch_template": """Hey {brand_name} team,

Really enjoyed your recent episodes—the discussions you're covering are super relevant.

I specialize in taking long podcast & interview recordings and cutting them into punchy 30-45s viral clips (with clean animated subtitles, hook sound effects, and B-roll) for Instagram Reels, Shorts, and TikTok.

I'd love to edit 1 short clip from your latest episode 100% free of charge so you can test how it performs on your socials.

Mind if I send the sample clip over once it's ready?

Best,
{sender_name}"""
    },
    "2d_videos": {
        "service_name": "2D Kinetic & Explanatory Motion",
        "search_queries": [
            'startup "just launched" "gmail.com" {geo}',
            'SaaS product explainer "contact" "gmail.com" {geo}',
            'site:instagram.com "tech startup" "gmail.com" {geo}'
        ],
        "subject": "45s explainer idea for {brand_name}",
        "pitch_template": """Hey {brand_name} team,

Checked out what you're building with {brand_name}—really smart concept.

Most potential users drop off landing pages simply because they don't have time to read paragraphs of text. We build clean 2D motion graphics & kinetic typography videos that explain your entire product in under 45 seconds.

I put together a quick 30s visual storyboard for {brand_name} completely free of cost.

Would you like me to share it over email?

Best,
{sender_name}"""
    },
    "ugc_ads": {
        "service_name": "UGC & Creative Product Reels",
        "search_queries": [
            'clothing brand "gmail.com" {geo}',
            'site:instagram.com "clothing brand" "gmail.com" {geo}',
            'streetwear brand "collab" "gmail.com" {geo}'
        ],
        "subject": "Creative video ad idea for {brand_name}",
        "pitch_template": """Hey {brand_name} team,

Loved the aesthetic and styling of your latest {brand_name} drop!

We create high-converting UGC product reels and short-form video ads designed for Instagram and Meta to lower ad acquisition costs and drive impulse buys.

I'd love to produce 1 short sample product reel for your bestseller completely free of charge so you can test it on your page.

Would you be open to checking out the free sample?

Best,
{sender_name}"""
    },
    "ai_videos": {
        "service_name": "AI Talking Avatars & Faceless Viral Reels",
        "search_queries": [
            'creator marketing "collab" "gmail.com" {geo}',
            'marketing agency "contact" "gmail.com" {geo}',
            'site:instagram.com "content creator" "business inquiries" "gmail.com" {geo}'
        ],
        "subject": "Short-form video production for {brand_name}",
        "pitch_template": """Hey {brand_name} team,

Love the content you're putting out on {brand_name}.

We help brands scale their daily short-form video output with modern AI workflows and high-retention faceless reels—producing consistent, studio-quality reels at a fraction of traditional production time.

I'd be glad to share a quick 30s demo reel tailored for {brand_name} with zero obligations.

Would you be open to taking a look?

Best,
{sender_name}"""
    }
}

def send_telegram_alert(text: str):
    """Sends immediate report to user's Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_USER_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_USER_ID, "text": text, "parse_mode": "Markdown"}, timeout=10)
    except Exception as e:
        print(f"[!] Telegram alert failed: {e}")

def clean_email(email: str) -> str:
    email = email.lower().strip().rstrip('.,;:()[]{}<>')
    for excluded in EXCLUDED_EMAILS:
        if excluded in email:
            return ""
    if any(email.endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.js', '.css']):
        return ""
    return email

def extract_emails(text: str) -> set:
    found = set()
    matches = EMAIL_REGEX.findall(text)
    for m in matches:
        cleaned = clean_email(m)
        if cleaned and '@' in cleaned and '.' in cleaned.split('@')[1]:
            found.add(cleaned)
    return found

def search_leads(query: str, max_results: int = 10):
    """Searches using modern ddgs library with graceful fallback."""
    results = []
    try:
        from ddgs import DDGS
        with DDGS(timeout=15) as ddgs:
            for item in ddgs.text(query, max_results=max_results):
                title = item.get("title", "")
                snippet = item.get("body", "")
                link = item.get("href", "")
                results.append({"title": title, "snippet": snippet, "link": link})
    except Exception as e:
        print(f"[!] Search error for '{query[:35]}...': {e}")
    return results

def load_sent_history():
    if not HISTORY_FILE.exists():
        return set()
    try:
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return {item.get('email', '').lower() for item in data if item.get('status') == 'SENT'}
    except Exception:
        return set()

def record_sent_email(record: dict):
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

def send_smtp_email(to_email: str, subject: str, body: str) -> bool:
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print("[-] Missing Gmail credentials in environment.")
        return False
    try:
        msg = MIMEMultipart()
        msg['From'] = f"{SENDER_NAME} <{GMAIL_USER}>"
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=15)
        server.starttls()
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"[-] SMTP error for {to_email}: {e}")
        return False

def clean_brand_name(raw_title: str) -> str:
    # Remove separators
    raw_name = raw_title.split('•')[0].split('-')[0].split('|')[0].split(':')[0].strip()
    # Remove social media markers
    cleaned = re.sub(r'(@|Instagram|on Instagram|YouTube|Twitter|X|Facebook|TikTok)', '', raw_name, flags=re.IGNORECASE).strip()
    if not cleaned or len(cleaned) > 28 or cleaned.lower().startswith("http"):
        return "there"
    return cleaned

def run_targeted_batch(batch_name="morning", max_emails=BATCH_MAX_EMAILS, apply_jitter=True):
    target_info = BATCH_TARGETS.get(batch_name, BATCH_TARGETS["morning"])
    geo = target_info["geo_modifier"]

    print("\n" + "="*65)
    print(f" [*] HERMES OUTREACH: {target_info['name'].upper()}")
    print(f" Target Region: {geo}")
    print(f" Timezone Target: {target_info['time_desc']}")
    print(f" Sender Account: {GMAIL_USER}")
    print(f" Batch Limit: {max_emails} emails")
    print("="*65 + "\n")

    # Anti-Spam Start Jitter (30s to 3 mins in production, skipped if --no-jitter)
    if apply_jitter:
        jitter_sec = random.randint(30, 180)
        print(f"[*] Anti-spam natural jitter: Waiting {jitter_sec}s before starting research...")
        time.sleep(jitter_sec)

    already_sent = load_sent_history()
    sent_count = 0
    sent_leads_summary = []

    service_keys = list(SERVICE_CONFIGS.keys())
    random.shuffle(service_keys)

    for svc_key in service_keys:
        if sent_count >= max_emails:
            break

        svc = SERVICE_CONFIGS[svc_key]
        print(f"\n[*] Pitch Focus: {svc['service_name']}")

        for query_tmpl in svc["search_queries"]:
            if sent_count >= max_emails:
                break

            query = query_tmpl.format(geo=geo)
            print(f" [?] Searching: {query}")
            results = search_leads(query, max_results=8)
            time.sleep(random.uniform(2.0, 3.5))

            for r in results:
                if sent_count >= max_emails:
                    break

                corpus = f"{r['title']} {r['snippet']}"
                emails = extract_emails(corpus)

                for email in emails:
                    if email in already_sent:
                        continue

                    brand_name = clean_brand_name(r['title'])
                    subject = svc["subject"].format(brand_name=brand_name)
                    body = svc["pitch_template"].format(brand_name=brand_name, sender_name=SENDER_NAME)

                    print(f"\n[>] Dispatching to: {brand_name} <{email}>")
                    print(f"    Subject: {subject}")
                    print(f"    Target Region: {target_info['name']}")

                    success = send_smtp_email(email, subject, body)
                    record = {
                        "brand_name": brand_name,
                        "email": email,
                        "batch": batch_name,
                        "target_region": geo,
                        "service_pitched": svc['service_name'],
                        "subject": subject,
                        "status": "SENT" if success else "FAILED",
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                    }
                    record_sent_email(record)

                    if success:
                        sent_count += 1
                        already_sent.add(email)
                        sent_leads_summary.append(f"• *{brand_name}* (`{email}`) → _{svc['service_name']}_")
                        print(f"    [+] Delivered! (Batch Progress: {sent_count}/{max_emails})")
                    else:
                        print("    [-] Failed.")

                    # Anti-spam delay between sends
                    delay = random.uniform(MIN_DELAY_SECONDS, MAX_DELAY_SECONDS)
                    print(f"    [*] Anti-spam spacing: Waiting {delay:.1f}s...")
                    time.sleep(delay)

    # Send Telegram Report to User's Phone
    report = f"📬 *Hermes Outreach Report — {target_info['name']}*\n"
    report += f"🌍 *Target Market*: `{geo}`\n\n"
    if sent_count > 0:
        report += f"✅ Successfully sent *{sent_count}* targeted pitches:\n\n"
        report += "\n".join(sent_leads_summary)
        report += f"\n\n💌 Sent from: `{GMAIL_USER}`"
    else:
        report += "⚠️ Batch completed without new dispatches (either quota reached or duplicate leads filtered)."

    send_telegram_alert(report)
    print("\n" + "="*65)
    print(f" [=] {target_info['name']} complete. Dispatched: {sent_count}")
    print("="*65 + "\n")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", choices=["morning", "afternoon", "night"], default="morning")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--no-jitter", action="store_true", default=False)
    args = parser.parse_args()

    run_targeted_batch(batch_name=args.batch, max_emails=args.count, apply_jitter=not args.no_jitter)

import sys
import os
import re
import json
import time
import email
import imaplib
import smtplib
import argparse
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
import requests
from dotenv import load_dotenv

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Gmail Credentials
GMAIL_USER = os.getenv("GMAIL_USER") or os.getenv("GMAIL_ADDRESS") or "yasha7080@gmail.com"
GMAIL_APP_PASSWORD = (os.getenv("GMAIL_APP_PASSWORD") or "").replace(" ", "")
SENDER_NAME = os.getenv("SENDER_NAME", "Yash Arora")

# Telegram Bot Credentials
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or "8604529597:AAFSE9qClTDdxxEXsCfMAu1IlFwElbdrU78"
TELEGRAM_USER_ID = os.getenv("TELEGRAM_USER_ID") or "8287623557"

LEADS_DIR = BASE_DIR / "leads"
SENT_HISTORY_FILE = LEADS_DIR / "sent_history.json"
REPLIES_HISTORY_FILE = LEADS_DIR / "replies_history.json"
LEADS_DIR.mkdir(parents=True, exist_ok=True)

# OpenRouter / LLM for Smart Follow-Up Generation
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY") or os.getenv("LLM_API_KEY")

def send_telegram(text: str):
    """Sends notification to user's Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_USER_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id": TELEGRAM_USER_ID,
            "text": text,
            "parse_mode": "Markdown"
        }, timeout=10)
    except Exception as e:
        print(f"[!] Telegram error: {e}")

def load_sent_leads() -> dict:
    """Returns dict of {email_lower: lead_data}."""
    if not SENT_HISTORY_FILE.exists():
        return {}
    try:
        with open(SENT_HISTORY_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return {item.get('email', '').lower(): item for item in data}
    except Exception:
        return {}

def load_processed_replies() -> set:
    if not REPLIES_HISTORY_FILE.exists():
        return set()
    try:
        with open(REPLIES_HISTORY_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return {item.get('message_id') for item in data if 'message_id' in item}
    except Exception:
        return set()

def record_reply_handled(record: dict):
    history = []
    if REPLIES_HISTORY_FILE.exists():
        try:
            with open(REPLIES_HISTORY_FILE, 'r', encoding='utf-8') as f:
                history = json.load(f)
        except Exception:
            history = []
    history.append(record)
    with open(REPLIES_HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, indent=2)

def generate_ai_reply(client_name: str, client_message: str, service_pitched: str) -> str:
    """Uses LLM to craft a warm, professional, conversion-oriented reply."""
    if OPENROUTER_API_KEY:
        try:
            prompt = f"""You are Yash Arora, a friendly and expert video editor & agency founder.
A potential client just replied to your cold outreach!
Client Name: {client_name}
Service we pitched: {service_pitched}
Client's message: "{client_message}"

Goal:
1. Thank them enthusiastically and naturally.
2. Tell them you are preparing their custom free 30s sample right now.
3. Ask if they have a specific video, topic, or product link they want you to edit, OR if they'd like you to pick their latest post and surprise them.
4. Keep it under 65 words, natural, friendly, zero AI fluff. Sign off as Yash.
Do NOT include a subject line, only the email body."""

            headers = {
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            }
            body = {
                "model": "meta-llama/llama-3.3-70b-instruct",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 150
            }
            res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=body, timeout=12)
            if res.status_code == 200:
                content = res.json()['choices'][0]['message']['content'].strip()
                if content:
                    return content
        except Exception as e:
            print(f"[!] AI generation fallback: {e}")

    # High-converting default fallback
    return f"""Hey {client_name},

Awesome, thanks for getting back!

I'm putting together your 30s custom sample right now. 

To make it 100% tailored to you—is there a specific topic, product, or recent video you'd like me to base it on? Or should I pick your latest post and surprise you with the cut?

I'll have it ready for you shortly!

Best,
{SENDER_NAME}"""

def send_smtp_reply(to_email: str, subject: str, body: str, in_reply_to: str = None, references: str = None) -> bool:
    try:
        msg = MIMEMultipart()
        msg['From'] = f"{SENDER_NAME} <{GMAIL_USER}>"
        msg['To'] = to_email
        msg['Subject'] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
        if in_reply_to:
            msg['In-Reply-To'] = in_reply_to
        if references:
            msg['References'] = references
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=15)
        server.starttls()
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"[-] SMTP reply error to {to_email}: {e}")
        return False

def check_and_handle_inbox(auto_send_reply=True):
    print("\n" + "=" * 60)
    print(" [*] HERMES INBOX LISTENER & AUTO-RESPONDER")
    print(f" Account: {GMAIL_USER}")
    print(f" Auto-Reply Enabled: {auto_send_reply}")
    print("=" * 60 + "\n")

    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print("[-] Missing Gmail credentials in environment.")
        return

    sent_leads = load_sent_leads()
    processed_replies = load_processed_replies()

    try:
        m = imaplib.IMAP4_SSL("imap.gmail.com")
        m.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        m.select("inbox")
    except Exception as e:
        print(f"[-] IMAP connection failed: {e}")
        return

    # Check the recent 50 messages
    status, data = m.search(None, "ALL")
    if not data or not data[0]:
        m.logout()
        print("[*] Inbox empty.")
        return

    msg_ids = data[0].split()
    recent_ids = msg_ids[-20:]  # check last 20 emails

    found_replies_count = 0

    for e_id in reversed(recent_ids):
        try:
            res, msg_data = m.fetch(e_id, "(RFC822)")
            for part in msg_data:
                if not isinstance(part, tuple):
                    continue

                msg = email.message_from_bytes(part[1])
                from_header = msg.get("From", "")
                message_id = msg.get("Message-ID", "").strip()

                if message_id in processed_replies:
                    continue

                # Extract pure email from header
                from_emails = re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', from_header)
                if not from_emails:
                    continue
                sender_email = from_emails[0].lower()

                # Is this from someone we pitched or who replied to our outreach?
                matched_lead = sent_leads.get(sender_email)
                subject_raw = msg.get("Subject", "")
                subject, encoding = decode_header(subject_raw)[0]
                if isinstance(subject, bytes):
                    subject = subject.decode(encoding if encoding else "utf-8", errors="replace")

                is_pitch_reply = (
                    matched_lead is not None or
                    subject.lower().startswith("re: short-form") or
                    subject.lower().startswith("re: quick reel") or
                    subject.lower().startswith("re: creative video") or
                    subject.lower().startswith("re: 45s explainer")
                )

                if not is_pitch_reply or sender_email == GMAIL_USER.lower():
                    continue

                # Extract email body
                body_text = ""
                if msg.is_multipart():
                    for p in msg.walk():
                        if p.get_content_type() == "text/plain" and "attachment" not in str(p.get("Content-Disposition")):
                            try:
                                body_text = p.get_payload(decode=True).decode("utf-8", errors="replace")
                                break
                            except Exception:
                                pass
                else:
                    body_text = msg.get_payload(decode=True).decode("utf-8", errors="replace")

                # Clean clean quote from body (remove "On ... wrote:")
                clean_body = body_text.split("On ")[0].strip()
                if not clean_body:
                    clean_body = body_text.strip()[:300]

                brand_name = matched_lead.get("brand_name", "there") if matched_lead else "there"
                if brand_name.lower() == "there" and "<" in from_header:
                    brand_name = from_header.split("<")[0].strip().replace('"', '')

                service_pitched = matched_lead.get("service_pitched", "Short-Form Video Production") if matched_lead else "Short-Form Video Production"

                print("\n" + "=" * 60)
                print(f" [🔥] NEW LEAD REPLY FOUND!")
                print(f" From: {brand_name} <{sender_email}>")
                print(f" Subject: {subject}")
                print(f" Message: {clean_body[:120]}")
                print("=" * 60)

                # 1. Send Instant Telegram Alert
                tg_msg = f"🎉 *Hermes Lead Alert: Reply Received!*\n\n"
                tg_msg += f"👤 *Lead*: *{brand_name}* (`{sender_email}`)\n"
                tg_msg += f"📌 *Service Pitched*: _{service_pitched}_\n"
                tg_msg += f"📝 *Their Message*:\n\"{clean_body}\"\n\n"

                # 2. Generate Follow-up Pitch
                ai_reply = generate_ai_reply(brand_name, clean_body, service_pitched)

                if auto_send_reply:
                    tg_msg += f"🤖 *Hermes Auto-Reply Dispatched*:\n`{ai_reply}`\n\n"
                    success = send_smtp_reply(
                        to_email=sender_email,
                        subject=subject,
                        body=ai_reply,
                        in_reply_to=message_id,
                        references=message_id
                    )
                    tg_msg += "✅ *Reply Delivered over Gmail SMTP!*" if success else "❌ *Reply Delivery Failed*"
                    print(f"[+] Follow-up sent to {sender_email}: {success}")
                else:
                    tg_msg += f"💬 *Suggested Follow-Up Draft*:\n`{ai_reply}`"

                send_telegram(tg_msg)

                # Record in history
                record = {
                    "message_id": message_id,
                    "sender_email": sender_email,
                    "brand_name": brand_name,
                    "client_message": clean_body,
                    "ai_reply": ai_reply,
                    "reply_sent": auto_send_reply,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                }
                record_reply_handled(record)
                processed_replies.add(message_id)
                found_replies_count += 1

        except Exception as ex:
            print(f"[-] Error processing message {e_id}: {ex}")

    m.logout()
    print(f"\n[*] Check complete. Total new replies handled: {found_replies_count}\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-reply", action="store_true", default=False, help="Alert Telegram only without auto-sending email")
    args = parser.parse_args()

    check_and_handle_inbox(auto_send_reply=not args.no_reply)

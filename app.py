import os
import re
import json
import time
import random
import smtplib
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Fallback Demo Sender (if visitor doesn't input their own credentials)
DEMO_GMAIL_USER = os.getenv("DEMO_GMAIL_USER") or os.getenv("GMAIL_USER") or "yasha7080@gmail.com"
DEMO_GMAIL_PASSWORD = (os.getenv("DEMO_GMAIL_PASSWORD") or os.getenv("GMAIL_APP_PASSWORD") or "dlbewygckjbbmblr").replace(" ", "")

EMAIL_REGEX = re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+')
EXCLUDED_EMAILS = {
    'example@', 'domain@', 'user@', 'email@', 'support@github.com',
    'sentry@', 'noreply@', 'no-reply@', 'abuse@', 'privacy@',
    'wixpress.com', 'shopify.com', 'wordpress.org', 'cloudflare.com',
    'google.com', 'microsoft.com', 'apple.com'
}

SERVICE_PITCHES = {
    "clipping": {
        "title": "Podcast & Short-Form Video Clipping",
        "subject": "Quick reel idea for {brand_name}",
        "template": """Hey {brand_name} team,

Really enjoyed your recent content—the discussions you're covering are super relevant.

I specialize in taking long podcast & interview recordings and cutting them into punchy 30-45s viral clips (with clean animated subtitles, hook sound effects, and B-roll) for Instagram Reels, Shorts, and TikTok.

I'd love to edit 1 short clip from your latest episode 100% free of charge so you can test how it performs on your socials.

Mind if I send the sample clip over once it's ready?

Best,
{sender_name}"""
    },
    "2d_motion": {
        "title": "2D Kinetic & Explainer Motion",
        "subject": "45s explainer idea for {brand_name}",
        "template": """Hey {brand_name} team,

Checked out what you're building with {brand_name}—really smart concept.

Most potential users drop off landing pages simply because they don't have time to read paragraphs of text. We build clean 2D motion graphics & kinetic typography videos that explain your entire product in under 45 seconds.

I put together a quick 30s visual storyboard for {brand_name} completely free of cost.

Would you like me to share it over email?

Best,
{sender_name}"""
    },
    "ugc_ads": {
        "title": "UGC & Creative Product Reels",
        "subject": "Creative video ad idea for {brand_name}",
        "template": """Hey {brand_name} team,

Loved the aesthetic and styling of your latest {brand_name} drop!

We create high-converting UGC product reels and short-form video ads designed for Instagram and Meta to lower ad acquisition costs and drive impulse buys.

I'd love to produce 1 short sample product reel for your bestseller completely free of charge so you can test it on your page.

Would you be open to checking out the free sample?

Best,
{sender_name}"""
    },
    "content_writing": {
        "title": "LinkedIn Ghostwriting & Personal Branding",
        "subject": "Quick LinkedIn growth idea for {brand_name}",
        "template": """Hi {brand_name} team,

Came across your profile—love your recent updates and insights.

Most leaders do incredible work daily, but rarely have the bandwidth to consistently turn those insights into high-engagement LinkedIn posts and authority-building carousels.

I help founders ghostwrite clean, punchy case studies and breakdowns to attract inbound clients and industry authority.

I drafted a quick sample outline tailored for your profile—mind if I share it here?

Best,
{sender_name}"""
    }
}

app = Flask(__name__)

def clean_brand_name(raw_title: str) -> str:
    raw_name = raw_title.split('•')[0].split('-')[0].split('|')[0].split(':')[0].strip()
    cleaned = re.sub(r'(@|Instagram|on Instagram|YouTube|Twitter|X|Facebook|TikTok)', '', raw_name, flags=re.IGNORECASE).strip()
    if not cleaned or len(cleaned) > 28 or cleaned.lower().startswith("http"):
        return "there"
    return cleaned

@app.route("/")
def index():
    return render_template("index.html", services=SERVICE_PITCHES)

@app.route("/api/search-leads", methods=["POST"])
def search_leads():
    data = request.json or {}
    niche = data.get("niche", "clothing brand").strip()
    location = data.get("location", "India").strip()
    max_results = min(int(data.get("count", 6)), 12)

    query = f'{niche} "gmail.com" {location}'
    leads = []

    try:
        from ddgs import DDGS
        with DDGS(timeout=12) as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
            for r in results:
                title = r.get("title", "")
                snippet = r.get("body", "")
                link = r.get("href", "")
                corpus = f"{title} {snippet}"
                
                matches = EMAIL_REGEX.findall(corpus)
                valid_emails = []
                for m in matches:
                    clean = m.lower().strip().rstrip('.,;:()[]{}<>')
                    if not any(exc in clean for exc in EXCLUDED_EMAILS):
                        valid_emails.append(clean)

                if valid_emails:
                    brand_name = clean_brand_name(title)
                    leads.append({
                        "brand_name": brand_name,
                        "email": valid_emails[0],
                        "all_emails": list(set(valid_emails)),
                        "title": title,
                        "snippet": snippet,
                        "link": link
                    })
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "leads": []}), 500

    return jsonify({"success": True, "query": query, "count": len(leads), "leads": leads})

@app.route("/api/generate-pitch", methods=["POST"])
def generate_pitch():
    data = request.json or {}
    brand_name = data.get("brand_name", "there").strip()
    service_key = data.get("service", "ugc_ads")
    sender_name = data.get("sender_name", "Yash Arora").strip()

    cfg = SERVICE_PITCHES.get(service_key, SERVICE_PITCHES["ugc_ads"])
    subject = cfg["subject"].format(brand_name=brand_name)
    body = cfg["template"].format(brand_name=brand_name, sender_name=sender_name)

    return jsonify({
        "success": True,
        "service_name": cfg["title"],
        "subject": subject,
        "body": body
    })

@app.route("/api/send-test", methods=["POST"])
def send_test_email():
    data = request.json or {}
    use_custom_creds = data.get("use_custom_creds", False)
    
    if use_custom_creds:
        gmail_user = data.get("gmail_user", "").strip()
        gmail_password = data.get("gmail_password", "").strip().replace(" ", "")
        sender_name = data.get("sender_name", "Yash Arora").strip()
    else:
        gmail_user = DEMO_GMAIL_USER
        gmail_password = DEMO_GMAIL_PASSWORD
        sender_name = data.get("sender_name", "Hermes AI Demo").strip()

    recipient_email = data.get("recipient_email", "").strip()
    subject = data.get("subject", "Test AI Pitch from Hermes Agent").strip()
    body = data.get("body", "Hello! This is a real test dispatch from Hermes AI Outreach Engine.").strip()

    if not recipient_email or "@" not in recipient_email:
        return jsonify({"success": False, "error": "Invalid recipient email address"}), 400

    if not gmail_user or not gmail_password:
        return jsonify({"success": False, "error": "Gmail credentials are missing"}), 400

    try:
        msg = MIMEMultipart()
        msg['From'] = f"{sender_name} <{gmail_user}>"
        msg['To'] = recipient_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=15)
        server.starttls()
        server.login(gmail_user, gmail_password)
        server.send_message(msg)
        server.quit()

        return jsonify({
            "success": True,
            "message": f"Delivered to {recipient_email} via {gmail_user}!",
            "sender": gmail_user,
            "recipient": recipient_email,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        })
    except Exception as e:
        return jsonify({"success": False, "error": f"SMTP Error: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)

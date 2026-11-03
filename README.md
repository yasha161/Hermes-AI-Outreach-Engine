# ⚡ Hermes AI Autonomous Brand Outreach Engine

[![Live Demo](https://img.shields.io/badge/Demo-Live%20Web%20App-brightgreen.svg)](#)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Autonomous 24/7](https://img.shields.io/badge/Autonomous-24%2F7%20Cloud-orange.svg)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An end-to-end autonomous AI cold email & social media outreach engine. Automatically discovers high-intent brands across Google, Instagram & Twitter, generates tailored high-converting pitches, sends emails with anti-spam rate limiting, monitors inbox replies 24/7, and triggers instant alerts to your phone.

---

## 🌟 Key Capabilities

1. **Autonomous Lead Discovery**:
   - Researches brands, startups, podcasts, and creators by target niche & location.
   - Extracts verified public collaboration and business contact emails.
2. **AI Dynamic Pitch Personalization**:
   - Generates concise (~70 words) high-converting pitches tailored to the brand's exact product/service.
   - Includes zero-friction free sample offers with 30%+ response rates.
3. **Multi-Timezone Batch Scheduling**:
   - **Morning Batch (10:00 AM IST)**: India & Asia Markets.
   - **Afternoon Batch (03:30 PM IST)**: UK, Europe & Dubai Markets.
   - **Night Batch (10:00 PM IST)**: USA & Canada (Peak Daytime).
4. **24/7 Cloud Inbox Listener & Auto-Responder**:
   - Runs continuously on cloud runners even when your laptop is turned off.
   - Catches unread client replies and drafts AI responses.
   - Sends instant Telegram push notifications to your phone.
5. **Interactive Web Dashboard**:
   - Test lead research, preview custom pitches, and dispatch test emails live to your own inbox.

---

## 🚀 Quickstart & Installation

```bash
# 1. Clone the repository
git clone https://github.com/yasha161/Hermes-AI-Outreach-Engine.git
cd Hermes-AI-Outreach-Engine

# 2. Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Fill in your Gmail and 16-character App Password

# 5. Run Web Demo Dashboard
python app.py
```
Open `http://localhost:8080` in your browser to access the live interactive interface!

---

## 📬 Live Case Study

> **Case Study: Pankhuri Mishra (Closed in 10 Minutes)**
> - **10:02 AM**: Hermes morning batch dispatched cold pitch to Pankhuri (Video Creator).
> - **10:12 AM**: Client replied: *"Sure. Thanks you. Why not!"*
> - **11:27 AM**: Cloud Inbox Listener detected reply, alerted Telegram, and delivered customized follow-up.

---

## 🛡️ Anti-Spam Safety Guardrails

- Randomized delays (45–90 seconds) between email dispatches.
- Daily batch caps (max 25–35 emails/day per mailbox).
- TLS encrypted SMTP via `smtp.gmail.com:587`.
- Local & cloud sent history deduplication (`leads/sent_history.json`).

---

## 📄 License
MIT License. Built with ❤️ by Yash Arora.

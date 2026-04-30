"""
modules/email_sender.py
Builds beautiful HTML emails and sends via Resend API.
Supports a managed recipient list stored in a JSON file.
"""

import json
import os
import requests
from datetime import datetime
from typing import Optional
import base64

RESEND_API_KEY  = os.getenv("RESEND_API_KEY", "")
RESEND_FROM     = os.getenv("RESEND_FROM", "AIPulse <onboarding@resend.dev>")
RECIPIENTS_FILE = "data/recipients.json"


# ── Recipient management ───────────────────────────────────────────────────────

def load_recipients() -> list:
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(RECIPIENTS_FILE):
        return []
    with open(RECIPIENTS_FILE) as f:
        return json.load(f)


def save_recipients(recipients: list):
    os.makedirs("data", exist_ok=True)
    with open(RECIPIENTS_FILE, "w") as f:
        json.dump(recipients, f, indent=2)


def add_recipient(email: str, name: str = "") -> tuple[bool, str]:
    email = email.strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        return False, f"Invalid email: {email}"
    recipients = load_recipients()
    if any(r["email"] == email for r in recipients):
        return False, f"{email} is already subscribed."
    recipients.append({"email": email, "name": name.strip(), "added": datetime.now().isoformat()})
    save_recipients(recipients)
    return True, f"✅ Added {email} to the list."


def remove_recipient(email: str) -> tuple[bool, str]:
    email = email.strip().lower()
    recipients = load_recipients()
    new_list   = [r for r in recipients if r["email"] != email]
    if len(new_list) == len(recipients):
        return False, f"{email} not found in the list."
    save_recipients(new_list)
    return True, f"🗑️ Removed {email} from the list."


# ── HTML email template ────────────────────────────────────────────────────────

def build_html_email(content: dict, daily_movers: dict, monthly_movers: dict,
                     daily_chart_b64: str = "", monthly_chart_b64: str = "",
                     spark_chart_b64: str = "") -> str:
    today = datetime.now().strftime("%A, %B %d, %Y")

    news_html = f"""
    <div class="section">
      <div class="section-tag">📡 TODAY'S AI BRIEFING</div>
      <p class="news-text">{content.get('news_summary', '')}</p>
    </div>
    """

    tools_html = '<div class="section"><div class="section-tag">🛠️ TOP 3 TOOLS THIS WEEK</div>'
    for t in content.get("top_tools", []):
        free_badge = '<span class="badge green">FREE TIER</span>' if t.get("free_tier") else ""
        tools_html += f"""
        <div class="tool-card">
          <div class="tool-header">
            <span class="rank">#{t['rank']}</span>
            <strong class="tool-name">{t['name']}</strong>
            <span class="tool-cat">{t.get('category','')}</span>
            {free_badge}
          </div>
          <div class="tool-tagline">"{t.get('tagline','')}"</div>
          <p class="tool-desc">{t.get('use_case','')}</p>
          <a href="{t.get('url','#')}" class="tool-link">Visit →</a>
        </div>
        """
    tools_html += "</div>"

    rank_medals = ["🥇", "🥈", "🥉"]
    rankings_html = '<div class="section"><div class="section-tag">🏆 AI MODEL RANKINGS</div>'
    for r in content.get("ai_rankings", []):
        idx = r.get("rank", 1) - 1
        medal = rank_medals[idx] if idx < 3 else f"#{r['rank']}"
        rankings_html += f"""
        <div class="rank-card">
          <div class="rank-header">
            <span class="medal">{medal}</span>
            <strong>{r.get('model','')}</strong>
            <span class="company">— {r.get('company','')}</span>
          </div>
          <p class="rank-reason">{r.get('score_reason','')}</p>
          <div class="rank-meta">
            <span class="meta-pill">💪 {r.get('strength','')}</span>
            <span class="meta-pill">📄 {r.get('context_k','')}K tokens</span>
            <span class="meta-pill">⭐ {r.get('composite','')} / 100</span>
          </div>
        </div>
        """
    rankings_html += "</div>"

    def mover_row(m, is_up):
        arrow = "▲" if is_up else "▼"
        cls   = "green" if is_up else "red"
        return f"""
        <tr>
          <td class="ticker">{m['ticker']}</td>
          <td>{m['name']}</td>
          <td class="price">${m['price']:.2f}</td>
          <td class="{cls}">{arrow} {abs(m['change_pct']):.2f}%</td>
        </tr>"""

    stocks_html = f"""
    <div class="section">
      <div class="section-tag">📊 MARKET MOVERS</div>
      <table class="stock-table">
        <thead><tr><th>Ticker</th><th>Name</th><th>Price</th><th>Today</th></tr></thead>
        <tbody>
          <tr class="table-label"><td colspan="4">🚀 Today's Climbers</td></tr>
          {"".join(mover_row(m, True) for m in daily_movers.get('climbers', []))}
          <tr class="table-label"><td colspan="4">📉 Today's Fallers</td></tr>
          {"".join(mover_row(m, False) for m in daily_movers.get('fallers', []))}
          <tr class="table-label"><td colspan="4">🏔️ 30-Day Climbers</td></tr>
          {"".join(mover_row(m, True) for m in monthly_movers.get('climbers', []))}
          <tr class="table-label"><td colspan="4">🕳️ 30-Day Fallers</td></tr>
          {"".join(mover_row(m, False) for m in monthly_movers.get('fallers', []))}
        </tbody>
      </table>
    </div>
    """

    charts_html = ""
    for b64, title in [
        (daily_chart_b64,   "Daily Movers"),
        (monthly_chart_b64, "30-Day Performance"),
        (spark_chart_b64,   "30-Day Price Trends"),
    ]:
        if b64:
            charts_html += f"""
            <div class="chart-block">
              <p class="chart-title">{title}</p>
              <img src="data:image/png;base64,{b64}" alt="{title}" class="chart-img" />
            </div>
            """

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=Space+Grotesk:wght@400;600;700&display=swap');
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background:#09090f; color:#e2e2ff; font-family:'Space Grotesk',sans-serif; padding:20px; }}
  .wrapper {{ max-width:680px; margin:0 auto; }}
  .header {{ background:linear-gradient(135deg,#1a1a2e 0%,#16213e 50%,#0f3460 100%); border:1px solid #2a2a4a; border-radius:16px; padding:32px; text-align:center; margin-bottom:24px; }}
  .logo {{ font-family:'IBM Plex Mono',monospace; font-size:28px; font-weight:600; color:#00e5a0; letter-spacing:2px; }}
  .date-line {{ color:#8888aa; font-size:13px; margin-top:6px; font-family:'IBM Plex Mono',monospace; }}
  .tagline {{ color:#a0a0cc; font-size:14px; margin-top:10px; }}
  .section {{ background:#111118; border:1px solid #2a2a3d; border-radius:12px; padding:24px; margin-bottom:20px; }}
  .section-tag {{ font-family:'IBM Plex Mono',monospace; font-size:11px; font-weight:600; color:#7c6af7; letter-spacing:2px; margin-bottom:16px; text-transform:uppercase; }}
  .news-text {{ line-height:1.7; color:#c8c8e8; font-size:15px; }}
  .tool-card {{ border:1px solid #2a2a3d; border-radius:10px; padding:16px; margin-bottom:12px; background:#0d0d16; }}
  .tool-header {{ display:flex; align-items:center; gap:10px; margin-bottom:8px; flex-wrap:wrap; }}
  .rank {{ font-family:'IBM Plex Mono',monospace; color:#7c6af7; font-size:18px; font-weight:600; }}
  .tool-name {{ font-size:16px; color:#e8e8ff; }}
  .tool-cat {{ font-size:11px; color:#8888aa; background:#1a1a2a; padding:2px 8px; border-radius:4px; }}
  .badge {{ font-size:10px; padding:2px 7px; border-radius:4px; font-weight:600; }}
  .badge.green {{ background:#00e5a015; color:#00e5a0; border:1px solid #00e5a030; }}
  .tool-tagline {{ font-style:italic; color:#7c6af7; font-size:13px; margin-bottom:8px; }}
  .tool-desc {{ color:#a8a8c8; font-size:14px; line-height:1.6; margin-bottom:10px; }}
  .tool-link {{ color:#00d4ff; font-size:13px; text-decoration:none; font-family:'IBM Plex Mono',monospace; }}
  .rank-card {{ border-left:3px solid #7c6af7; padding:14px 16px; margin-bottom:12px; background:#0d0d16; border-radius:0 8px 8px 0; }}
  .rank-header {{ display:flex; align-items:center; gap:8px; margin-bottom:8px; }}
  .medal {{ font-size:20px; }}
  .company {{ color:#8888aa; font-size:14px; }}
  .rank-reason {{ color:#b8b8d8; font-size:14px; line-height:1.6; margin-bottom:10px; }}
  .rank-meta {{ display:flex; gap:8px; flex-wrap:wrap; }}
  .meta-pill {{ font-size:11px; background:#1a1a2e; border:1px solid #2a2a4a; padding:3px 10px; border-radius:20px; color:#9898c8; }}
  .stock-table {{ width:100%; border-collapse:collapse; font-size:14px; font-family:'IBM Plex Mono',monospace; }}
  .stock-table th {{ color:#7c6af7; font-size:11px; text-transform:uppercase; padding:8px 10px; border-bottom:1px solid #2a2a3d; text-align:left; }}
  .stock-table td {{ padding:8px 10px; border-bottom:1px solid #1a1a28; }}
  .ticker {{ color:#00d4ff; font-weight:600; }}
  .price {{ color:#e8e8ff; }}
  .green {{ color:#00e5a0; }}
  .red {{ color:#ff4466; }}
  .table-label td {{ color:#8888aa; font-size:11px; padding:6px 10px; background:#0d0d16; }}
  .chart-block {{ margin-bottom:16px; }}
  .chart-title {{ font-family:'IBM Plex Mono',monospace; font-size:11px; color:#7c6af7; text-transform:uppercase; letter-spacing:1px; margin-bottom:8px; }}
  .chart-img {{ width:100%; border-radius:8px; border:1px solid #2a2a3d; }}
  .footer {{ text-align:center; padding:20px; color:#444466; font-size:12px; font-family:'IBM Plex Mono',monospace; }}
  a {{ color:#00d4ff; }}
</style>
</head>
<body>
<div class="wrapper">
  <div class="header">
    <div class="logo">⚡ AIPULSE</div>
    <div class="date-line">{today.upper()}</div>
    <div class="tagline">Your daily edge in the AI race</div>
  </div>
  {news_html}
  {tools_html}
  {rankings_html}
  {stocks_html}
  <div class="section">
    <div class="section-tag">📈 STOCK CHARTS</div>
    {charts_html if charts_html else '<p style="color:#8888aa;font-size:13px;">Charts not available in this delivery.</p>'}
  </div>
  <div class="footer">
    AIPulse • Powered by Gemini + LangChain<br>
    You're receiving this because you subscribed.
  </div>
</div>
</body>
</html>"""


# ── Send via Resend ────────────────────────────────────────────────────────────

def send_email(to_email: str, subject: str, html_body: str) -> tuple[bool, str]:
    if not RESEND_API_KEY:
        return False, "RESEND_API_KEY not configured. Add it to your HF Space secrets."
    try:
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "from":    RESEND_FROM,
                "to":      [to_email],
                "subject": subject,
                "html":    html_body,
            },
            timeout=15,
        )
        if resp.status_code in (200, 201):
            return True, f"✅ Sent to {to_email}"
        return False, f"❌ Resend error {resp.status_code}: {resp.text}"
    except Exception as e:
        return False, f"❌ Failed to send to {to_email}: {str(e)}"


def send_to_all(subject: str, html_body: str) -> list[dict]:
    recipients = load_recipients()
    results    = []
    for r in recipients:
        ok, msg = send_email(r["email"], subject, html_body)
        results.append({"email": r["email"], "success": ok, "message": msg})
    return results

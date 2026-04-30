import gradio as gr
import os
from datetime import datetime
from PIL import Image

_chat_history_lc = []


# ── Chat ──────────────────────────────────────────────────────────────────────

def respond(message, chat_history):
    from modules.ai_content import chat_with_ai
    lc_history = []
    for user_msg, bot_msg in chat_history:
        lc_history.append({"role": "user",  "parts": [user_msg]})
        lc_history.append({"role": "model", "parts": [bot_msg]})
    bot_reply = chat_with_ai(lc_history, message)
    chat_history.append({"role": "user", "content": message})
    chat_history.append({"role": "assistant", "content": bot_reply})
    return "", chat_history


# ── Charts ────────────────────────────────────────────────────────────────────

def load_charts():
    from modules.stock_tracker   import fetch_current_quotes, get_daily_movers, get_monthly_movers
    from modules.chart_generator import get_all_charts_as_pil
    try:
        quotes  = fetch_current_quotes()
        daily   = get_daily_movers(quotes)
        monthly = get_monthly_movers()
        img1, img2, img3 = get_all_charts_as_pil(daily, monthly)

        def fmt(mv, up):
            a = "▲" if up else "▼"
            return f"{'🟢' if up else '🔴'} **{mv['ticker']}** {a} {abs(mv['change_pct']):.2f}%  ${mv['price']:.2f}"

        summary  = "### 🚀 Today's Climbers\n" + "\n".join(fmt(m, True)  for m in daily["climbers"])
        summary += "\n\n### 📉 Today's Fallers\n"  + "\n".join(fmt(m, False) for m in daily["fallers"])
        summary += "\n\n### 🏔️ 30-Day Climbers\n" + "\n".join(f"🟢 **{m['ticker']}**  +{m['monthly_pct']:.1f}%" for m in monthly["climbers"])
        summary += "\n\n### 🕳️ 30-Day Fallers\n"  + "\n".join(f"🔴 **{m['ticker']}**  {m['monthly_pct']:.1f}%"  for m in monthly["fallers"])
        return img1, img2, img3, summary, f"✅ Updated {datetime.now().strftime('%H:%M:%S')}"
    except Exception as e:
        blank = Image.new("RGB", (900, 400), color=(10, 10, 20))
        return blank, blank, blank, f"Error: {e}", "❌ Error"


# ── Email ─────────────────────────────────────────────────────────────────────

def get_recipients_display():
    from modules.email_sender import load_recipients
    recipients = load_recipients()
    if not recipients:
        return "📭 No recipients yet."
    lines = [f"**{r.get('name') or r['email']}** — `{r['email']}`" for r in recipients]
    return f"**{len(recipients)} subscriber(s):**\n\n" + "\n\n".join(lines)


def handle_add(email, name):
    from modules.email_sender import add_recipient
    ok, msg = add_recipient(email, name)
    return msg, get_recipients_display(), "", ""


def handle_remove(email):
    from modules.email_sender import remove_recipient
    ok, msg = remove_recipient(email)
    return msg, get_recipients_display(), ""


def run_preview():
    from modules.sequencer      import run_daily_sequence
    from modules.chart_generator import get_all_charts_as_pil
    log_lines = []
    result = run_daily_sequence(progress_callback=lambda m: log_lines.append(m), send_email_flag=False)
    try:
        img1, img2, _ = get_all_charts_as_pil(result["daily_movers"], result["monthly_movers"])
    except:
        img1 = img2 = Image.new("RGB", (900, 400), color=(10, 10, 20))
    return "\n".join(log_lines), result.get("subject", ""), img1, img2


def run_send_all():
    from modules.sequencer import run_daily_sequence
    log_lines = []
    result = run_daily_sequence(progress_callback=lambda m: log_lines.append(m), send_email_flag=True)
    sent   = sum(1 for r in result.get("send_results", []) if r["success"])
    failed = len(result.get("send_results", [])) - sent
    return "\n".join(log_lines), f"✅ Sent: {sent}  |  ❌ Failed: {failed}"


# ── Leaderboard ───────────────────────────────────────────────────────────────

def compute_leaderboard():
    from modules.ai_ranker import rank_all_models
    try:
        ranked = rank_all_models(top_n=8)
        medals = ["🥇", "🥈", "🥉"]
        md     = ["### 🏆 AI Model Leaderboard\n",
                  "| Rank | Model | Company | Score | Δ | Strength |",
                  "|------|-------|---------|-------|---|----------|"]
        rows   = []
        for e in ranked:
            medal = medals[e["rank"]-1] if e["rank"] <= 3 else f"#{e['rank']}"
            md.append(f"| {medal} | **{e['model']}** | {e['company']} | `{e['composite']:.1f}` | {e['rank_change']} | {e.get('strength','')} |")
            dims = e["dimensions"]
            rows.append([
                f"#{e['rank']}", e["model"], e["company"], f"{e['composite']:.1f}", e["rank_change"],
                dims["reasoning"]["raw"], dims["coding"]["raw"], dims["speed"]["raw"],
                dims["cost_efficiency"]["raw"], dims["multimodal"]["raw"],
                dims["safety_align"]["raw"], dims["community"]["raw"], dims["context_window"]["raw"],
            ])
        md.append("\n\n**Weights:** Reasoning 22% · Coding 18% · Context 12% · Speed 12% · Cost 10% · Multimodal 10% · Safety 8% · Community 8%")
        return "\n".join(md), rows
    except Exception as e:
        return f"❌ Error: {e}", []


# ── Logs ──────────────────────────────────────────────────────────────────────

def refresh_logs(level_str):
    from modules.logger import get_log_text, get_log_files, Level
    text  = get_log_text(n=200, min_level=Level[level_str])
    files = get_log_files()
    return text, gr.Dropdown(choices=files)


def load_log_file(filepath):
    if not filepath:
        return ""
    from modules.logger import read_log_file
    return read_log_file(filepath)


# ── Build UI ──────────────────────────────────────────────────────────────────

CSS = """
body, .gradio-container { background: #08080f !important; color: #e0e0ff !important; }
footer { display: none !important; }
"""

with gr.Blocks(css=CSS, title="⚡ AI Email Bot") as app:

    gr.HTML("""
    <div style="background:linear-gradient(135deg,#0d0d1f,#1a1035);border:1px solid #252538;
    border-radius:16px;padding:28px;text-align:center;margin-bottom:8px;">
      <div style="font-family:monospace;font-size:26px;font-weight:600;color:#00e5a0;letter-spacing:3px;">⚡ AI EMAIL BOT</div>
      <div style="color:#7878a0;font-size:13px;margin-top:6px;font-family:monospace;">
        AI NEWS · STOCK MOVERS · DAILY BRIEFINGS · LANGCHAIN + GEMINI
      </div>
    </div>
    """)

    with gr.Tabs():

        # ── Chat ──────────────────────────────────────────────────────────────
        with gr.Tab("🤖 AI Chat"):
            gr.Markdown("Chat with AIPulse — ask about AI news, tools, models, or stocks.")
            chatbot  = gr.Chatbot(height=460, type="messages")
            with gr.Row():
                msg_in   = gr.Textbox(placeholder="Ask anything about AI...", scale=5, show_label=False)
                send_btn = gr.Button("Send", scale=1, variant="primary")
                clr_btn  = gr.Button("Clear", scale=1)
            send_btn.click(respond, [msg_in, chatbot], [msg_in, chatbot])
            msg_in.submit(respond,  [msg_in, chatbot], [msg_in, chatbot])
            clr_btn.click(lambda: [], outputs=[chatbot])

        # ── Charts ────────────────────────────────────────────────────────────
        with gr.Tab("📊 Stock Charts"):
            with gr.Row():
                refresh_btn  = gr.Button("🔄 Refresh Charts", variant="primary")
                chart_status = gr.Markdown("Click Refresh to load charts.")
            movers_md   = gr.Markdown("")
            gr.Markdown("#### Daily Movers")
            daily_img   = gr.Image(show_label=False)
            gr.Markdown("#### 30-Day Performance")
            monthly_img = gr.Image(show_label=False)
            gr.Markdown("#### 30-Day Sparklines")
            spark_img   = gr.Image(show_label=False)
            refresh_btn.click(load_charts, outputs=[daily_img, monthly_img, spark_img, movers_md, chart_status])

        # ── Email Manager ─────────────────────────────────────────────────────
        with gr.Tab("📧 Email Manager"):
            with gr.Row():
                with gr.Column(scale=1):
                    gr.Markdown("#### Add Subscriber")
                    email_in  = gr.Textbox(label="Email")
                    name_in   = gr.Textbox(label="Name (optional)")
                    add_btn   = gr.Button("➕ Add", variant="primary")
                    gr.Markdown("#### Remove Subscriber")
                    rem_in    = gr.Textbox(label="Email to remove")
                    rem_btn   = gr.Button("🗑️ Remove")
                    action_md = gr.Markdown("")
                with gr.Column(scale=2):
                    gr.Markdown("#### Subscribers")
                    recip_md  = gr.Markdown(get_recipients_display())

            gr.Markdown("---\n#### Send Briefing")
            with gr.Row():
                preview_btn  = gr.Button("👁️ Preview (no send)", variant="primary")
                send_all_btn = gr.Button("🚀 Send to All", variant="primary")
            subject_box = gr.Textbox(label="Generated Subject Line", interactive=False)
            send_status = gr.Markdown("")
            with gr.Row():
                prev_img1 = gr.Image(label="Daily Movers")
                prev_img2 = gr.Image(label="30-Day Performance")
            log_box = gr.Textbox(label="Pipeline Log", interactive=False, lines=8)

            add_btn.click(handle_add,    [email_in, name_in], [action_md, recip_md, email_in, name_in])
            rem_btn.click(handle_remove, [rem_in],            [action_md, recip_md, rem_in])
            preview_btn.click(run_preview,   outputs=[log_box, subject_box, prev_img1, prev_img2])
            send_all_btn.click(run_send_all, outputs=[log_box, send_status])

        # ── Leaderboard ───────────────────────────────────────────────────────
        with gr.Tab("🏆 AI Leaderboard"):
            gr.Markdown("Rankings from real benchmark data — weighted scoring engine, not an LLM guess.")
            rank_btn    = gr.Button("🔢 Compute Rankings", variant="primary")
            leader_md   = gr.Markdown("")
            score_table = gr.Dataframe(
                headers=["Rank","Model","Company","Score","Δ","Reasoning","Coding","Speed","Cost","Multimodal","Safety","Community","Context"],
                interactive=False,
            )
            rank_btn.click(compute_leaderboard, outputs=[leader_md, score_table])

        # ── Logs ──────────────────────────────────────────────────────────────
        with gr.Tab("📋 Logs"):
            gr.Markdown("Live system logs. ERROR/CRITICAL events trigger escalation emails.")
            with gr.Row():
                level_dd    = gr.Dropdown(["DEBUG","INFO","WARNING","ERROR","CRITICAL"], value="INFO", label="Min Level", scale=1)
                log_ref_btn = gr.Button("🔄 Refresh", variant="primary", scale=1)
            log_viewer  = gr.Textbox(label="Logs", interactive=False, lines=20, value="Click Refresh to load.")
            log_file_dd = gr.Dropdown(choices=[], label="Log files")
            load_btn    = gr.Button("📂 Load File")
            file_viewer = gr.Textbox(label="File Contents", interactive=False, lines=10)
            log_ref_btn.click(refresh_logs, [level_dd], [log_viewer, log_file_dd])
            load_btn.click(load_log_file,   [log_file_dd], [file_viewer])

        # ── Settings ──────────────────────────────────────────────────────────
        with gr.Tab("⚙️ Settings"):
            gr.Markdown("""
## Configuration

Set these as **HF Space Secrets** (Settings → Secrets):

| Secret | Required | Description |
|--------|----------|-------------|
| `GEMINI_API_KEY` | ✅ | [aistudio.google.com](https://aistudio.google.com) — free |
| `RESEND_API_KEY` | ✅ for email | [resend.com](https://resend.com) — free, 3k/month |
| `RESEND_FROM` | Optional | e.g. `AI Bot <you@yourdomain.com>` |
| `TRADEWATCH_API_KEY` | Optional | Mock data works without it |
| `ADMIN_EMAIL` | Optional | Receives error escalation alerts |
            """)

app.launch(server_name="0.0.0.0", server_port=7860, share=False)

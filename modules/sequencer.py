"""
modules/sequencer.py
LangChain-powered email sequencer.
Orchestrates: fetch data → rank AIs → generate content → build charts → send emails.
Full structured logging via modules.logger with escalation on errors.
"""

import os
import json
from datetime import datetime
from typing import Optional, Callable

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import PromptTemplate
from modules import logger

GEMINI_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY_HERE")


def build_langchain_llm():
    """Build a LangChain-wrapped Gemini LLM."""
    if GEMINI_KEY == "YOUR_GEMINI_API_KEY_HERE":
        logger.warning("sequencer", "GEMINI_API_KEY not set — LangChain LLM unavailable")
        return None
    return ChatGoogleGenerativeAI(
        model="gemini-1.5-flash",
        google_api_key=GEMINI_KEY,
        temperature=0.6,
        max_output_tokens=1024,
    )


# ── Subject line chain ─────────────────────────────────────────────────────────

SUBJECT_PROMPT = PromptTemplate(
    input_variables=["top_tool", "top_model", "top_model_score", "top_climber"],
    template=(
        "Write a compelling, curiosity-driving email subject line for a daily AI newsletter. "
        "Today's top tool: {top_tool}. Leading AI model: {top_model} (composite score: {top_model_score}/100). "
        "Biggest stock climber: {top_climber}. "
        "Max 65 characters. No quotes. No emojis at the start. Be punchy and specific."
    ),
)


def generate_subject_line(content: dict, movers: dict) -> str:
    """Use LangChain to generate an email subject line."""
    logger.info("sequencer", "Generating subject line via LangChain...")
    try:
        llm = build_langchain_llm()
        if not llm:
            fallback = f"⚡ AIPulse — {datetime.now().strftime('%b %d')} AI Briefing"
            logger.info("sequencer", f"Using fallback subject: {fallback}")
            return fallback

        chain = SUBJECT_PROMPT | llm

        rankings    = content.get("ai_rankings", [])
        top_tool    = content.get("top_tools", [{}])[0].get("name", "AI Tools")
        top_model   = rankings[0].get("model", "GPT-4o") if rankings else "GPT-4o"
        top_score   = f"{rankings[0].get('composite', 0):.1f}" if rankings else "N/A"
        top_climber = movers.get("climbers", [{}])[0].get("ticker", "NVDA")

        result = chain.invoke({
            "top_tool":         top_tool,
            "top_model":        top_model,
            "top_model_score":  top_score,
            "top_climber":      top_climber,
        })
        subject = getattr(result, "content", str(result)).strip()[:80]
        logger.info("sequencer", f"Subject line: {subject}")
        return subject

    except Exception as e:
        logger.error("sequencer", "Subject line generation failed", exc=e)
        return f"⚡ AIPulse — {datetime.now().strftime('%b %d')} AI Briefing"


# ── Main pipeline ──────────────────────────────────────────────────────────────

def run_daily_sequence(
    progress_callback: Optional[Callable] = None,
    send_email_flag: bool = True,
) -> dict:
    """
    Full daily sequence (8 steps):
    1. Fetch stock quotes
    2. Calculate movers (daily + monthly)
    3. Compute AI model rankings (weighted benchmark engine)
    4. Generate AI news + tools content via Gemini
    5. Build charts
    6. Generate subject line via LangChain
    7. Build HTML email
    8. Send to all recipients

    All steps are fully logged. Errors are escalated via email.
    Returns a summary dict including logs.
    """
    from modules.stock_tracker   import fetch_current_quotes, get_daily_movers, get_monthly_movers
    from modules.ai_content       import get_daily_ai_content
    from modules.ai_ranker        import rank_all_models, get_ranking_leaderboard_text
    from modules.chart_generator  import make_daily_movers_chart, make_monthly_movers_chart, make_sparkline_chart
    from modules.email_sender     import build_html_email, send_to_all, load_recipients

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    logger.info("sequencer", f"Starting daily sequence run_id={run_id}")

    if progress_callback:
        logger.register_ui_callback(progress_callback)

    step_errors = []
    result = {
        "status": "running", "run_id": run_id,
        "timestamp": datetime.now().isoformat(),
        "subject": "", "content": {}, "daily_movers": {},
        "monthly_movers": {}, "ai_rankings": [],
        "daily_chart_b64": "", "monthly_chart_b64": "", "spark_chart_b64": "",
        "html_body": "", "send_results": [], "log": [],
    }

    # Step 1: Stock quotes
    logger.info("sequencer", "Step 1/8 — Fetching AI sector stock quotes...")
    try:
        quotes = fetch_current_quotes()
        logger.info("sequencer", f"Fetched quotes for {len(quotes)} tickers")
    except Exception as e:
        logger.error("sequencer", "Stock quote fetch failed", exc=e)
        step_errors.append("quotes")
        quotes = {}

    # Step 2: Stock movers
    logger.info("sequencer", "Step 2/8 — Calculating daily & 30-day movers...")
    try:
        daily_movers   = get_daily_movers(quotes) if quotes else {"climbers": [], "fallers": []}
        monthly_movers = get_monthly_movers()
        result["daily_movers"]   = daily_movers
        result["monthly_movers"] = monthly_movers
        top_c = daily_movers["climbers"][0]["ticker"] if daily_movers.get("climbers") else "N/A"
        logger.info("sequencer", f"Top daily climber: {top_c}")
    except Exception as e:
        logger.error("sequencer", "Mover calculation failed", exc=e)
        step_errors.append("movers")
        daily_movers   = {"climbers": [], "fallers": []}
        monthly_movers = {"climbers": [], "fallers": [], "all": []}

    # Step 3: AI rankings
    logger.info("sequencer", "Step 3/8 — Computing AI model rankings...")
    try:
        ai_rankings = rank_all_models(top_n=8)
        result["ai_rankings"] = ai_rankings
        logger.info("sequencer",
            f"#1={ai_rankings[0]['model']} ({ai_rankings[0]['composite']:.1f}) "
            f"#2={ai_rankings[1]['model']} ({ai_rankings[1]['composite']:.1f}) "
            f"#3={ai_rankings[2]['model']} ({ai_rankings[2]['composite']:.1f})"
        )
    except Exception as e:
        logger.critical("sequencer", "AI ranking engine failed", exc=e)
        step_errors.append("rankings")
        ai_rankings = []

    # Step 4: AI content
    logger.info("sequencer", "Step 4/8 — Generating AI news + tools via Gemini...")
    try:
        content = get_daily_ai_content()
        result["content"] = content
        logger.info("sequencer", "Content generated successfully")
    except Exception as e:
        logger.error("sequencer", "AI content generation failed", exc=e)
        step_errors.append("content")
        content = {"news_summary": "", "top_tools": [], "ai_rankings": ai_rankings}

    # Step 5: Charts
    logger.info("sequencer", "Step 5/8 — Building Plotly stock charts...")
    try:
        daily_chart_b64   = make_daily_movers_chart(daily_movers)
        monthly_chart_b64 = make_monthly_movers_chart(monthly_movers)
        spark_chart_b64   = make_sparkline_chart(monthly_movers)
        result.update(daily_chart_b64=daily_chart_b64,
                      monthly_chart_b64=monthly_chart_b64,
                      spark_chart_b64=spark_chart_b64)
        logger.info("sequencer", "All 3 charts generated")
    except Exception as e:
        logger.error("sequencer", "Chart generation failed", exc=e)
        step_errors.append("charts")
        daily_chart_b64 = monthly_chart_b64 = spark_chart_b64 = ""

    # Step 6: Subject line
    logger.info("sequencer", "Step 6/8 — Generating subject line via LangChain...")
    subject = generate_subject_line(content, daily_movers)
    result["subject"] = subject

    # Step 7: Build email
    logger.info("sequencer", "Step 7/8 — Building HTML email...")
    try:
        html_body = build_html_email(
            content, daily_movers, monthly_movers,
            daily_chart_b64, monthly_chart_b64, spark_chart_b64,
        )
        result["html_body"] = html_body
        logger.info("sequencer", f"Email built ({len(html_body):,} chars)")
    except Exception as e:
        logger.critical("sequencer", "Email build failed", exc=e)
        step_errors.append("email_build")
        html_body = ""

    # Step 8: Send
    send_results = []
    if send_email_flag and html_body:
        recipients = load_recipients()
        if recipients:
            logger.info("sequencer", f"Step 8/8 — Sending to {len(recipients)} recipient(s)...")
            send_results = send_to_all(subject, html_body)
            sent   = sum(1 for r in send_results if r["success"])
            failed = len(send_results) - sent
            if failed > 0:
                logger.warning("sequencer", f"{failed} delivery failure(s)",
                               extra={"failed": [r for r in send_results if not r["success"]]})
            logger.info("sequencer", f"Delivery: {sent} sent, {failed} failed")
        else:
            logger.warning("sequencer", "No recipients configured — send skipped")
    elif not send_email_flag:
        logger.info("sequencer", "Step 8/8 — Preview mode, send skipped")
    else:
        logger.error("sequencer", "Email body empty — send aborted")

    result["send_results"] = send_results
    result["status"]       = "completed" if not step_errors else f"completed_with_errors:{step_errors}"
    result["log"]          = [e["message"] for e in logger.get_recent_logs(50)]

    if step_errors:
        logger.warning("sequencer", f"Sequence done with errors in: {step_errors}")
    else:
        logger.info("sequencer", f"Sequence {run_id} completed cleanly")

    if progress_callback:
        logger.unregister_ui_callback(progress_callback)

    return result

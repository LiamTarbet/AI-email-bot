"""
modules/logger.py
─────────────────────────────────────────────────────────────────────────────
AIPulse structured logger with:
  - Log levels: DEBUG / INFO / WARNING / ERROR / CRITICAL
  - File logging with daily rotation (logs/aipulse_YYYY-MM-DD.log)
  - Console logging with color
  - Escalation system: WARNING+ triggers in-app alerts, ERROR/CRITICAL sends
    an immediate escalation email to the admin address
  - Log viewer callable from Gradio UI
─────────────────────────────────────────────────────────────────────────────
"""

import os
import json
import smtplib
import ssl
import traceback
from datetime import datetime
from enum import IntEnum
from pathlib import Path
from typing import Optional, Callable


# ── Log levels ────────────────────────────────────────────────────────────────

class Level(IntEnum):
    DEBUG    = 10
    INFO     = 20
    WARNING  = 30
    ERROR    = 40
    CRITICAL = 50


LEVEL_LABELS = {
    Level.DEBUG:    "DEBUG",
    Level.INFO:     "INFO ",
    Level.WARNING:  "WARN ",
    Level.ERROR:    "ERROR",
    Level.CRITICAL: "CRIT ",
}

# ANSI colors for console
LEVEL_COLORS = {
    Level.DEBUG:    "\033[36m",   # cyan
    Level.INFO:     "\033[32m",   # green
    Level.WARNING:  "\033[33m",   # yellow
    Level.ERROR:    "\033[31m",   # red
    Level.CRITICAL: "\033[35m",   # magenta
}
RESET = "\033[0m"


# ── Config ────────────────────────────────────────────────────────────────────

LOG_DIR         = Path("logs")
MIN_LEVEL       = Level[os.getenv("LOG_LEVEL", "INFO").upper()]
ESCALATE_LEVEL  = Level.ERROR          # escalate on ERROR and CRITICAL
ADMIN_EMAIL     = os.getenv("ADMIN_EMAIL", os.getenv("GMAIL_USER", ""))
GMAIL_USER      = os.getenv("GMAIL_USER", "")
GMAIL_APP_PASS  = os.getenv("GMAIL_APP_PASSWORD", "")

# In-memory ring buffer for the Gradio log viewer (last 500 entries)
_ring_buffer: list[dict] = []
RING_BUFFER_SIZE = 500

# External progress callbacks registered by the UI
_ui_callbacks: list[Callable] = []


# ── Core logger ───────────────────────────────────────────────────────────────

def _log_file() -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return LOG_DIR / f"aipulse_{datetime.now().strftime('%Y-%m-%d')}.log"


def _format(level: Level, module: str, message: str, ts: datetime) -> str:
    label = LEVEL_LABELS[level]
    return f"[{ts.strftime('%Y-%m-%d %H:%M:%S')}] [{label}] [{module:20s}] {message}"


def log(
    level: Level,
    module: str,
    message: str,
    exc: Optional[Exception] = None,
    extra: Optional[dict] = None,
):
    """Core log function. All other helpers route through here."""
    if level < MIN_LEVEL:
        return

    ts       = datetime.now()
    tb_str   = ""
    if exc:
        tb_str = "\n" + "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))

    full_msg = message + tb_str
    line     = _format(level, module, full_msg, ts)

    # ── Console ──
    color = LEVEL_COLORS.get(level, "")
    print(f"{color}{line}{RESET}")

    # ── File ──
    try:
        with open(_log_file(), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

    # ── Ring buffer ──
    entry = {
        "ts":      ts.isoformat(),
        "level":   LEVEL_LABELS[level].strip(),
        "module":  module,
        "message": full_msg,
        "extra":   extra or {},
    }
    _ring_buffer.append(entry)
    if len(_ring_buffer) > RING_BUFFER_SIZE:
        _ring_buffer.pop(0)

    # ── UI callbacks (Gradio progress) ──
    for cb in _ui_callbacks:
        try:
            cb(f"[{LEVEL_LABELS[level].strip()}] {message}")
        except Exception:
            pass

    # ── Escalation ──
    if level >= ESCALATE_LEVEL:
        _escalate(level, module, full_msg, ts, extra)


# ── Convenience wrappers ──────────────────────────────────────────────────────

def debug(module: str, msg: str, **kw):
    log(Level.DEBUG, module, msg, **kw)

def info(module: str, msg: str, **kw):
    log(Level.INFO, module, msg, **kw)

def warning(module: str, msg: str, **kw):
    log(Level.WARNING, module, msg, **kw)

def error(module: str, msg: str, exc: Optional[Exception] = None, **kw):
    log(Level.ERROR, module, msg, exc=exc, **kw)

def critical(module: str, msg: str, exc: Optional[Exception] = None, **kw):
    log(Level.CRITICAL, module, msg, exc=exc, **kw)


# ── Escalation email ──────────────────────────────────────────────────────────

def _escalate(level: Level, module: str, message: str, ts: datetime, extra: Optional[dict]):
    """Send an escalation email to ADMIN_EMAIL for ERROR/CRITICAL events."""
    if not ADMIN_EMAIL or not GMAIL_USER or not GMAIL_APP_PASS:
        return   # credentials not configured — skip silently
    if ADMIN_EMAIL == GMAIL_USER and not GMAIL_APP_PASS:
        return

    label    = LEVEL_LABELS[level].strip()
    subject  = f"🚨 AIPulse [{label}] — {module}: {message[:60]}"
    extra_md = json.dumps(extra, indent=2) if extra else "—"

    html = f"""<!DOCTYPE html>
<html>
<head>
<style>
  body {{ background:#09090f; color:#e0e0ff; font-family:monospace; padding:20px; }}
  .box {{ background:#1a0010; border:1px solid #ff446640; border-radius:10px; padding:20px; max-width:640px; }}
  .badge {{ display:inline-block; background:#ff446620; color:#ff4466; border:1px solid #ff446650;
            padding:4px 12px; border-radius:6px; font-size:13px; font-weight:600; margin-bottom:16px; }}
  .row {{ margin-bottom:10px; }}
  .lbl {{ color:#888; font-size:12px; text-transform:uppercase; letter-spacing:1px; }}
  .val {{ color:#e0e0ff; font-size:14px; margin-top:2px; }}
  pre  {{ background:#0d0d16; border:1px solid #2a2a3d; border-radius:6px;
          padding:12px; color:#ff9999; font-size:12px; white-space:pre-wrap; word-break:break-all; }}
</style>
</head>
<body>
<div class="box">
  <div class="badge">⚠ {label} ESCALATION</div>
  <div class="row"><div class="lbl">Timestamp</div><div class="val">{ts.strftime('%Y-%m-%d %H:%M:%S UTC')}</div></div>
  <div class="row"><div class="lbl">Module</div><div class="val">{module}</div></div>
  <div class="row"><div class="lbl">Message</div><div class="val">{message[:500]}</div></div>
  <div class="row"><div class="lbl">Extra context</div><pre>{extra_md}</pre></div>
  <hr style="border-color:#2a2a3d;margin:16px 0">
  <div style="color:#666;font-size:11px;">AIPulse automated escalation system</div>
</div>
</body>
</html>"""

    try:
        from email.mime.multipart import MIMEMultipart
        from email.mime.text      import MIMEText
        msg          = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"AIPulse Alerts <{GMAIL_USER}>"
        msg["To"]      = ADMIN_EMAIL
        msg.attach(MIMEText(html, "html"))

        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASS)
            server.sendmail(GMAIL_USER, ADMIN_EMAIL, msg.as_string())

        # NOTE: avoid calling log() here to prevent infinite recursion
        print(f"\033[35m[ESCALATION] Alert email sent to {ADMIN_EMAIL}\033[0m")
    except Exception as e:
        print(f"\033[31m[ESCALATION] Failed to send alert: {e}\033[0m")


# ── UI helpers ────────────────────────────────────────────────────────────────

def register_ui_callback(cb: Callable):
    """Register a callback that receives each log line (used by Gradio progress)."""
    _ui_callbacks.append(cb)


def unregister_ui_callback(cb: Callable):
    if cb in _ui_callbacks:
        _ui_callbacks.remove(cb)


def get_recent_logs(n: int = 100, min_level: Level = Level.DEBUG) -> list[dict]:
    """Return the last n entries from the ring buffer at or above min_level."""
    filtered = [e for e in _ring_buffer if Level[e["level"]] >= min_level]
    return filtered[-n:]


def get_log_text(n: int = 150, min_level: Level = Level.INFO) -> str:
    """Format recent logs as a plain-text string for Gradio Textbox."""
    entries = get_recent_logs(n, min_level)
    if not entries:
        return "No log entries yet."
    lines = []
    for e in entries:
        ts_short = e["ts"][11:19]  # HH:MM:SS
        lines.append(f"[{ts_short}] [{e['level']:5s}] [{e['module']:20s}] {e['message']}")
    return "\n".join(lines)


def get_log_files() -> list[str]:
    """List available log files."""
    if not LOG_DIR.exists():
        return []
    return sorted((str(p) for p in LOG_DIR.glob("aipulse_*.log")), reverse=True)


def read_log_file(filepath: str) -> str:
    """Read a log file and return its contents."""
    try:
        with open(filepath, encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading {filepath}: {e}"

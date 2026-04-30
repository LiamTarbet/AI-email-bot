"""
modules/stock_tracker.py
Fetches AI-related stock data from TradeWatch API.
Calculates daily movers + 30-day trend climbers/fallers.
"""

import requests
import json
import os
from datetime import datetime, timedelta
from typing import Optional
import random

# ── TradeWatch API config ──────────────────────────────────────────────────────
TRADEWATCH_API_KEY = os.getenv("TRADEWATCH_API_KEY", "YOUR_TRADEWATCH_API_KEY_HERE")
TRADEWATCH_BASE    = "https://api.tradewatch.io/v1"

# Core AI-sector tickers
AI_TICKERS = {
    "NVDA":  "NVIDIA",
    "MSFT":  "Microsoft",
    "GOOGL": "Alphabet",
    "META":  "Meta",
    "AMZN":  "Amazon",
    "AMD":   "AMD",
    "INTC":  "Intel",
    "TSLA":  "Tesla",
    "ORCL":  "Oracle",
    "CRM":   "Salesforce",
    "PLTR":  "Palantir",
    "AI":    "C3.ai",
    "SOUN":  "SoundHound",
    "BBAI":  "BigBear.ai",
    "IONQ":  "IonQ",
}


def _headers():
    return {
        "Authorization": f"Bearer {TRADEWATCH_API_KEY}",
        "Content-Type": "application/json",
    }


def fetch_current_quotes() -> dict:
    """Fetch current quotes for all AI tickers."""
    if TRADEWATCH_API_KEY == "YOUR_TRADEWATCH_API_KEY_HERE":
        return _mock_quotes()

    results = {}
    for ticker in AI_TICKERS:
        try:
            resp = requests.get(
                f"{TRADEWATCH_BASE}/stocks/{ticker}/quote",
                headers=_headers(),
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                results[ticker] = {
                    "name":    AI_TICKERS[ticker],
                    "price":   data.get("price", 0),
                    "change":  data.get("change", 0),
                    "change_pct": data.get("change_percent", 0),
                    "volume":  data.get("volume", 0),
                    "timestamp": data.get("timestamp", datetime.utcnow().isoformat()),
                }
        except Exception as e:
            print(f"[StockTracker] Error fetching {ticker}: {e}")
    return results if results else _mock_quotes()


def fetch_historical(ticker: str, days: int = 30) -> list:
    """Fetch historical OHLC data for a ticker."""
    if TRADEWATCH_API_KEY == "YOUR_TRADEWATCH_API_KEY_HERE":
        return _mock_history(ticker, days)

    try:
        end   = datetime.utcnow()
        start = end - timedelta(days=days)
        resp  = requests.get(
            f"{TRADEWATCH_BASE}/stocks/{ticker}/history",
            headers=_headers(),
            params={
                "from": start.strftime("%Y-%m-%d"),
                "to":   end.strftime("%Y-%m-%d"),
                "interval": "1d",
            },
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json().get("candles", [])
    except Exception as e:
        print(f"[StockTracker] History error {ticker}: {e}")
    return _mock_history(ticker, days)


# ── Calculations ───────────────────────────────────────────────────────────────

def get_daily_movers(quotes: dict) -> dict:
    """Return top 3 climbers and top 3 fallers for TODAY."""
    sorted_tickers = sorted(
        quotes.items(),
        key=lambda x: x[1].get("change_pct", 0),
        reverse=True,
    )
    climbers = sorted_tickers[:3]
    fallers  = sorted_tickers[-3:][::-1]
    return {
        "climbers": [
            {
                "ticker":     t,
                "name":       d["name"],
                "price":      d["price"],
                "change_pct": round(d["change_pct"], 2),
                "change":     round(d["change"], 2),
            }
            for t, d in climbers
        ],
        "fallers": [
            {
                "ticker":     t,
                "name":       d["name"],
                "price":      d["price"],
                "change_pct": round(d["change_pct"], 2),
                "change":     round(d["change"], 2),
            }
            for t, d in fallers
        ],
    }


def get_monthly_movers() -> dict:
    """
    Calculate 30-day performance for each ticker.
    Compares current price vs price 30 days ago.
    Returns top 3 climbers + fallers over the month.
    """
    monthly_perf = []

    for ticker, name in AI_TICKERS.items():
        history = fetch_historical(ticker, days=31)
        if len(history) >= 2:
            # Oldest close in the window
            oldest_close = history[0].get("close", history[0].get("c", 0))
            # Most recent close
            newest_close = history[-1].get("close", history[-1].get("c", 0))

            if oldest_close and oldest_close != 0:
                pct_change = ((newest_close - oldest_close) / oldest_close) * 100
                abs_change = newest_close - oldest_close

                # Volatility: std dev of daily % changes
                closes = [
                    c.get("close", c.get("c", 0)) for c in history if c.get("close", c.get("c"))
                ]
                if len(closes) > 1:
                    daily_changes = [
                        ((closes[i] - closes[i - 1]) / closes[i - 1]) * 100
                        for i in range(1, len(closes))
                    ]
                    import statistics
                    volatility = statistics.stdev(daily_changes) if len(daily_changes) > 1 else 0
                else:
                    volatility = 0

                monthly_perf.append({
                    "ticker":          ticker,
                    "name":            name,
                    "price_30d_ago":   round(oldest_close, 2),
                    "current_price":   round(newest_close, 2),
                    "monthly_pct":     round(pct_change, 2),
                    "monthly_abs":     round(abs_change, 2),
                    "volatility_30d":  round(volatility, 2),
                    "history":         closes,
                })

    sorted_perf = sorted(monthly_perf, key=lambda x: x["monthly_pct"], reverse=True)
    return {
        "climbers": sorted_perf[:3],
        "fallers":  sorted_perf[-3:][::-1],
        "all":      sorted_perf,
    }


# ── Mock data (used when no API key is set) ───────────────────────────────────

def _mock_quotes() -> dict:
    """Realistic mock quotes for demo / no-key mode."""
    base_prices = {
        "NVDA": 875.40, "MSFT": 415.20, "GOOGL": 178.50, "META": 545.30,
        "AMZN": 195.80, "AMD": 162.40,  "INTC": 31.20,   "TSLA": 248.50,
        "ORCL": 138.90, "CRM":  298.70, "PLTR": 28.40,   "AI":   35.60,
        "SOUN": 7.82,   "BBAI": 3.14,   "IONQ": 12.50,
    }
    random.seed(datetime.now().day)  # Consistent within a day
    results = {}
    for ticker, base in base_prices.items():
        change_pct = round(random.uniform(-6.5, 7.2), 2)
        change     = round(base * change_pct / 100, 2)
        results[ticker] = {
            "name":       AI_TICKERS[ticker],
            "price":      round(base + change, 2),
            "change":     change,
            "change_pct": change_pct,
            "volume":     random.randint(5_000_000, 80_000_000),
            "timestamp":  datetime.utcnow().isoformat(),
        }
    return results


def _mock_history(ticker: str, days: int = 30) -> list:
    """Generate plausible 30-day price history."""
    base_prices = {
        "NVDA": 830.0, "MSFT": 400.0, "GOOGL": 170.0, "META": 510.0,
        "AMZN": 185.0, "AMD":  150.0, "INTC":  29.0,  "TSLA": 230.0,
        "ORCL": 130.0, "CRM":  285.0, "PLTR":  24.0,  "AI":   30.0,
        "SOUN": 6.50,  "BBAI": 2.80,  "IONQ":  10.50,
    }
    seed_val = sum(ord(c) for c in ticker)
    rng      = random.Random(seed_val)
    base     = base_prices.get(ticker, 100.0)
    history  = []
    price    = base
    for i in range(days):
        day_change = rng.uniform(-0.03, 0.035)
        price      = max(0.5, price * (1 + day_change))
        history.append({
            "date":  (datetime.utcnow() - timedelta(days=days - i)).strftime("%Y-%m-%d"),
            "open":  round(price * rng.uniform(0.99, 1.01), 2),
            "high":  round(price * rng.uniform(1.00, 1.03), 2),
            "low":   round(price * rng.uniform(0.97, 1.00), 2),
            "close": round(price, 2),
            "volume": rng.randint(5_000_000, 80_000_000),
        })
    return history

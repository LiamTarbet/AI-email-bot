"""
modules/ai_ranker.py
─────────────────────────────────────────────────────────────────────────────
Calculates AI model rankings using a weighted multi-factor scoring engine.

Scoring dimensions (weights sum to 1.0):
  - Reasoning       0.22  (MMLU, GPQA, ARC benchmarks)
  - Coding          0.18  (HumanEval, SWE-bench, LiveCodeBench)
  - Context window  0.12  (normalised tokens)
  - Speed           0.12  (tokens/sec, normalised)
  - Cost efficiency 0.10  (price per 1M tokens, inverted + normalised)
  - Multimodal      0.10  (vision/audio/video capability score)
  - Safety/Align    0.08  (TruthfulQA, BBQ, Constitutional)
  - Community       0.08  (API availability, integrations, ecosystem)

Each dimension is scored 0–100.  Final composite = weighted sum.
Rankings are recalculated fresh every run so they reflect the latest data
embedded in the module (update BENCHMARK_DATA as new evals drop).

Also exposes score_delta vs previous run (stored in data/ranking_history.json)
so the email can show "▲2" or "▼1" rank changes.
─────────────────────────────────────────────────────────────────────────────
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── Weights ───────────────────────────────────────────────────────────────────

WEIGHTS = {
    "reasoning":       0.22,
    "coding":          0.18,
    "context_window":  0.12,
    "speed":           0.12,
    "cost_efficiency": 0.10,
    "multimodal":      0.10,
    "safety_align":    0.08,
    "community":       0.08,
}

assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9, "Weights must sum to 1.0"

# ── Benchmark data ────────────────────────────────────────────────────────────
# Scores are 0–100 per dimension.  Update these as new benchmarks are published.
# Sources: MMLU/GPQA from Papers With Code; HumanEval/SWE from model cards;
# speed from Artificial Analysis; cost from official pricing pages.

BENCHMARK_DATA: dict[str, dict] = {
    "GPT-4o": {
        "company":        "OpenAI",
        "released":       "May 2024",
        "context_tokens": 128_000,
        "reasoning":      88,   # MMLU 88.7, GPQA 53.6
        "coding":         82,   # HumanEval 90.2, SWE-bench 33.2
        "speed":          78,   # ~120 tok/s (Artificial Analysis)
        "cost_efficiency":62,   # $5/$15 per 1M in/out
        "multimodal":     92,   # vision + audio + realtime
        "safety_align":   80,   # TruthfulQA 85
        "community":      95,   # largest plugin/API ecosystem
        "context_window": 0,    # computed below
    },
    "Claude 3.5 Sonnet": {
        "company":        "Anthropic",
        "released":       "June 2024",
        "context_tokens": 200_000,
        "reasoning":      90,   # MMLU 90.4, GPQA 59.4
        "coding":         93,   # HumanEval 92.0, SWE-bench 49.0 (best in class)
        "speed":          72,   # ~85 tok/s
        "cost_efficiency":65,   # $3/$15 per 1M in/out
        "multimodal":     78,   # vision, no native audio
        "safety_align":   92,   # Constitutional AI, low hallucination
        "community":      82,   # strong API, growing integrations
        "context_window": 0,
    },
    "Gemini 1.5 Pro": {
        "company":        "Google DeepMind",
        "released":       "February 2024",
        "context_tokens": 2_000_000,
        "reasoning":      86,   # MMLU 85.9, GPQA 46.2
        "coding":         77,   # HumanEval 84.1
        "speed":          65,   # variable via API
        "cost_efficiency":70,   # $3.50/$10.50 per 1M
        "multimodal":     88,   # video, audio, image, docs
        "safety_align":   81,
        "community":      85,   # Google Workspace + Search grounding
        "context_window": 0,
    },
    "Gemini 1.5 Flash": {
        "company":        "Google DeepMind",
        "released":       "May 2024",
        "context_tokens": 1_000_000,
        "reasoning":      78,
        "coding":         71,
        "speed":          92,   # very fast
        "cost_efficiency":94,   # $0.075/$0.30 per 1M — cheapest tier
        "multimodal":     82,
        "safety_align":   79,
        "community":      80,
        "context_window": 0,
    },
    "GPT-4o mini": {
        "company":        "OpenAI",
        "released":       "July 2024",
        "context_tokens": 128_000,
        "reasoning":      76,
        "coding":         75,
        "speed":          89,
        "cost_efficiency":90,   # $0.15/$0.60 per 1M
        "multimodal":     80,
        "safety_align":   78,
        "community":      88,
        "context_window": 0,
    },
    "Llama 3.1 405B": {
        "company":        "Meta",
        "released":       "July 2024",
        "context_tokens": 128_000,
        "reasoning":      85,   # MMLU 88.6
        "coding":         81,
        "speed":          45,   # self-hosted dependent
        "cost_efficiency":55,   # self-host costs vary; API ~$3/$3
        "multimodal":     40,   # text-only flagship
        "safety_align":   74,
        "community":      76,   # open weights = massive community
        "context_window": 0,
    },
    "Mistral Large 2": {
        "company":        "Mistral AI",
        "released":       "July 2024",
        "context_tokens": 128_000,
        "reasoning":      81,
        "coding":         80,   # HumanEval 92 (reported)
        "speed":          74,
        "cost_efficiency":72,   # $3/$9 per 1M
        "multimodal":     38,   # text-only
        "safety_align":   76,
        "community":      68,
        "context_window": 0,
    },
    "o1-preview": {
        "company":        "OpenAI",
        "released":       "September 2024",
        "context_tokens": 128_000,
        "reasoning":      96,   # GPQA 78.3 — best reasoning benchmark
        "coding":         88,   # SWE-bench 41.3
        "speed":          28,   # slow chain-of-thought
        "cost_efficiency":25,   # $15/$60 per 1M
        "multimodal":     60,   # limited vision
        "safety_align":   87,
        "community":      70,   # API access limited
        "context_window": 0,
    },
}

# ── Context window normalisation ──────────────────────────────────────────────

_MAX_CONTEXT = max(v["context_tokens"] for v in BENCHMARK_DATA.values())

for _model_data in BENCHMARK_DATA.values():
    import math
    # Log-scale normalisation: log(tokens) / log(max_tokens) * 100
    _model_data["context_window"] = round(
        (math.log(_model_data["context_tokens"] + 1) /
         math.log(_MAX_CONTEXT + 1)) * 100, 1
    )

# ── Scoring engine ────────────────────────────────────────────────────────────

HISTORY_FILE = Path("data/ranking_history.json")


def _load_history() -> dict:
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_history(scores: dict):
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump(scores, f, indent=2)
    except Exception:
        pass


def compute_composite_score(model_name: str) -> dict:
    """
    Compute weighted composite score for a single model.
    Returns dict with per-dimension scores + composite.
    """
    data = BENCHMARK_DATA[model_name]
    dim_scores = {}
    composite  = 0.0

    for dim, weight in WEIGHTS.items():
        raw_score      = data.get(dim, 0)
        weighted_score = raw_score * weight
        composite     += weighted_score
        dim_scores[dim] = {
            "raw":      raw_score,
            "weight":   weight,
            "weighted": round(weighted_score, 3),
        }

    return {
        "model":        model_name,
        "company":      data["company"],
        "released":     data["released"],
        "context_k":    data["context_tokens"] // 1000,
        "composite":    round(composite, 2),
        "dimensions":   dim_scores,
    }


def rank_all_models(top_n: int = 8) -> list[dict]:
    """
    Score every model in BENCHMARK_DATA, sort by composite score descending,
    attach rank + rank_delta vs previous run, save history.
    Returns top_n ranked models.
    """
    from modules import logger

    history    = _load_history()
    prev_ranks = history.get("ranks", {})   # {model_name: rank_int}

    scored = [compute_composite_score(m) for m in BENCHMARK_DATA]
    scored.sort(key=lambda x: x["composite"], reverse=True)

    today     = datetime.now().strftime("%Y-%m-%d")
    new_ranks = {}

    for i, entry in enumerate(scored):
        rank      = i + 1
        model     = entry["model"]
        prev_rank = prev_ranks.get(model)

        if prev_rank is None:
            delta_label = "NEW"
            delta_num   = 0
        else:
            delta_num   = prev_rank - rank   # positive = climbed, negative = dropped
            if delta_num > 0:
                delta_label = f"▲{delta_num}"
            elif delta_num < 0:
                delta_label = f"▼{abs(delta_num)}"
            else:
                delta_label = "—"

        entry["rank"]        = rank
        entry["rank_delta"]  = delta_num
        entry["rank_change"] = delta_label
        new_ranks[model]     = rank

    # Persist new ranks
    _save_history({"date": today, "ranks": new_ranks})

    logger.info("ai_ranker", f"Rankings computed for {len(scored)} models. "
                f"Top: {scored[0]['model']} ({scored[0]['composite']:.1f})")

    return scored[:top_n]


def get_top3_ranked() -> list[dict]:
    """
    Convenience: return the top-3 models formatted for email/display,
    including a human-readable score breakdown.
    """
    all_ranked = rank_all_models(top_n=3)
    results    = []

    for entry in all_ranked:
        dims = entry["dimensions"]

        # Build a readable strength string from the top-2 weighted dims
        top_dims = sorted(
            dims.items(), key=lambda x: x[1]["weighted"], reverse=True
        )[:2]
        strength = " + ".join(
            d.replace("_", " ").title() for d, _ in top_dims
        )

        # Score bar (visual 0-100 → chars)
        bar_filled = int(entry["composite"] / 5)   # 0-20 chars
        bar = "█" * bar_filled + "░" * (20 - bar_filled)

        results.append({
            "rank":          entry["rank"],
            "model":         entry["model"],
            "company":       entry["company"],
            "released":      entry["released"],
            "context_k":     entry["context_k"],
            "composite":     entry["composite"],
            "score_bar":     bar,
            "strength":      strength,
            "rank_change":   entry["rank_change"],
            "rank_delta":    entry["rank_delta"],
            "score_breakdown": {
                d: v["raw"] for d, v in dims.items()
            },
            "score_reason":  _build_score_reason(entry),
        })

    return results


def _build_score_reason(entry: dict) -> str:
    """Generate a 2-sentence human-readable score justification."""
    dims     = entry["dimensions"]
    model    = entry["model"]
    comp     = entry["composite"]
    top_dims = sorted(dims.items(), key=lambda x: x[1]["raw"], reverse=True)[:2]
    bot_dims = sorted(dims.items(), key=lambda x: x[1]["raw"])[:1]

    strong_1 = top_dims[0][0].replace("_", " ")
    strong_2 = top_dims[1][0].replace("_", " ")
    weak_1   = bot_dims[0][0].replace("_", " ")
    s1_score = top_dims[0][1]["raw"]
    s2_score = top_dims[1][1]["raw"]

    return (
        f"{model} scores {comp:.1f}/100 overall, leading on {strong_1} ({s1_score}/100) "
        f"and {strong_2} ({s2_score}/100). "
        f"Its relative weakness is {weak_1}, which factors into the weighted composite score."
    )


def get_ranking_leaderboard_text() -> str:
    """Return a formatted leaderboard string for display in chat / logs."""
    all_ranked = rank_all_models(top_n=8)
    medals     = ["🥇", "🥈", "🥉"]
    lines      = ["╔══ AIPulse AI Model Leaderboard ══╗"]

    for entry in all_ranked:
        medal  = medals[entry["rank"] - 1] if entry["rank"] <= 3 else f"#{entry['rank']} "
        change = entry["rank_change"]
        lines.append(
            f"  {medal} {entry['model']:22s} "
            f"[{entry['composite']:5.1f}/100]  {change:>5}"
        )

    lines.append("╚══════════════════════════════════╝")
    return "\n".join(lines)

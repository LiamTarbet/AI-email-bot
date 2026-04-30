"""
modules/chart_generator.py
Generates beautiful stock charts using Plotly:
  - Daily movers bar chart (climbers + fallers)
  - Monthly movers comparison
  - 30-day sparkline trends
"""

import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import pandas as pd
import os
import io
import base64
from datetime import datetime


# ── Color palette ─────────────────────────────────────────────────────────────
COLORS = {
    "bg":          "#0a0a0f",
    "surface":     "#111118",
    "card":        "#16161f",
    "border":      "#2a2a3d",
    "text":        "#e8e8ff",
    "text_dim":    "#8888aa",
    "green":       "#00e5a0",
    "green_dim":   "#00e5a020",
    "red":         "#ff4466",
    "red_dim":     "#ff446620",
    "accent":      "#7c6af7",
    "accent2":     "#00d4ff",
    "gold":        "#ffd166",
}

PLOTLY_LAYOUT = dict(
    paper_bgcolor=COLORS["bg"],
    plot_bgcolor=COLORS["surface"],
    font=dict(family="'IBM Plex Mono', monospace", color=COLORS["text"], size=12),
    margin=dict(l=20, r=20, t=50, b=20),
)


def make_daily_movers_chart(movers: dict) -> str:
    """
    Bar chart: today's top 3 climbers (green) + top 3 fallers (red).
    Returns base64-encoded PNG string.
    """
    climbers = movers["climbers"]
    fallers  = movers["fallers"]

    labels  = [f"{s['ticker']}\n{s['name']}" for s in climbers] + \
              [f"{s['ticker']}\n{s['name']}" for s in fallers]
    values  = [s["change_pct"] for s in climbers] + [s["change_pct"] for s in fallers]
    colors  = [COLORS["green"]] * 3 + [COLORS["red"]] * 3
    borders = [COLORS["green"]] * 3 + [COLORS["red"]] * 3

    fig = go.Figure(go.Bar(
        x=labels,
        y=values,
        marker=dict(
            color=colors,
            line=dict(color=borders, width=1.5),
            opacity=0.85,
        ),
        text=[f"{v:+.2f}%" for v in values],
        textposition="outside",
        textfont=dict(size=13, color=COLORS["text"]),
        hovertemplate="<b>%{x}</b><br>Change: %{y:+.2f}%<extra></extra>",
    ))

    fig.update_layout(
        **PLOTLY_LAYOUT,
        title=dict(
            text=f"🚀 AI STOCKS — DAILY MOVERS  <span style='font-size:12px;color:{COLORS['text_dim']}'>{datetime.now().strftime('%b %d, %Y')}</span>",
            font=dict(size=16, color=COLORS["text"]),
            x=0.5,
        ),
        xaxis=dict(
            showgrid=False,
            tickfont=dict(size=10),
            color=COLORS["text_dim"],
        ),
        yaxis=dict(
            gridcolor=COLORS["border"],
            ticksuffix="%",
            zeroline=True,
            zerolinecolor=COLORS["border"],
            zerolinewidth=1,
            color=COLORS["text_dim"],
        ),
        showlegend=False,
        height=420,
        bargap=0.35,
    )

    # Annotation: climbers vs fallers labels
    fig.add_annotation(x=1, y=1.08, xref="paper", yref="paper",
                       text="▲ CLIMBERS", font=dict(color=COLORS["green"], size=11),
                       showarrow=False)
    fig.add_annotation(x=0.75, y=1.08, xref="paper", yref="paper",
                       text="▼ FALLERS", font=dict(color=COLORS["red"], size=11),
                       showarrow=False)

    return _fig_to_b64(fig)


def make_monthly_movers_chart(monthly: dict) -> str:
    """
    Side-by-side grouped bars: 30-day % change for top 3 climbers and top 3 fallers.
    Includes a secondary annotation showing price change in $.
    """
    climbers = monthly["climbers"]
    fallers  = monthly["fallers"]
    all_stocks = climbers + fallers

    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=("🏆 30-Day Climbers", "📉 30-Day Fallers"),
        horizontal_spacing=0.12,
    )

    # Climbers
    fig.add_trace(go.Bar(
        x=[s["ticker"] for s in climbers],
        y=[s["monthly_pct"] for s in climbers],
        name="Climbers",
        marker=dict(
            color=[COLORS["green"], COLORS["accent2"], COLORS["gold"]],
            line=dict(color=COLORS["green"], width=1),
            opacity=0.9,
        ),
        text=[f"+{s['monthly_pct']:.1f}%<br>(${s['monthly_abs']:+.2f})" for s in climbers],
        textposition="outside",
        textfont=dict(size=11),
        hovertemplate="<b>%{x}</b><br>30d: %{y:+.2f}%<extra></extra>",
    ), row=1, col=1)

    # Fallers
    fig.add_trace(go.Bar(
        x=[s["ticker"] for s in fallers],
        y=[s["monthly_pct"] for s in fallers],
        name="Fallers",
        marker=dict(
            color=[COLORS["red"], "#ff8866", "#ff66aa"],
            line=dict(color=COLORS["red"], width=1),
            opacity=0.9,
        ),
        text=[f"{s['monthly_pct']:.1f}%<br>(${s['monthly_abs']:+.2f})" for s in fallers],
        textposition="outside",
        textfont=dict(size=11),
        hovertemplate="<b>%{x}</b><br>30d: %{y:+.2f}%<extra></extra>",
    ), row=1, col=2)

    fig.update_layout(
        **PLOTLY_LAYOUT,
        title=dict(
            text="📊 AI STOCKS — 30-DAY PERFORMANCE",
            font=dict(size=16, color=COLORS["text"]),
            x=0.5,
        ),
        showlegend=False,
        height=450,
    )

    # Style both axes
    for axis in ["xaxis", "xaxis2"]:
        fig.update_layout(**{axis: dict(showgrid=False, color=COLORS["text_dim"])})
    for axis in ["yaxis", "yaxis2"]:
        fig.update_layout(**{axis: dict(
            gridcolor=COLORS["border"],
            ticksuffix="%",
            zeroline=True,
            zerolinecolor=COLORS["border"],
            color=COLORS["text_dim"],
        )})

    # Style subplot titles
    for annotation in fig.layout.annotations:
        annotation.font = dict(color=COLORS["text"], size=13)

    return _fig_to_b64(fig)


def make_sparkline_chart(monthly: dict) -> str:
    """
    30-day line sparklines for the top 6 movers (3 up + 3 down).
    Each stock gets its own mini chart in a 2x3 grid.
    """
    all_stocks = monthly["climbers"] + monthly["fallers"]
    fig = make_subplots(
        rows=2, cols=3,
        subplot_titles=[f"{s['ticker']} ({s['monthly_pct']:+.1f}%)" for s in all_stocks],
        vertical_spacing=0.18,
        horizontal_spacing=0.08,
    )

    for idx, stock in enumerate(all_stocks):
        row = idx // 3 + 1
        col = idx % 3 + 1
        history = stock.get("history", [])
        is_climber = idx < 3
        line_color = COLORS["green"] if is_climber else COLORS["red"]
        fill_color = COLORS["green_dim"] if is_climber else COLORS["red_dim"]

        if history:
            x_vals = list(range(len(history)))
            fig.add_trace(go.Scatter(
                x=x_vals,
                y=history,
                mode="lines",
                line=dict(color=line_color, width=2),
                fill="tozeroy",
                fillcolor=fill_color,
                hovertemplate=f"<b>{stock['ticker']}</b><br>Day %{{x}}: $%{{y:.2f}}<extra></extra>",
                showlegend=False,
            ), row=row, col=col)

    fig.update_layout(
        **PLOTLY_LAYOUT,
        title=dict(
            text="📈 30-DAY PRICE TRENDS — TOP MOVERS",
            font=dict(size=16, color=COLORS["text"]),
            x=0.5,
        ),
        height=500,
    )

    for i in range(1, 7):
        suffix = "" if i == 1 else str(i)
        fig.update_layout(**{
            f"xaxis{suffix}": dict(showgrid=False, showticklabels=False, color=COLORS["text_dim"]),
            f"yaxis{suffix}": dict(gridcolor=COLORS["border"], tickprefix="$", tickfont=dict(size=9), color=COLORS["text_dim"]),
        })

    for ann in fig.layout.annotations:
        ann.font = dict(color=COLORS["text_dim"], size=11)

    return _fig_to_b64(fig)


def _fig_to_b64(fig) -> str:
    """Convert a Plotly figure to a base64 PNG string."""
    img_bytes = fig.to_image(format="png", width=900, height=fig.layout.height or 450, scale=1.5)
    return base64.b64encode(img_bytes).decode("utf-8")


def fig_to_pil(fig):
    """Convert Plotly figure to PIL Image for Gradio display."""
    from PIL import Image
    img_bytes = fig.to_image(format="png", width=900, scale=1.5)
    return Image.open(io.BytesIO(img_bytes))


def get_all_charts_as_pil(daily_movers: dict, monthly_movers: dict):
    """
    Returns three PIL images:
      1. Daily movers bar
      2. Monthly movers bar
      3. 30-day sparklines
    """
    import io
    from PIL import Image

    def b64_to_pil(b64_str: str):
        img_data = base64.b64decode(b64_str)
        return Image.open(io.BytesIO(img_data))

    daily_b64   = make_daily_movers_chart(daily_movers)
    monthly_b64 = make_monthly_movers_chart(monthly_movers)
    spark_b64   = make_sparkline_chart(monthly_movers)

    return (
        b64_to_pil(daily_b64),
        b64_to_pil(monthly_b64),
        b64_to_pil(spark_b64),
    )

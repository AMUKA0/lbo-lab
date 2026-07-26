"""Shared design system for the LBO Lab app.

One place for the palette, typography, CSS, and the Plotly template so the
landing page and the simulator read as a single product. Import and call
`use_theme()` at the top of every page.
"""

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

# ------------------------------------------------------------------ palette
INK_BG = "#0d1210"          # page ground
RAISE_BG = "#141b17"        # cards / panels
RAISE_EDGE = "#243029"      # hairline borders
TEXT = "#e9eae3"
TEXT_SOFT = "#a9b3aa"
TEXT_FAINT = "#6f7a71"
PINE = "#46b581"            # primary accent
PINE_DEEP = "#1f7a51"
BRASS = "#cf9c4c"           # secondary accent — figures, eyebrows
RUST = "#c0653c"            # downside / negative
GRID = "#232d26"

COLORWAY = [PINE, BRASS, "#5e9bb5", RUST, "#8f7fc0", "#b5ac5e"]

_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,500;8..60,600&family=IBM+Plex+Mono:wght@400;500&display=swap');

:root {{
  --ink: {INK_BG};
  --raise: {RAISE_BG};
  --edge: {RAISE_EDGE};
  --text: {TEXT};
  --soft: {TEXT_SOFT};
  --faint: {TEXT_FAINT};
  --pine: {PINE};
  --brass: {BRASS};
  --rust: {RUST};
  --serif: 'Source Serif 4', Georgia, serif;
  --mono: 'IBM Plex Mono', Consolas, monospace;
}}

/* ---- strip Streamlit chrome (but never the sidebar toggle) ---- */
#MainMenu, footer, [data-testid="stDecoration"], [data-testid="stMainMenu"] {{ display: none; }}
[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ padding-top: 2.2rem; max-width: 1200px; }}

/* the reopen-sidebar chevron must always be visible and obviously clickable */
[data-testid="stSidebarCollapsedControl"], [data-testid="stExpandSidebarButton"] {{
  display: flex !important; visibility: visible !important;
  background: {RAISE_BG}; border: 1px solid {PINE};
  border-radius: 8px; z-index: 1000;
}}
[data-testid="stSidebarCollapsedControl"] svg, [data-testid="stSidebarCollapsedControl"] button,
[data-testid="stExpandSidebarButton"] svg {{
  color: {PINE} !important; fill: {PINE} !important;
}}

/* ---- tabs (Streamlit renders these as div[role="tab"]) ---- */
[role="tablist"] {{ gap: 0.4rem; border-bottom: 1px solid var(--edge); }}
[role="tab"] {{
  font-family: var(--mono) !important; font-size: 0.74rem !important;
  letter-spacing: 0.12em; text-transform: uppercase;
  color: var(--faint) !important; background: transparent;
  padding: 0.6rem 1.05rem !important; transition: color 0.15s ease;
}}
html body [data-testid="stTab"] p, html body [role="tab"] p {{
  font-family: var(--mono) !important; font-size: 0.74rem !important;
  letter-spacing: 0.12em !important; text-transform: uppercase !important;
  color: inherit !important; margin: 0 !important;
}}
[role="tab"]:hover {{ color: var(--soft) !important; }}
[role="tab"][aria-selected="true"] {{ color: var(--pine) !important; }}
[role="tab"][aria-selected="true"] p {{ color: var(--pine) !important; font-weight: 600; }}
[data-baseweb="tab-highlight"] {{ background-color: var(--pine) !important; }}
[data-baseweb="tab-border"] {{ background-color: var(--edge) !important; }}

/* ---- typography ---- */
h1, h2, h3 {{ font-family: var(--serif) !important; letter-spacing: -0.01em; }}
h1 {{ font-weight: 600 !important; }}
[data-testid="stMetricValue"] {{ font-family: var(--serif); }}

/* ---- eyebrow section labels ---- */
.eyebrow {{
  font-family: var(--mono); font-size: 0.72rem; letter-spacing: 0.16em;
  text-transform: uppercase; color: var(--brass); margin: 0 0 0.35rem 0;
  display: flex; align-items: center; gap: 0.7rem;
}}
.eyebrow::after {{ content: ""; flex: 1; height: 1px; background: var(--edge); }}
.section-title {{
  font-family: var(--serif); font-size: 1.45rem; font-weight: 600;
  color: var(--text); margin: 0 0 1.0rem 0;
}}

/* ---- hero (landing) ---- */
.hero {{ padding: 3.2rem 0 2.2rem 0; }}
.hero-kicker {{
  font-family: var(--mono); font-size: 0.78rem; letter-spacing: 0.22em;
  text-transform: uppercase; color: var(--brass);
  animation: fadeUp 0.5s ease both;
}}
.hero-title {{
  font-family: var(--serif); font-size: clamp(2.4rem, 5vw, 3.6rem);
  font-weight: 600; line-height: 1.06; color: var(--text);
  margin: 0.8rem 0 1.1rem 0; max-width: 21ch; text-wrap: balance;
  animation: fadeUp 0.5s 0.08s ease both;
}}
.hero-title em {{ font-style: normal; color: var(--pine); }}
.hero-sub {{
  font-size: 1.12rem; color: var(--soft); max-width: 58ch; line-height: 1.65;
  animation: fadeUp 0.5s 0.16s ease both;
}}
.hero-cta-row {{ animation: fadeUp 0.5s 0.24s ease both; }}

/* ---- stat strip (landing) ---- */
.stat-strip {{
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 1px;
  background: var(--edge); border: 1px solid var(--edge); border-radius: 10px;
  overflow: hidden; margin: 2.2rem 0;
  animation: fadeUp 0.5s 0.32s ease both;
}}
.stat-cell {{ background: var(--raise); padding: 1.1rem 1.3rem; }}
.stat-cell .v {{
  font-family: var(--serif); font-size: 1.7rem; font-weight: 600; color: var(--pine);
  font-variant-numeric: tabular-nums;
}}
.stat-cell .k {{
  font-family: var(--mono); font-size: 0.68rem; letter-spacing: 0.12em;
  text-transform: uppercase; color: var(--faint); margin-top: 0.2rem;
}}

/* ---- feature cards ---- */
.feature-card {{
  background: var(--raise); border: 1px solid var(--edge); border-radius: 10px;
  padding: 1.35rem 1.45rem; height: 100%;
  transition: transform 0.18s ease, border-color 0.18s ease;
}}
.feature-card:hover {{ transform: translateY(-3px); border-color: var(--pine); }}
.feature-card .fc-no {{
  font-family: var(--mono); font-size: 0.72rem; color: var(--brass);
  letter-spacing: 0.1em; margin-bottom: 0.55rem;
}}
.feature-card h4 {{
  font-family: var(--serif); font-size: 1.08rem; font-weight: 600;
  color: var(--text); margin: 0 0 0.45rem 0;
}}
.feature-card p {{ font-size: 0.9rem; color: var(--soft); line-height: 1.55; margin: 0; }}

/* ---- metric tiles (simulator) ---- */
.tile-row {{
  display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 1px;
  background: var(--edge); border: 1px solid var(--edge); border-radius: 10px;
  overflow: hidden; margin: 0.4rem 0 1.4rem 0;
}}
.tile {{ background: var(--raise); padding: 1.0rem 1.2rem; }}
.tile .t-label {{
  font-family: var(--mono); font-size: 0.66rem; letter-spacing: 0.13em;
  text-transform: uppercase; color: var(--faint);
}}
.tile .t-value {{
  font-family: var(--serif); font-size: 1.85rem; font-weight: 600;
  color: var(--text); margin-top: 0.25rem; font-variant-numeric: tabular-nums;
  transition: color 0.3s ease;
}}
.tile .t-value.accent {{ color: var(--pine); }}
.tile .t-sub {{ font-family: var(--mono); font-size: 0.72rem; color: var(--faint); margin-top: 0.15rem; }}

/* ---- flag banners ---- */
.flag {{
  border-left: 3px solid var(--brass);
  background: color-mix(in srgb, var(--brass) 9%, transparent);
  border-radius: 0 8px 8px 0; padding: 0.75rem 1.0rem; margin: 0.45rem 0;
  font-size: 0.88rem; color: var(--soft); line-height: 1.5;
}}
.flag.info {{ border-left-color: var(--pine); background: color-mix(in srgb, var(--pine) 8%, transparent); }}
.flag .flag-src {{
  display: block; font-family: var(--mono); font-size: 0.7rem;
  color: var(--faint); margin-top: 0.25rem;
}}

/* ---- sidebar ---- */
[data-testid="stSidebar"] {{
  background: {RAISE_BG}; border-right: 1px solid var(--edge);
}}
[data-testid="stSidebar"] h1 {{ font-size: 1.25rem !important; }}
[data-testid="stSidebar"] h3 {{
  font-family: var(--mono) !important; font-size: 0.7rem !important;
  letter-spacing: 0.14em; text-transform: uppercase; color: var(--brass) !important;
  margin-top: 1.1rem;
}}

/* ---- tables ---- */
[data-testid="stTable"] table {{ font-size: 0.86rem; }}
[data-testid="stTable"] thead th {{
  font-family: var(--mono); font-size: 0.68rem; letter-spacing: 0.1em;
  text-transform: uppercase; color: var(--faint) !important;
}}

/* ---- page links styled as buttons ---- */
[data-testid="stPageLink"] a {{
  border: 1px solid var(--pine); border-radius: 8px;
  padding: 0.55rem 1.1rem; transition: background 0.15s ease;
}}
[data-testid="stPageLink"] a:hover {{ background: color-mix(in srgb, var(--pine) 14%, transparent); }}
[data-testid="stPageLink"] a p {{ color: var(--pine) !important; font-weight: 600; }}

/* ---- footer ---- */
.site-footer {{
  border-top: 1px solid var(--edge); margin-top: 3rem; padding-top: 1.2rem;
  display: flex; justify-content: space-between; flex-wrap: wrap; gap: 0.5rem;
  font-family: var(--mono); font-size: 0.72rem; color: var(--faint);
}}

@keyframes fadeUp {{
  from {{ opacity: 0; transform: translateY(14px); }}
  to {{ opacity: 1; transform: translateY(0); }}
}}
@media (prefers-reduced-motion: reduce) {{
  * {{ animation: none !important; transition: none !important; }}
}}
</style>
"""


def use_theme() -> None:
    """Inject the design system and register the Plotly template. Call once
    per page, immediately after st.set_page_config."""
    st.markdown(_CSS, unsafe_allow_html=True)
    if "lbo" not in pio.templates:
        pio.templates["lbo"] = go.layout.Template(
            layout=go.Layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(family="'Segoe UI', system-ui, sans-serif", color=TEXT_SOFT, size=12),
                colorway=COLORWAY,
                xaxis=dict(gridcolor=GRID, zerolinecolor=GRID, linecolor=RAISE_EDGE),
                yaxis=dict(gridcolor=GRID, zerolinecolor=GRID, linecolor=RAISE_EDGE),
                legend=dict(bgcolor="rgba(0,0,0,0)"),
                margin=dict(l=10, r=10, t=24, b=10),
                hoverlabel=dict(bgcolor=RAISE_BG, bordercolor=RAISE_EDGE, font=dict(color=TEXT)),
            )
        )
    pio.templates.default = "lbo"


def section(eyebrow: str, title: str) -> None:
    st.markdown(
        f'<p class="eyebrow">{eyebrow}</p><p class="section-title">{title}</p>',
        unsafe_allow_html=True,
    )


def metric_tiles(items: list[tuple[str, str, str, bool]]) -> None:
    """Row of styled tiles: (label, value, sub, accent)."""
    cells = "".join(
        f'<div class="tile"><div class="t-label">{label}</div>'
        f'<div class="t-value{" accent" if accent else ""}">{value}</div>'
        f'<div class="t-sub">{sub}</div></div>'
        for label, value, sub, accent in items
    )
    st.markdown(f'<div class="tile-row">{cells}</div>', unsafe_allow_html=True)


def flag_banner(message: str, source: str, level: str) -> None:
    css = "flag info" if level == "info" else "flag"
    st.markdown(
        f'<div class="{css}">{message}<span class="flag-src">Source: {source}</span></div>',
        unsafe_allow_html=True,
    )


def footer() -> None:
    st.markdown(
        '<div class="site-footer"><span>LBO Lab — a deal-level leveraged buyout laboratory</span>'
        "<span>engine validated against a hand-derived golden model · all figures illustrative</span></div>",
        unsafe_allow_html=True,
    )

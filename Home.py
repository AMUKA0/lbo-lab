"""LBO Lab — landing page."""

import streamlit as st

from ui import footer, section, use_theme

st.set_page_config(
    page_title="LBO Lab — leveraged buyout laboratory",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)
use_theme()

# ------------------------------------------------------------------- hero
st.markdown(
    """
    <div class="hero">
      <div class="hero-kicker">LBO Lab · Deal-level buyout modelling</div>
      <h1 class="hero-title">Interrogate a leveraged buyout <em>in real time.</em></h1>
      <p class="hero-sub">
        A working laboratory for private-equity deal mechanics: a fully engineered
        LBO model — multi-tranche debt, cash sweep, the interest circularity solved
        properly — with the judgement layer most models skip: market-range guardrails
        on every assumption, driver attribution, stress tests, and the model run in reverse.
      </p>
    </div>
    """,
    unsafe_allow_html=True,
)

cta1, cta2, _sp = st.columns([1.2, 1.4, 3])
with cta1:
    st.markdown('<div class="hero-cta-row">', unsafe_allow_html=True)
    st.page_link("pages/1_Simulator.py", label="Open the simulator →")
    st.markdown("</div>", unsafe_allow_html=True)
with cta2:
    st.markdown('<div class="hero-cta-row">', unsafe_allow_html=True)
    st.page_link("Home.py", label="Methodology below ↓")
    st.markdown("</div>", unsafe_allow_html=True)

# ------------------------------------------------------------------- stats
st.markdown(
    """
    <div class="stat-strip">
      <div class="stat-cell"><div class="v">58</div><div class="k">tests · golden model to 1e-6</div></div>
      <div class="stat-cell"><div class="v">7</div><div class="k">drivers in the tornado</div></div>
      <div class="stat-cell"><div class="v">4</div><div class="k">scenarios incl. recession stress</div></div>
      <div class="stat-cell"><div class="v">±2×</div><div class="k">entry / exit sensitivity grid</div></div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ------------------------------------------------------------------- features
section("What the lab does", "Built like the models funds actually run")

FEATURES = [
    ("01", "The engine, done properly",
     "Sources & uses with equity as the plug, a multi-tranche debt schedule with mandatory "
     "amortisation and a senior-first cash sweep, PIK accretion, NOL carryforwards under the "
     "80% limitation, a revolver for shortfalls — and the interest ↔ balance circularity "
     "resolved by an iterative solve, the way Excel's iterative mode does it."),
    ("02", "Value-creation bridge",
     "Every outcome decomposed into the three drivers an investment committee actually argues "
     "about — EBITDA growth, multiple expansion, deleveraging — plus the fee drag. The bridge "
     "sums exactly to the equity gain; the test suite asserts the identity."),
    ("03", "Calibration guardrails",
     "Each assumption is checked against published market bands — Bain, PitchBook LCD, S&P — "
     "and flags when you drift outside them. You are allowed to model 2007; the lab just "
     "tells you that you are."),
    ("04", "Tornado & scenarios",
     "One-at-a-time driver swings ranked by IRR impact, and a base / upside / downside / "
     "recession set run side-by-side — including the honest finding that a V-shaped shock "
     "can beat a permanent downgrade."),
    ("05", "The model in reverse",
     "A breakeven solver: name a target IRR and the lab bisects for the exit multiple that "
     "clears it. The distance between that and your entry multiple is how much of your "
     "return you are asking the market to hand you."),
    ("06", "The lender's view",
     "Net leverage, interest coverage, (EBITDA − capex) coverage and FCF conversion by year, "
     "against the covenant conventions credit committees actually use. A structure that "
     "breaches them on paper doesn't get financed on those terms."),
]

for row_start in (0, 3):
    cols = st.columns(3)
    for col, (no, title, body) in zip(cols, FEATURES[row_start:row_start + 3]):
        with col:
            st.markdown(
                f'<div class="feature-card"><div class="fc-no">{no}</div>'
                f"<h4>{title}</h4><p>{body}</p></div>",
                unsafe_allow_html=True,
            )
    st.markdown('<div style="height:14px"></div>', unsafe_allow_html=True)

# ------------------------------------------------------------------- methodology
st.markdown('<div style="height:26px"></div>', unsafe_allow_html=True)
section("Methodology", "Conventions, stated plainly")

m1, m2 = st.columns(2)
with m1:
    st.markdown(
        """
- **Entry** — cash-free / debt-free; EV = EBITDA × entry multiple; sponsor equity is the plug.
- **Interest** — on the average of opening and closing balances, the advanced-model convention; the circularity is resolved iteratively each year to a 1e-10 tolerance, with the pass count shown in the UI. A circularity-breaker toggle switches to opening-balance-only, the escape hatch bank models ship.
- **Waterfall** — mandatory amortisation (% of *original* principal, term-loan convention) → revolver repayment → cash sweep, senior-first, sweepable tranches only.
- **Taxes** — on EBT after all deductible interest and fee amortisation; losses carry forward as NOLs sheltering up to 80% of later income (post-TCJA §172(a)).
        """
    )
with m2:
    st.markdown(
        """
- **Fees** — financing fees amortise over the *facility tenor* per ASC 835-30, not the hold; sale-process costs come out of exit proceeds.
- **Exit** — exit multiple × terminal EBITDA, less net debt and exit fees; sponsor equity floored at zero (limited liability).
- **Returns** — MOIC and bisection IRR on the sponsor's flows; the value bridge reconciles exactly, and credit stats cover the lender's view.
- **Simplifications, documented** — annual periodicity, fixed rates, no dividend recaps or management rollover. Listed with their consequences in the README, because pretending they don't exist is how models lie.
        """
    )

footer()

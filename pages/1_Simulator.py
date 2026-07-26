"""LBO Lab — the simulator. All financial logic lives in lbo_engine;
this page is a styled view over one Assumptions object and one LBOResult."""

import math

import plotly.graph_objects as go
import streamlit as st

from lbo_engine import Assumptions, DebtTranche, OperatingAssumptions, RevolverAssumptions, run_lbo
from lbo_engine.analysis import (
    breakeven_exit_multiple,
    debt_paydown_table,
    entry_exit_sensitivity,
    scenario_set,
    tornado,
)
from lbo_engine.calibration import check_assumptions
from lbo_engine.returns import returns_bridge, sponsor_irr
from ui import BRASS, PINE, PINE_DEEP, RUST, TEXT_FAINT, flag_banner, footer, metric_tiles, section, use_theme

st.set_page_config(page_title="Simulator — LBO Lab", page_icon="📈", layout="wide")
use_theme()

# ---------------------------------------------------------------- assumptions
st.sidebar.title("Assumptions")

st.sidebar.subheader("Entry")
entry_ebitda = st.sidebar.number_input("Entry EBITDA", 10.0, 10_000.0, 100.0, step=10.0)
entry_multiple = st.sidebar.slider("Entry EV / EBITDA", 4.0, 20.0, 10.0, 0.25)

st.sidebar.subheader("Operations")
entry_revenue = st.sidebar.number_input("Entry revenue", 10.0, 100_000.0, 500.0, step=10.0)
revenue_growth = st.sidebar.slider("Revenue growth % p.a.", -10.0, 25.0, 5.0, 0.5) / 100
ebitda_margin = st.sidebar.slider("EBITDA margin %", 5.0, 60.0, 21.0, 0.5) / 100
da_pct = st.sidebar.slider("D&A % of revenue", 0.0, 15.0, 3.5, 0.5) / 100
capex_pct = st.sidebar.slider("Capex % of revenue", 0.0, 15.0, 4.0, 0.5) / 100
nwc_pct = st.sidebar.slider("NWC % of revenue", 0.0, 30.0, 10.0, 1.0) / 100
tax_rate = st.sidebar.slider("Tax rate %", 0.0, 45.0, 25.0, 1.0) / 100

st.sidebar.subheader("Senior term loan")
senior_turns = st.sidebar.slider("Senior leverage (× EBITDA)", 0.5, 7.0, 4.0, 0.25)
senior_rate = st.sidebar.slider("Senior cash rate %", 2.0, 12.0, 5.5, 0.25) / 100
senior_amort = st.sidebar.slider("Mandatory amort % of original p.a.", 0.0, 20.0, 5.0, 1.0) / 100

st.sidebar.subheader("Mezzanine")
mezz_turns = st.sidebar.slider("Mezz leverage (× EBITDA)", 0.0, 4.0, 1.0, 0.25)
mezz_rate = st.sidebar.slider("Mezz cash rate %", 4.0, 16.0, 8.0, 0.25) / 100
mezz_pik = st.sidebar.slider("Mezz PIK rate %", 0.0, 8.0, 3.0, 0.25) / 100

st.sidebar.subheader("Cash policy & revolver")
sweep_pct = st.sidebar.slider("Cash sweep %", 0, 100, 100, 5) / 100
minimum_cash = st.sidebar.number_input("Minimum cash", 0.0, 1_000.0, 10.0, step=5.0)
revolver_commitment = st.sidebar.number_input("Revolver commitment", 0.0, 5_000.0, 50.0, step=10.0)
revolver_rate = st.sidebar.slider("Revolver rate %", 2.0, 12.0, 6.0, 0.25) / 100

st.sidebar.subheader("Fees")
txn_fee = st.sidebar.slider("Transaction fees % of EV", 0.0, 5.0, 1.5, 0.25) / 100
fin_fee = st.sidebar.slider("Financing fees % of debt", 0.0, 5.0, 2.5, 0.25) / 100

st.sidebar.subheader("Exit")
hold_years = st.sidebar.slider("Hold period (years)", 3, 10, 5)
exit_multiple = st.sidebar.slider("Exit EV / EBITDA", 4.0, 20.0, 10.5, 0.25)

tranches = [
    DebtTranche(
        name="senior", leverage_turns=senior_turns, cash_rate=senior_rate,
        mandatory_amort_pct=senior_amort, sweepable=True,
    )
]
if mezz_turns > 0:
    tranches.append(
        DebtTranche(
            name="mezz", leverage_turns=mezz_turns, cash_rate=mezz_rate,
            pik_rate=mezz_pik, sweepable=False,
        )
    )

assumptions = Assumptions(
    entry_ebitda=entry_ebitda,
    entry_multiple=entry_multiple,
    operating=OperatingAssumptions(
        entry_revenue=entry_revenue, revenue_growth=revenue_growth,
        ebitda_margin=ebitda_margin, da_pct_revenue=da_pct,
        capex_pct_revenue=capex_pct, nwc_pct_revenue=nwc_pct, tax_rate=tax_rate,
    ),
    tranches=tranches,
    revolver=RevolverAssumptions(commitment=revolver_commitment, cash_rate=revolver_rate),
    transaction_fee_pct_ev=txn_fee,
    financing_fee_pct_debt=fin_fee,
    minimum_cash=minimum_cash,
    cash_sweep_pct=sweep_pct,
    hold_years=hold_years,
    exit_multiple=exit_multiple,
)

# ---------------------------------------------------------------- run
st.title("Simulator")

implied = entry_revenue * ebitda_margin
if abs(implied - entry_ebitda) / entry_ebitda > 0.15:
    flag_banner(
        f"Entry EBITDA ({entry_ebitda:,.0f}) and revenue × margin ({implied:,.0f}) disagree by "
        "more than 15% — the projection is driven by revenue × margin, so entry EBITDA only "
        "sizes the cheque and the debt.",
        "Internal consistency check", "amber",
    )

for flag in check_assumptions(assumptions):
    flag_banner(flag.message, flag.source, flag.level)

try:
    result = run_lbo(assumptions)
except ValueError as exc:
    st.error(f"**Structure fails:** {exc}")
    st.stop()

irr_value = sponsor_irr(result)
bridge = returns_bridge(result)
su = result.sources_uses

metric_tiles([
    ("Sponsor IRR", f"{irr_value:.1%}", f"{assumptions.hold_years}-year hold", True),
    ("MOIC", f"{result.moic:.2f}×", "multiple of invested capital", True),
    ("Equity cheque", f"{result.entry_equity:,.0f}", "at close", False),
    ("Exit equity", f"{result.exit_equity:,.0f}", f"at {assumptions.exit_multiple:.2f}× exit", False),
    ("Entry leverage", f"{assumptions.total_leverage_turns:.2f}×", "debt / EBITDA", False),
])

# ---------------------------------------------------------------- S&U
with st.expander("Sources & Uses at close"):
    left, right = st.columns(2)
    with left:
        st.markdown("**Sources**")
        for name, amt in su.tranche_amounts.items():
            st.text(f"{name:<22}{amt:>12,.1f}")
        st.text(f"{'sponsor equity':<22}{su.sponsor_equity:>12,.1f}")
        st.text(f"{'total':<22}{su.total_sources:>12,.1f}")
    with right:
        st.markdown("**Uses**")
        st.text(f"{'enterprise value':<22}{su.entry_ev:>12,.1f}")
        st.text(f"{'transaction fees':<22}{su.transaction_fees:>12,.1f}")
        st.text(f"{'financing fees':<22}{su.financing_fees:>12,.1f}")
        st.text(f"{'cash to balance sheet':<22}{su.cash_to_balance_sheet:>12,.1f}")
        st.text(f"{'total':<22}{su.total_uses:>12,.1f}")

# ---------------------------------------------------------------- bridge + paydown
left, right = st.columns(2)

with left:
    section("Attribution", "Value-creation bridge")
    labels = ["Entry equity", "EBITDA growth", "Multiple", "Deleveraging", "Fees", "Exit equity"]
    fig = go.Figure(
        go.Waterfall(
            orientation="v",
            measure=["absolute", "relative", "relative", "relative", "relative", "total"],
            x=labels,
            y=[
                bridge.entry_equity, bridge.ebitda_growth, bridge.multiple_expansion,
                bridge.deleveraging, bridge.fee_drag, 0,
            ],
            increasing={"marker": {"color": PINE_DEEP}},
            decreasing={"marker": {"color": RUST}},
            totals={"marker": {"color": BRASS}},
            connector={"line": {"width": 1, "color": TEXT_FAINT}},
        )
    )
    fig.update_layout(height=380, showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

with right:
    section("Deleveraging", "Debt paydown across the hold")
    paydown = debt_paydown_table(assumptions)
    fig2 = go.Figure()
    for col in [c for c in paydown.columns if c != "cash"]:
        fig2.add_trace(
            go.Scatter(x=paydown.index, y=paydown[col], name=col, stackgroup="debt", mode="lines")
        )
    fig2.add_trace(
        go.Scatter(x=paydown.index, y=paydown["cash"], name="cash",
                   mode="lines+markers", line=dict(dash="dot"))
    )
    fig2.update_layout(height=380, xaxis_title="Year", yaxis_title="Balance")
    st.plotly_chart(fig2, use_container_width=True)

# ---------------------------------------------------------------- tornado + scenarios
left, right = st.columns(2)

with left:
    section("Drivers", "What actually moves the IRR")
    torn = tornado(assumptions)
    base_irr_pct = torn["base_irr"].iloc[0] * 100
    fig3 = go.Figure()
    drivers = torn.index.tolist()[::-1]
    fig3.add_trace(go.Bar(
        y=drivers,
        x=[(torn.loc[d, "low_irr"] * 100) - base_irr_pct for d in drivers],
        base=base_irr_pct, orientation="h", name="Downside", marker_color=RUST,
    ))
    fig3.add_trace(go.Bar(
        y=drivers,
        x=[(torn.loc[d, "high_irr"] * 100) - base_irr_pct for d in drivers],
        base=base_irr_pct, orientation="h", name="Upside", marker_color=PINE,
    ))
    fig3.add_vline(x=base_irr_pct, line_width=1, line_dash="dash", line_color=TEXT_FAINT)
    fig3.update_layout(
        height=380, barmode="overlay", xaxis_title="Sponsor IRR %",
        legend=dict(orientation="h", y=-0.25),
    )
    st.plotly_chart(fig3, use_container_width=True)
    st.caption("One driver moved at a time, all else held. Ranked widest first.")

with right:
    section("Resilience", "Scenarios & stress")
    rows = []
    for name, variant in scenario_set(assumptions).items():
        try:
            res = run_lbo(variant)
            rows.append({
                "scenario": name,
                "IRR": f"{sponsor_irr(res):.1%}",
                "MOIC": f"{res.moic:.2f}×",
                "peak revolver": f"{max(r.revolver_closing for r in res.years):,.0f}",
                "exit net debt": f"{res.exit_net_debt:,.0f}",
            })
        except ValueError:
            rows.append({
                "scenario": name, "IRR": "fails", "MOIC": "—",
                "peak revolver": "exhausted", "exit net debt": "—",
            })
    st.table(rows)
    st.caption(
        "Upside/downside: ±200bps growth, ±100bps margin, ±0.5–1.0× exit. "
        "Recession: EBITDA −20% in years 1–2 with recovery, exit −1.5×."
    )

    target = st.select_slider(
        "Breakeven — target IRR", options=[0.15, 0.20, 0.25, 0.30], value=0.20,
        format_func=lambda v: f"{v:.0%}",
    )
    be = breakeven_exit_multiple(assumptions, target)
    if math.isnan(be):
        metric_tiles([("Breakeven exit multiple", "unreachable", f"for {target:.0%} IRR", False)] )
    else:
        metric_tiles([(
            "Breakeven exit multiple", f"{be:.2f}×",
            f"{be - entry_multiple:+.2f}× vs entry — expansion you must be handed", be <= entry_multiple,
        )])

# ---------------------------------------------------------------- sensitivity
section("Sensitivity", "IRR across entry × exit multiple")
entry_range = [round(entry_multiple + d, 2) for d in (-2.0, -1.0, 0.0, 1.0, 2.0)]
exit_range = [round(exit_multiple + d, 2) for d in (-2.0, -1.0, 0.0, 1.0, 2.0)]
grid = entry_exit_sensitivity(assumptions, entry_range, exit_range)

heat = go.Figure(
    go.Heatmap(
        z=grid.values * 100,
        x=[f"{x:.2f}×" for x in grid.columns],
        y=[f"{y:.2f}×" for y in grid.index],
        colorscale=[[0, "#141b17"], [1, PINE]],
        text=[[("–" if math.isnan(v) else f"{v:.1%}") for v in row] for row in grid.values],
        texttemplate="%{text}",
        colorbar={"title": "IRR %"},
    )
)
heat.update_layout(
    height=400, xaxis_title="Exit multiple", yaxis_title="Entry multiple",
    yaxis={"autorange": "reversed"},
)
st.plotly_chart(heat, use_container_width=True)
st.caption("Dashes mark structures that fail (revolver exhausted) or wipe the sponsor — shown honestly, not smoothed over.")

# ---------------------------------------------------------------- schedule
section("The numbers", "Annual schedule")
st.dataframe(result.to_dataframe().round(1), use_container_width=True)

iters = ", ".join(str(row.interest_iterations) for row in result.years)
st.caption(
    f"Interest circularity resolved iteratively each year (passes: {iters}); "
    "interest charged on average of opening and closing balances."
)

footer()

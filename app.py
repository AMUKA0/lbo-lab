"""LBO Lab — the local Streamlit workbench over lbo_engine.

Run with:  streamlit run app.py

Every widget feeds one Assumptions object; every chart is a view of one
LBOResult. The app contains no financial logic of its own.
"""

import math

import plotly.graph_objects as go
import streamlit as st

from lbo_engine import Assumptions, DebtTranche, OperatingAssumptions, RevolverAssumptions, run_lbo
from lbo_engine.analysis import debt_paydown_table, entry_exit_sensitivity
from lbo_engine.returns import returns_bridge, sponsor_irr

st.set_page_config(page_title="LBO Lab", page_icon="📈", layout="wide")

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

st.sidebar.subheader("Debt — senior term loan")
senior_turns = st.sidebar.slider("Senior leverage (× EBITDA)", 0.5, 7.0, 4.0, 0.25)
senior_rate = st.sidebar.slider("Senior cash rate %", 2.0, 12.0, 5.5, 0.25) / 100
senior_amort = st.sidebar.slider("Mandatory amort % of original p.a.", 0.0, 20.0, 5.0, 1.0) / 100

st.sidebar.subheader("Debt — mezzanine")
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
st.title("LBO Lab")

# Implied EBITDA consistency check: EBITDA input vs revenue × margin at entry.
implied = entry_revenue * ebitda_margin
if abs(implied - entry_ebitda) / entry_ebitda > 0.15:
    st.warning(
        f"Entry EBITDA ({entry_ebitda:,.0f}) and revenue × margin "
        f"({implied:,.0f}) disagree by more than 15% — the projection is "
        "driven by revenue × margin, so entry EBITDA only sizes the cheque and the debt."
    )

try:
    result = run_lbo(assumptions)
except ValueError as exc:
    st.error(f"**Structure fails:** {exc}")
    st.stop()

irr_value = sponsor_irr(result)
bridge = returns_bridge(result)
su = result.sources_uses

# ---------------------------------------------------------------- tiles
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Sponsor IRR", f"{irr_value:.1%}")
c2.metric("MOIC", f"{result.moic:.2f}×")
c3.metric("Equity cheque", f"{result.entry_equity:,.0f}")
c4.metric("Exit equity", f"{result.exit_equity:,.0f}")
c5.metric("Entry leverage", f"{assumptions.total_leverage_turns:.2f}×")

# ---------------------------------------------------------------- S&U
with st.expander("Sources & Uses at close", expanded=False):
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
    st.subheader("Value-creation bridge")
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
            connector={"line": {"width": 1}},
        )
    )
    fig.update_layout(height=380, margin=dict(l=10, r=10, t=10, b=10), showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

with right:
    st.subheader("Debt paydown")
    paydown = debt_paydown_table(assumptions)
    fig2 = go.Figure()
    for col in [c for c in paydown.columns if c != "cash"]:
        fig2.add_trace(
            go.Scatter(
                x=paydown.index, y=paydown[col], name=col,
                stackgroup="debt", mode="lines",
            )
        )
    fig2.add_trace(
        go.Scatter(x=paydown.index, y=paydown["cash"], name="cash", mode="lines+markers")
    )
    fig2.update_layout(
        height=380, margin=dict(l=10, r=10, t=10, b=10),
        xaxis_title="Year", yaxis_title="Balance",
    )
    st.plotly_chart(fig2, use_container_width=True)

# ---------------------------------------------------------------- sensitivity
st.subheader("Sensitivity: IRR across entry × exit multiple")
entry_range = [round(entry_multiple + d, 2) for d in (-2.0, -1.0, 0.0, 1.0, 2.0)]
exit_range = [round(exit_multiple + d, 2) for d in (-2.0, -1.0, 0.0, 1.0, 2.0)]
grid = entry_exit_sensitivity(assumptions, entry_range, exit_range)

heat = go.Figure(
    go.Heatmap(
        z=grid.values * 100,
        x=[f"{x:.2f}×" for x in grid.columns],
        y=[f"{y:.2f}×" for y in grid.index],
        colorscale="Greens",
        text=[[("–" if math.isnan(v) else f"{v:.1%}") for v in row] for row in grid.values],
        texttemplate="%{text}",
        colorbar={"title": "IRR %"},
    )
)
heat.update_layout(
    height=380, margin=dict(l=10, r=10, t=10, b=10),
    xaxis_title="Exit multiple", yaxis_title="Entry multiple",
    yaxis={"autorange": "reversed"},
)
st.plotly_chart(heat, use_container_width=True)
st.caption("Dashes mark structures that fail (revolver exhausted) or wipe the sponsor — shown honestly, not smoothed over.")

# ---------------------------------------------------------------- schedule
st.subheader("Annual schedule")
st.dataframe(result.to_dataframe().round(1), use_container_width=True)

iters = ", ".join(str(row.interest_iterations) for row in result.years)
st.caption(
    f"Interest circularity resolved iteratively each year (passes: {iters}); "
    "interest charged on average of opening and closing balances."
)

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

import db
from ui_helpers import (
    eur, pct, ROLE_ACTUAL, ROLE_COMMITTED, ROLE_REMAINING, ROLE_OVERRUN,
    COST_TYPE_COLORS, MUTED, GRIDLINE, STATUS_CRITICAL, STATUS_GOOD,
)

st.set_page_config(page_title="Construction Cost Tracker", page_icon="🏗️", layout="wide")
db.init_db()

st.title("🏗️ Construction Cost Tracker")
st.caption("Budget vs. actual vs. committed costs for your project — all data stored locally.")

primary_codes = db.df_primary_cost_codes()
cost_codes = db.df_cost_codes()
cost_types = db.df_cost_types()
tx = db.df_transactions()
bl = db.df_budget_lines()

if cost_codes.empty:
    st.warning("No cost codes found. Go to the **Cost Codes** page to add some.")
    st.stop()

# ---------------- Filters ----------------
primary_options = primary_codes["name"].tolist() + ["Unassigned"]
code_options = cost_codes["name"].tolist()
type_options = cost_types["name"].tolist() + ["Unassigned"]

f0, f1, f2 = st.columns(3)
with f0:
    selected_primary = st.multiselect("Primary (where: Building / Pools / Exterior)", primary_options, default=primary_options)
with f1:
    selected_codes = st.multiselect("Secondary cost code (what)", code_options, default=code_options)
with f2:
    selected_types = st.multiselect("Cost type (materials / labor / equipment / other)", type_options, default=type_options)

# ---------------- Prepare filtered data ----------------
if not bl.empty:
    bl = bl.copy()
    bl["cost_type_display"] = bl["cost_type"].fillna("Unassigned")
    bl["primary_display"] = bl["primary_cost_code"].fillna("Unassigned")
    bl_f = bl[
        bl["cost_code"].isin(selected_codes)
        & bl["cost_type_display"].isin(selected_types)
        & bl["primary_display"].isin(selected_primary)
    ]
else:
    bl_f = bl

if not tx.empty:
    tx = tx.copy()
    tx["cost_type_display"] = tx["cost_type"].fillna("Unassigned")
    tx["primary_display"] = tx["primary_cost_code"].fillna("Unassigned")
    tx_f = tx[
        tx["cost_code"].isin(selected_codes)
        & tx["cost_type_display"].isin(selected_types)
        & tx["primary_display"].isin(selected_primary)
    ]
else:
    tx_f = tx

# Budget per cost code
if not bl_f.empty:
    budget_by_code = bl_f.groupby("cost_code")["gross_amount"].sum().rename("budget")
else:
    budget_by_code = pd.Series(dtype=float, name="budget")

# Actual / committed per cost code
if not tx_f.empty:
    actual_by_code = tx_f[tx_f["status"] == "actual"].groupby("cost_code")["gross_amount"].sum().rename("actual")
    committed_by_code = tx_f[tx_f["status"] == "committed"].groupby("cost_code")["gross_amount"].sum().rename("committed")
else:
    actual_by_code = pd.Series(dtype=float, name="actual")
    committed_by_code = pd.Series(dtype=float, name="committed")

summary = pd.DataFrame({"cost_code": selected_codes}).set_index("cost_code")
summary = summary.join(budget_by_code).join(actual_by_code).join(committed_by_code).fillna(0)
summary["spent"] = summary["actual"] + summary["committed"]
summary["remaining"] = (summary["budget"] - summary["spent"]).clip(lower=0)
summary["overrun"] = (summary["spent"] - summary["budget"]).clip(lower=0)
summary["pct_spent"] = summary.apply(lambda r: (r["spent"] / r["budget"] * 100) if r["budget"] else 0, axis=1)
summary = summary.sort_values("budget", ascending=False)

# ---------------- KPI tiles ----------------
total_budget = summary["budget"].sum()
total_actual = summary["actual"].sum()
total_committed = summary["committed"].sum()
total_spent = summary["spent"].sum()
total_remaining = total_budget - total_spent

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Budget", eur(total_budget))
k2.metric("Actual (invoiced)", eur(total_actual))
k3.metric("Committed", eur(total_committed))
k4.metric("Total spent", eur(total_spent), pct(total_spent, total_budget))
k5.metric(
    "Cost to complete" if total_remaining >= 0 else "Over budget",
    eur(abs(total_remaining)),
    delta=None,
)

if total_remaining < 0:
    st.error(f"⚠️ Over budget by {eur(-total_remaining)} across the selected filters.")

# Outstanding payments
if not tx_f.empty:
    outstanding = tx_f[tx_f["status"] == "actual"]["balance_due"].clip(lower=0).sum()
    unpaid_count = (tx_f[(tx_f["status"] == "actual") & (tx_f["balance_due"] > 0.01)]).shape[0]
    if outstanding > 0:
        st.info(f"💳 Outstanding payments: **{eur(outstanding)}** across {unpaid_count} invoice(s) not fully paid.")

st.divider()

# ---------------- Chart 0: budget composition per primary cost code (where) ----------------
st.subheader("Budget vs. actual vs. committed, by primary cost code (where)")

if not primary_codes.empty:
    if not bl_f.empty:
        budget_by_primary = bl_f.groupby("primary_display")["gross_amount"].sum().rename("budget")
    else:
        budget_by_primary = pd.Series(dtype=float, name="budget")
    if not tx_f.empty:
        actual_by_primary = tx_f[tx_f["status"] == "actual"].groupby("primary_display")["gross_amount"].sum().rename("actual")
        committed_by_primary = tx_f[tx_f["status"] == "committed"].groupby("primary_display")["gross_amount"].sum().rename("committed")
    else:
        actual_by_primary = pd.Series(dtype=float, name="actual")
        committed_by_primary = pd.Series(dtype=float, name="committed")

    primary_summary = pd.DataFrame({"primary_cost_code": selected_primary}).set_index("primary_cost_code")
    primary_summary = primary_summary.join(budget_by_primary).join(actual_by_primary).join(committed_by_primary).fillna(0)
    primary_summary["spent"] = primary_summary["actual"] + primary_summary["committed"]
    primary_summary["remaining"] = (primary_summary["budget"] - primary_summary["spent"]).clip(lower=0)
    primary_summary["overrun"] = (primary_summary["spent"] - primary_summary["budget"]).clip(lower=0)
    primary_summary = primary_summary.sort_values("budget", ascending=False)

    if primary_summary["budget"].sum() == 0 and primary_summary["spent"].sum() == 0:
        st.caption("No budget lines or transactions yet for the selected filters.")
    else:
        pchart_df = primary_summary.reset_index()[::-1]

        pfig = go.Figure()
        pfig.add_bar(name="Actual (invoiced)", y=pchart_df["primary_cost_code"], x=pchart_df["actual"],
                     orientation="h", marker_color=ROLE_ACTUAL,
                     hovertemplate="Actual: %{x:,.2f} €<extra></extra>")
        pfig.add_bar(name="Committed", y=pchart_df["primary_cost_code"], x=pchart_df["committed"],
                     orientation="h", marker_color=ROLE_COMMITTED,
                     hovertemplate="Committed: %{x:,.2f} €<extra></extra>")
        pfig.add_bar(name="Remaining budget", y=pchart_df["primary_cost_code"], x=pchart_df["remaining"],
                     orientation="h", marker_color=ROLE_REMAINING,
                     hovertemplate="Remaining: %{x:,.2f} €<extra></extra>")
        pfig.add_bar(name="Over budget", y=pchart_df["primary_cost_code"], x=pchart_df["overrun"],
                     orientation="h", marker_color=ROLE_OVERRUN,
                     hovertemplate="Over budget: %{x:,.2f} €<extra></extra>")
        pfig.update_layout(
            barmode="stack",
            height=max(220, 50 * len(pchart_df) + 60),
            margin=dict(l=10, r=10, t=10, b=10),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(title="€", gridcolor=GRIDLINE, zeroline=False),
            yaxis=dict(title=""),
            font=dict(color=MUTED),
        )
        st.plotly_chart(pfig, use_container_width=True)
else:
    st.caption("No primary cost codes found. Go to the **Cost Codes** page to add Building/Pools/Exterior.")

st.divider()

# ---------------- Chart 1: budget composition per cost code ----------------
st.subheader("Budget vs. actual vs. committed, by secondary cost code (what)")

if summary["budget"].sum() == 0 and summary["spent"].sum() == 0:
    st.caption("No budget lines or transactions yet for the selected filters.")
else:
    chart_df = summary.reset_index()
    chart_df = chart_df[::-1]  # Plotly draws bottom-up; reverse so highest budget is on top

    fig = go.Figure()
    fig.add_bar(name="Actual (invoiced)", y=chart_df["cost_code"], x=chart_df["actual"],
                orientation="h", marker_color=ROLE_ACTUAL,
                hovertemplate="Actual: %{x:,.2f} €<extra></extra>")
    fig.add_bar(name="Committed", y=chart_df["cost_code"], x=chart_df["committed"],
                orientation="h", marker_color=ROLE_COMMITTED,
                hovertemplate="Committed: %{x:,.2f} €<extra></extra>")
    fig.add_bar(name="Remaining budget", y=chart_df["cost_code"], x=chart_df["remaining"],
                orientation="h", marker_color=ROLE_REMAINING,
                hovertemplate="Remaining: %{x:,.2f} €<extra></extra>")
    fig.add_bar(name="Over budget", y=chart_df["cost_code"], x=chart_df["overrun"],
                orientation="h", marker_color=ROLE_OVERRUN,
                hovertemplate="Over budget: %{x:,.2f} €<extra></extra>")

    fig.update_layout(
        barmode="stack",
        height=max(320, 40 * len(chart_df) + 80),
        margin=dict(l=10, r=10, t=10, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(title="€", gridcolor=GRIDLINE, zeroline=False),
        yaxis=dict(title=""),
        font=dict(color=MUTED),
    )
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ---------------- Chart 2: spend by cost type ----------------
st.subheader("Spend by cost type (materials / labor / equipment / other)")

if not tx_f.empty:
    type_df = (
        tx_f[tx_f["status"].isin(["actual", "committed"])]
        .groupby("cost_type_display")["gross_amount"].sum()
        .reset_index()
        .rename(columns={"cost_type_display": "cost_type", "gross_amount": "amount"})
        .sort_values("amount", ascending=True)
    )
    if type_df.empty or type_df["amount"].sum() == 0:
        st.caption("No transactions yet for the selected filters.")
    else:
        colors = [COST_TYPE_COLORS.get(t, MUTED) for t in type_df["cost_type"]]
        fig2 = go.Figure(
            go.Bar(
                x=type_df["amount"], y=type_df["cost_type"], orientation="h",
                marker_color=colors,
                hovertemplate="%{y}: %{x:,.2f} €<extra></extra>",
            )
        )
        fig2.update_layout(
            height=max(220, 50 * len(type_df) + 60),
            margin=dict(l=10, r=10, t=10, b=10),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(title="€", gridcolor=GRIDLINE, zeroline=False),
            yaxis=dict(title=""),
            font=dict(color=MUTED),
            showlegend=False,
        )
        st.plotly_chart(fig2, use_container_width=True)
else:
    st.caption("No transactions yet.")

st.divider()

# ---------------- Table: cost-to-complete breakdown ----------------
st.subheader("Cost-to-complete, by cost code")

table_df = summary.reset_index()[["cost_code", "budget", "actual", "committed", "spent", "remaining", "overrun", "pct_spent"]]
table_df["status"] = table_df.apply(
    lambda r: "⚠️ Over budget" if r["overrun"] > 0 else ("✅ On track" if r["budget"] else "—"), axis=1
)

st.dataframe(
    table_df,
    column_config={
        "cost_code": st.column_config.TextColumn("Cost code"),
        "budget": st.column_config.NumberColumn("Budget", format="€%.2f"),
        "actual": st.column_config.NumberColumn("Actual", format="€%.2f"),
        "committed": st.column_config.NumberColumn("Committed", format="€%.2f"),
        "spent": st.column_config.NumberColumn("Spent (actual+committed)", format="€%.2f"),
        "remaining": st.column_config.NumberColumn("Cost to complete", format="€%.2f"),
        "overrun": st.column_config.NumberColumn("Over budget by", format="€%.2f"),
        "pct_spent": st.column_config.ProgressColumn("% of budget spent", format="%.0f%%", min_value=0, max_value=max(100, table_df["pct_spent"].max() if not table_df.empty else 100)),
        "status": st.column_config.TextColumn("Status"),
    },
    hide_index=True,
    use_container_width=True,
)

st.caption(
    "Budget comes from the **Budget** page's budget lines. Actual = invoiced/paid-for costs. "
    "Committed = agreed costs (PO, signed contract) not yet invoiced. Add both via the **Transactions** page."
)

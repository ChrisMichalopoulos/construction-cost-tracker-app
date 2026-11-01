from datetime import date
import pandas as pd
import streamlit as st
import db
from ui_helpers import eur
from attachments_ui import render_attachments_section

st.set_page_config(page_title="Payments", page_icon="💳", layout="wide")
db.init_db()

st.title("💳 Payments")
st.caption("Record one or more payments against a transaction — supports partial payments over time.")

tx = db.df_transactions()

if tx.empty:
    st.caption("No transactions yet. Add one on the **Transactions** page first.")
    st.stop()

if "payment_editor_key_n" not in st.session_state:
    st.session_state.payment_editor_key_n = 0

# ---------------- Outstanding overview ----------------
st.subheader("Outstanding balances")

outstanding = tx[(tx["balance_due"] > 0.01)].copy()
show_all = st.checkbox("Show fully paid transactions too", value=False)
overview = tx.copy() if show_all else outstanding

if overview.empty:
    st.success("Nothing outstanding — everything is paid up. 🎉")
else:
    overview = overview.sort_values("balance_due", ascending=False)
    st.dataframe(
        overview[["date", "cost_code", "vendor_name", "description", "gross_amount", "paid_amount", "balance_due", "payment_status"]],
        column_config={
            "date": "Date", "cost_code": "Cost code", "vendor_name": "Vendor", "description": "Description",
            "gross_amount": st.column_config.NumberColumn("Total", format="€%.2f"),
            "paid_amount": st.column_config.NumberColumn("Paid", format="€%.2f"),
            "balance_due": st.column_config.NumberColumn("Balance due", format="€%.2f"),
            "payment_status": "Status",
        },
        hide_index=True,
        use_container_width=True,
    )
    st.caption(f"Total outstanding: **{eur(outstanding['balance_due'].sum())}** across {len(outstanding)} transaction(s).")

st.divider()

# ---------------- Record a payment ----------------
st.subheader("Record a payment")

tx_sorted = tx.sort_values("date", ascending=False)
tx_sorted["label"] = tx_sorted.apply(
    lambda r: f"{r['date']} — {r['cost_code']} — {r['description'] or '(no description)'} — "
              f"{r['vendor_name'] or 'no vendor'} — balance {eur(r['balance_due'])}",
    axis=1,
)
selected_label = st.selectbox("Transaction", tx_sorted["label"].tolist())
selected_row = tx_sorted[tx_sorted["label"] == selected_label].iloc[0]
selected_id = int(selected_row["id"])

m1, m2, m3 = st.columns(3)
m1.metric("Total (gross)", eur(selected_row["gross_amount"]))
m2.metric("Paid so far", eur(selected_row["paid_amount"]))
m3.metric("Balance due", eur(selected_row["balance_due"]))

with st.form("add_payment", clear_on_submit=True):
    c1, c2, c3 = st.columns(3)
    pay_date = c1.date_input("Payment date", value=date.today())
    pay_amount = c2.number_input("Amount", min_value=0.0, value=float(max(selected_row["balance_due"], 0)), step=1.0)
    pay_ref = c3.text_input("Reference (bank transfer code, receipt #, etc.)")
    pay_notes = st.text_input("Notes (optional)")
    pay_files = st.file_uploader("Attach the bank transfer receipt / proof of payment (optional)", accept_multiple_files=True)
    if st.form_submit_button("➕ Record payment", type="primary"):
        new_payment_id = db.add_payment(selected_id, pay_date.isoformat(), pay_amount, pay_ref, pay_notes)
        for f in pay_files or []:
            db.add_attachment("payment", new_payment_id, f.name, f.getvalue())
        st.session_state.payment_editor_key_n += 1  # force the grid to rebuild fresh - row positions may have shifted
        st.success("Payment recorded.")
        st.rerun()

st.divider()

# ---------------- Existing payments for selected transaction ----------------
st.subheader(f"Payment history for: {selected_row['description'] or '(no description)'}")

payments = db.df_payments(transaction_id=selected_id)
if payments.empty:
    st.caption("No payments recorded yet for this transaction.")
else:
    edit_df = payments[["id", "date", "amount", "reference", "notes"]].copy()
    file_counts = db.attachment_counts("payment")
    edit_df = edit_df.merge(file_counts, left_on="id", right_on="entity_id", how="left").drop(columns=["entity_id"], errors="ignore")
    edit_df["n"] = pd.to_numeric(edit_df["n"], errors="coerce").fillna(0).astype(int)
    edit_df = edit_df.rename(columns={"n": "files"})

    edited = st.data_editor(
        edit_df,
        key=f"payment_editor_{selected_id}_{st.session_state.payment_editor_key_n}",
        hide_index=True,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "id": st.column_config.NumberColumn("ID", disabled=True),
            "date": st.column_config.TextColumn("Date", required=True, help="YYYY-MM-DD"),
            "amount": st.column_config.NumberColumn("Amount", format="€%.2f", required=True),
            "reference": st.column_config.TextColumn("Reference"),
            "notes": st.column_config.TextColumn("Notes"),
            "files": st.column_config.NumberColumn("📎 Files", disabled=True),
        },
    )
    edited = edited.drop(columns=["files"], errors="ignore")

    if st.button("💾 Save payment changes", type="primary"):
        original_ids = set(payments["id"].dropna().astype(int).tolist())
        edited_ids = set(edited["id"].dropna().astype(int).tolist())
        for del_id in original_ids - edited_ids:
            db.delete_payment(int(del_id))
        for _, row in edited.iterrows():
            if pd.isna(row["id"]):
                db.add_payment(selected_id, row["date"], float(row["amount"]), row.get("reference", "") or "", row.get("notes", "") or "")
            else:
                db.update_payment(int(row["id"]), row["date"], float(row["amount"]), row.get("reference", "") or "", row.get("notes", "") or "")
        st.session_state.payment_editor_key_n += 1  # force the grid to rebuild fresh on the next render
        st.success("Saved.")
        st.rerun()

    st.divider()
    st.markdown("**📎 Attachments for a specific payment**")
    pay_options = payments.apply(
        lambda r: f"#{int(r['id'])} — {r['date']} — {eur(r['amount'])}" + (f" ({r['reference']})" if r['reference'] else ""),
        axis=1,
    ).tolist()
    pay_sel = st.selectbox("Payment", pay_options, key="payment_attach_select")
    sel_pay_id = int(pay_sel.split("—")[0].strip().lstrip("#"))
    render_attachments_section("payment", sel_pay_id, key_prefix=f"pay_{sel_pay_id}")

from datetime import date
import pandas as pd
import streamlit as st
import db
from ui_helpers import eur
from attachments_ui import render_attachments_section

st.set_page_config(page_title="Transactions", page_icon="🧾", layout="wide")
db.init_db()

st.title("🧾 Actual Costs & Committed Costs")
st.caption(
    "Every invoice, receipt, or agreed cost. Mark a cost **Committed** when you've agreed a price "
    "(PO, signed contract, verbal deal) but don't have an invoice yet — switch it to **Actual** once invoiced. "
    "Toggle VAT off for cash/no-invoice ('μαύρα') payments."
)

primary_codes = db.df_primary_cost_codes()
codes = db.df_cost_codes()
types = db.df_cost_types()
vendors = db.df_vendors()

if codes.empty:
    st.warning("Add at least one cost code first, on the **Cost Codes** page.")
    st.stop()
if primary_codes.empty:
    st.warning("Add at least one primary cost code (Building/Pools/Exterior) first, on the **Cost Codes** page.")
    st.stop()

primary_names = primary_codes["name"].tolist()
code_names = codes["name"].tolist()
type_names = ["—"] + types["name"].tolist()
vendor_names = ["—"] + vendors["name"].tolist()
status_options = ["actual", "committed"]
status_labels = {"actual": "Actual (invoiced)", "committed": "Committed (not yet invoiced)"}

if "tx_editor_key_n" not in st.session_state:
    st.session_state.tx_editor_key_n = 0

# ==================== ADD ====================
st.subheader("Add a transaction")

c0, c1, c2, c3, c4 = st.columns(5)
primary_sel = c0.selectbox("Primary (where)", primary_names)
tx_date = c1.date_input("Date", value=date.today())
code_sel = c2.selectbox("Secondary (what)", code_names)
type_sel = c3.selectbox("Cost type", type_names)
vendor_sel = c4.selectbox("Vendor / Subcontractor", vendor_names)

code_row = codes[codes["name"] == code_sel].iloc[0]
default_vat = float(code_row["default_vat_rate"])

c5, c6 = st.columns(2)
status_sel = c5.selectbox("Status", status_options, format_func=lambda s: status_labels[s])
description = c6.text_input("Description")

c7, c8, c9 = st.columns(3)
quantity = c7.number_input("Quantity (optional)", min_value=0.0, value=0.0, step=1.0)
unit = c8.text_input("Unit (optional)", value="")
net_amount = c9.number_input(
    "Net amount (before VAT)", value=0.0, step=1.0,
    help="Enter a negative number for a credit invoice (πιστωτικό) — a refund, discount, or returned goods.",
)

c10, c11, c12 = st.columns(3)
vat_applicable = c10.checkbox("VAT applicable", value=True)
vat_rate = c11.number_input("VAT rate", value=default_vat, step=0.01, format="%.2f", disabled=not vat_applicable)
gross_preview = round(net_amount * (1 + vat_rate), 2) if vat_applicable else round(net_amount, 2)
c12.metric("Total (gross)", eur(gross_preview))

c13, c14 = st.columns(2)
invoice_number = c13.text_input("Invoice number (optional, '-' if none)")
document_ref = c14.text_input("Document reference (path in your data/ folder, optional)")
notes = st.text_area("Notes (optional)")

if "tx_upload_key_n" not in st.session_state:
    st.session_state.tx_upload_key_n = 0
new_files = st.file_uploader(
    "Attach file(s) — invoice, receipt, photo, etc. (optional)",
    accept_multiple_files=True,
    key=f"tx_new_files_{st.session_state.tx_upload_key_n}",
)

if st.button("➕ Add transaction", type="primary"):
    primary_cost_code_id = int(primary_codes[primary_codes["name"] == primary_sel].iloc[0]["id"])
    cost_code_id = int(code_row["id"])
    cost_type_id = int(types[types["name"] == type_sel].iloc[0]["id"]) if type_sel != "—" else None
    vendor_id = int(vendors[vendors["name"] == vendor_sel].iloc[0]["id"]) if vendor_sel != "—" else None
    new_id = db.add_transaction(
        tx_date.isoformat(), primary_cost_code_id, cost_code_id, cost_type_id, vendor_id, description,
        quantity or None, unit, net_amount, vat_applicable, vat_rate, status_sel,
        invoice_number, document_ref, notes,
    )
    for f in new_files or []:
        db.add_attachment("transaction", new_id, f.name, f.getvalue())
    st.session_state.tx_upload_key_n += 1  # reset the uploader widget
    st.session_state.tx_editor_key_n += 1  # force the grid to rebuild fresh - row positions just shifted
    st.success("Transaction added.")
    st.rerun()

st.divider()

# ==================== FILTER + TABLE ====================
st.subheader("All transactions")

tx = db.df_transactions()

if tx.empty:
    st.caption("No transactions yet.")
    st.stop()

# ---------------- "Given to accountant" marker ----------------
given_mask = tx["given_to_accountant"].astype(bool)
if given_mask.any():
    last_given = tx.loc[given_mask, "given_to_accountant_date"].max()
    st.info(f"📨 Last handed to the accountant: **{last_given}** — {given_mask.sum()} invoice(s) given so far, "
            f"{(~given_mask).sum()} not yet given.")
else:
    st.info(f"📨 Nothing marked as given to the accountant yet — {len(tx)} invoice(s) pending.")

primary_filter_options = primary_names + ["—"]

fr1 = st.columns(4)
fr2 = st.columns(3)
f_primary = fr1[0].multiselect("Primary (where)", primary_filter_options, default=primary_filter_options)
f_codes = fr1[1].multiselect("Secondary (what)", code_names, default=code_names)
f_types = fr1[2].multiselect("Cost type", type_names, default=type_names)
f_status = fr1[3].multiselect("Status", status_options, default=status_options, format_func=lambda s: status_labels[s])
payment_status_options = ["Unpaid", "Partially Paid", "Paid", "Overpaid", "Credit", "Credit (adjusted)"]
f_pay = fr2[0].multiselect("Payment status", payment_status_options, default=payment_status_options)
f_acct = fr2[1].multiselect("Given to accountant?", ["Given", "Not given"], default=["Given", "Not given"])
f_search = fr2[2].text_input("Search (description / vendor / invoice)")

tx_display = tx.copy()
tx_display["cost_type"] = tx_display["cost_type"].fillna("—")
tx_display["vendor_name"] = tx_display["vendor_name"].fillna("—")
tx_display["primary_cost_code"] = tx_display["primary_cost_code"].fillna("—")
tx_display["accountant_display"] = tx_display["given_to_accountant"].astype(bool).map({True: "Given", False: "Not given"})

mask = (
    tx_display["primary_cost_code"].isin(f_primary)
    & tx_display["cost_code"].isin(f_codes)
    & tx_display["cost_type"].isin(f_types)
    & tx_display["status"].isin(f_status)
    & tx_display["payment_status"].isin(f_pay)
    & tx_display["accountant_display"].isin(f_acct)
)
if f_search.strip():
    s = f_search.strip().lower()
    mask &= (
        tx_display["description"].fillna("").str.lower().str.contains(s)
        | tx_display["vendor_name"].fillna("").str.lower().str.contains(s)
        | tx_display["invoice_number"].fillna("").str.lower().str.contains(s)
    )
filtered = tx_display[mask]

st.caption(f"Showing {len(filtered)} of {len(tx_display)} transactions.")

not_given_in_view = filtered[~filtered["given_to_accountant"].astype(bool)]
if not not_given_in_view.empty:
    if st.button(f"📨 Mark these {len(not_given_in_view)} shown transactions as given to the accountant today"):
        db.set_given_to_accountant(not_given_in_view["id"].astype(int).tolist(), True)
        st.session_state.tx_editor_key_n += 1  # force the grid to rebuild fresh with the updated values
        st.success(f"Marked {len(not_given_in_view)} transaction(s) as given to the accountant.")
        st.rerun()

edit_cols = ["id", "date", "primary_cost_code", "cost_code", "cost_type", "vendor_name", "status", "description",
             "quantity", "unit", "net_amount", "vat_applicable", "vat_rate", "gross_amount",
             "invoice_number", "document_ref", "notes", "paid_amount", "balance_due", "payment_status",
             "given_to_accountant", "given_to_accountant_date"]
edit_df = filtered[edit_cols].rename(columns={"vendor_name": "vendor"}).copy()
edit_df["given_to_accountant"] = edit_df["given_to_accountant"].astype(bool)

file_counts = db.attachment_counts("transaction")
edit_df = edit_df.merge(file_counts, left_on="id", right_on="entity_id", how="left").drop(columns=["entity_id"], errors="ignore")
edit_df["n"] = pd.to_numeric(edit_df["n"], errors="coerce").fillna(0).astype(int)
edit_df = edit_df.rename(columns={"n": "files"})

edited = st.data_editor(
    edit_df,
    key=f"tx_editor_{st.session_state.tx_editor_key_n}",
    hide_index=True,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "id": st.column_config.NumberColumn("ID", disabled=True),
        "date": st.column_config.TextColumn("Date", required=True, help="YYYY-MM-DD"),
        "primary_cost_code": st.column_config.SelectboxColumn("Primary (where)", options=["—"] + primary_names),
        "cost_code": st.column_config.SelectboxColumn("Secondary (what)", options=code_names, required=True),
        "cost_type": st.column_config.SelectboxColumn("Cost type", options=type_names),
        "vendor": st.column_config.SelectboxColumn("Vendor", options=vendor_names),
        "status": st.column_config.SelectboxColumn("Status", options=status_options, required=True),
        "description": st.column_config.TextColumn("Description"),
        "quantity": st.column_config.NumberColumn("Qty"),
        "unit": st.column_config.TextColumn("Unit"),
        "net_amount": st.column_config.NumberColumn("Net amount", format="€%.2f", required=True),
        "vat_applicable": st.column_config.CheckboxColumn("VAT?"),
        "vat_rate": st.column_config.NumberColumn("VAT rate", format="%.2f"),
        "gross_amount": st.column_config.NumberColumn("Gross (total)", format="€%.2f", disabled=True),
        "invoice_number": st.column_config.TextColumn("Invoice #"),
        "document_ref": st.column_config.TextColumn("Document ref."),
        "notes": st.column_config.TextColumn("Notes"),
        "paid_amount": st.column_config.NumberColumn("Paid so far", format="€%.2f", disabled=True),
        "balance_due": st.column_config.NumberColumn("Balance due", format="€%.2f", disabled=True),
        "payment_status": st.column_config.TextColumn("Payment status", disabled=True),
        "files": st.column_config.NumberColumn("📎 Files", disabled=True),
        "given_to_accountant": st.column_config.CheckboxColumn("📨 Given to accountant"),
        "given_to_accountant_date": st.column_config.TextColumn("Date given", help="YYYY-MM-DD — auto-filled with today if left blank and the box above is checked"),
    },
)
edited = edited.drop(columns=["files"], errors="ignore")

if st.button("💾 Save changes", type="primary"):
    original_ids = set(edit_df["id"].dropna().astype(int).tolist())
    edited_ids = set(edited["id"].dropna().astype(int).tolist())

    for del_id in original_ids - edited_ids:
        db.delete_transaction(int(del_id))

    name_to_code_id = dict(zip(codes["name"], codes["id"]))
    name_to_type_id = dict(zip(types["name"], types["id"]))
    name_to_vendor_id = dict(zip(vendors["name"], vendors["id"]))
    name_to_primary_id = dict(zip(primary_codes["name"], primary_codes["id"]))

    for _, row in edited.iterrows():
        if row["cost_code"] not in name_to_code_id:
            st.warning(f"Skipped a row — no cost code selected ({row.get('description', '')}).")
            continue
        primary_cost_code_id = name_to_primary_id.get(row.get("primary_cost_code"))
        cost_code_id = int(name_to_code_id[row["cost_code"]])
        cost_type_id = int(name_to_type_id[row["cost_type"]]) if row["cost_type"] in name_to_type_id else None
        vendor_id = int(name_to_vendor_id[row["vendor"]]) if row["vendor"] in name_to_vendor_id else None
        qty = row["quantity"] if pd.notna(row["quantity"]) else None
        vat_rate_v = float(row["vat_rate"]) if pd.notna(row["vat_rate"]) else 0.24
        vat_applicable_v = bool(row["vat_applicable"]) if pd.notna(row["vat_applicable"]) else True

        args = (
            row["date"], primary_cost_code_id, cost_code_id, cost_type_id, vendor_id, row.get("description", "") or "",
            qty, row.get("unit", "") or "", float(row["net_amount"]) if pd.notna(row["net_amount"]) else 0.0,
            vat_applicable_v, vat_rate_v, row["status"], row.get("invoice_number", "") or "",
            row.get("document_ref", "") or "", row.get("notes", "") or "",
        )
        if pd.isna(row["id"]):
            row_id = db.add_transaction(*args)
        else:
            row_id = int(row["id"])
            db.update_transaction(row_id, *args)

        given = bool(row.get("given_to_accountant", False))
        given_date = (row.get("given_to_accountant_date", "") or "").strip() or None
        db.set_given_to_accountant([row_id], given, given_date if given else None)
    st.session_state.tx_editor_key_n += 1  # force the grid to rebuild fresh on the next render
    st.success("Saved.")
    st.rerun()

st.download_button(
    "⬇️ Export all transactions to CSV",
    data=tx.to_csv(index=False).encode("utf-8-sig"),
    file_name="transactions_export.csv",
    mime="text/csv",
)

st.divider()
st.subheader("📎 Attachments")
st.caption("Attach the invoice, receipt, or a photo to a specific transaction.")

tx_options = tx.apply(
    lambda r: f"#{int(r['id'])} — {r['date']} — {r['cost_code']} — {r['description'] or '(no description)'}", axis=1
).tolist()
tx_sel = st.selectbox("Transaction", tx_options, key="tx_attach_select")
sel_tx_id = int(tx_sel.split("—")[0].strip().lstrip("#"))
render_attachments_section("transaction", sel_tx_id, key_prefix=f"tx_{sel_tx_id}")

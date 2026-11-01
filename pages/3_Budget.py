import streamlit as st
import pandas as pd
import db
from attachments_ui import render_attachments_section

st.set_page_config(page_title="Budget", page_icon="📋", layout="wide")
db.init_db()

st.title("📋 Budget Lines")
st.caption(
    "Your planned cost per cost code (and optionally per cost type), the same way you broke it down "
    "in your original budget spreadsheet — e.g. quantity × unit price for concrete (m³), tiling (m²), etc."
)

primary_codes = db.df_primary_cost_codes()
codes = db.df_cost_codes()
types = db.df_cost_types()

if codes.empty:
    st.warning("Add at least one cost code first, on the **Cost Codes** page.")
    st.stop()
if primary_codes.empty:
    st.warning("Add at least one primary cost code (Building/Pools/Exterior) first, on the **Cost Codes** page.")
    st.stop()

primary_names = primary_codes["name"].tolist()
code_names = codes["name"].tolist()
type_names = ["— (whole cost code, not split)"] + types["name"].tolist()

if "budget_editor_key_n" not in st.session_state:
    st.session_state.budget_editor_key_n = 0

# ---------------- Quick add ----------------
st.subheader("Add a budget line")

c0, c1, c2 = st.columns(3)
primary_sel = c0.selectbox("Primary cost code (where)", primary_names)
code_sel = c1.selectbox("Secondary cost code (what)", code_names)
type_sel = c2.selectbox("Cost type (optional)", type_names)
code_row = codes[codes["name"] == code_sel].iloc[0]
default_vat = float(code_row["default_vat_rate"])

description = st.text_input("Description (e.g. 'Θεμέλια', 'Foundations')")

c4, c5, c6, c7 = st.columns(4)
quantity = c4.number_input("Quantity (optional)", min_value=0.0, value=0.0, step=1.0)
unit = c5.text_input("Unit (e.g. κυβικά, τ.μ.)", value="")
unit_price = c6.number_input("Unit price, net (optional)", min_value=0.0, value=0.0, step=1.0)
vat_rate = c7.number_input("VAT rate", value=default_vat, step=0.01, format="%.2f")

suggested = round(quantity * unit_price, 2) if quantity and unit_price else 0.0
amount = st.number_input(
    "Budget amount, net (before VAT) — auto-suggested from quantity × unit price if both given",
    min_value=0.0, value=suggested, step=1.0,
)
notes = st.text_area("Notes (optional)")

if "budget_upload_key_n" not in st.session_state:
    st.session_state.budget_upload_key_n = 0
new_files = st.file_uploader(
    "Attach file(s) — contract, quote, etc. (optional)",
    accept_multiple_files=True,
    key=f"budget_new_files_{st.session_state.budget_upload_key_n}",
)

if st.button("➕ Add budget line", type="primary"):
    primary_cost_code_id = int(primary_codes[primary_codes["name"] == primary_sel].iloc[0]["id"])
    cost_code_id = int(code_row["id"])
    cost_type_id = None
    if type_sel != type_names[0]:
        cost_type_id = int(types[types["name"] == type_sel].iloc[0]["id"])
    new_id = db.add_budget_line(primary_cost_code_id, cost_code_id, cost_type_id, description, quantity or None, unit, unit_price or None, amount, vat_rate, notes)
    for f in new_files or []:
        db.add_attachment("budget_line", new_id, f.name, f.getvalue())
    st.session_state.budget_upload_key_n += 1  # reset the uploader widget
    st.session_state.budget_editor_key_n += 1  # force the grid to rebuild fresh - row positions may have shifted
    st.success("Budget line added.")
    st.rerun()

st.divider()

# ---------------- Edit / delete grid ----------------
st.subheader("All budget lines")
st.caption("Edit values directly in the table, or delete a row with the ✕ on the left. Click 'Save changes' when done.")

bl = db.df_budget_lines()

if bl.empty:
    st.caption("No budget lines yet.")
else:
    edit_df = bl[["id", "primary_cost_code", "cost_code", "cost_type", "description", "quantity", "unit", "unit_price", "amount", "vat_rate", "notes"]].copy()
    edit_df["cost_type"] = edit_df["cost_type"].fillna(type_names[0])
    edit_df["primary_cost_code"] = edit_df["primary_cost_code"].fillna("—")

    file_counts = db.attachment_counts("budget_line")
    edit_df = edit_df.merge(file_counts, left_on="id", right_on="entity_id", how="left").drop(columns=["entity_id"], errors="ignore")
    edit_df["n"] = pd.to_numeric(edit_df["n"], errors="coerce").fillna(0).astype(int)
    edit_df = edit_df.rename(columns={"n": "files"})

    edited = st.data_editor(
        edit_df,
        key=f"budget_editor_{st.session_state.budget_editor_key_n}",
        hide_index=True,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "id": st.column_config.NumberColumn("ID", disabled=True),
            "primary_cost_code": st.column_config.SelectboxColumn("Primary (where)", options=["—"] + primary_names),
            "cost_code": st.column_config.SelectboxColumn("Secondary (what)", options=code_names, required=True),
            "cost_type": st.column_config.SelectboxColumn("Cost type", options=type_names),
            "description": st.column_config.TextColumn("Description"),
            "quantity": st.column_config.NumberColumn("Qty"),
            "unit": st.column_config.TextColumn("Unit"),
            "unit_price": st.column_config.NumberColumn("Unit price (net)", format="€%.2f"),
            "amount": st.column_config.NumberColumn("Amount (net)", format="€%.2f", required=True),
            "vat_rate": st.column_config.NumberColumn("VAT rate", format="%.2f", required=True),
            "notes": st.column_config.TextColumn("Notes"),
            "files": st.column_config.NumberColumn("📎 Files", disabled=True),
        },
    )
    edited = edited.drop(columns=["files"], errors="ignore")

    if st.button("💾 Save changes", type="primary"):
        original_ids = set(edit_df["id"].dropna().astype(int).tolist())
        edited_ids = set(edited["id"].dropna().astype(int).tolist())

        for del_id in original_ids - edited_ids:
            db.delete_budget_line(int(del_id))

        name_to_code_id = dict(zip(codes["name"], codes["id"]))
        name_to_type_id = dict(zip(types["name"], types["id"]))
        name_to_primary_id = dict(zip(primary_codes["name"], primary_codes["id"]))

        for _, row in edited.iterrows():
            if row["cost_code"] not in name_to_code_id:
                st.warning(f"Skipped a row — no cost code selected ({row.get('description', '')}).")
                continue
            primary_cost_code_id = name_to_primary_id.get(row.get("primary_cost_code"))
            cost_code_id = int(name_to_code_id[row["cost_code"]])
            cost_type_id = None
            if row["cost_type"] in name_to_type_id:
                cost_type_id = int(name_to_type_id[row["cost_type"]])
            qty = row["quantity"] if pd.notna(row["quantity"]) else None
            unit_price_v = row["unit_price"] if pd.notna(row["unit_price"]) else None

            if pd.isna(row["id"]):
                db.add_budget_line(
                    primary_cost_code_id, cost_code_id, cost_type_id, row.get("description", "") or "",
                    qty, row.get("unit", "") or "", unit_price_v,
                    float(row["amount"]) if pd.notna(row["amount"]) else 0.0,
                    float(row["vat_rate"]) if pd.notna(row["vat_rate"]) else 0.24,
                    row.get("notes", "") or "",
                )
            else:
                db.update_budget_line(
                    int(row["id"]), primary_cost_code_id, cost_code_id, cost_type_id, row.get("description", "") or "",
                    qty, row.get("unit", "") or "", unit_price_v,
                    float(row["amount"]) if pd.notna(row["amount"]) else 0.0,
                    float(row["vat_rate"]) if pd.notna(row["vat_rate"]) else 0.24,
                    row.get("notes", "") or "",
                )
        st.session_state.budget_editor_key_n += 1  # force the grid to rebuild fresh on the next render
        st.success("Saved.")
        st.rerun()

    total_net = bl["amount"].sum()
    total_gross = bl["gross_amount"].sum()
    st.caption(f"**Total budget:** €{total_net:,.2f} net / €{total_gross:,.2f} incl. VAT")

    st.divider()
    st.subheader("📎 Attachments")
    st.caption("Attach the contract, quote, or any other file to a specific budget line.")

    bl_options = bl.apply(lambda r: f"#{int(r['id'])} — {r['cost_code']} — {r['description'] or '(no description)'}", axis=1).tolist()
    bl_sel = st.selectbox("Budget line", bl_options, key="budget_attach_select")
    sel_id = int(bl_sel.split("—")[0].strip().lstrip("#"))
    render_attachments_section("budget_line", sel_id, key_prefix=f"budget_{sel_id}")

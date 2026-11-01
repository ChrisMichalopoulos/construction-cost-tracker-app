import streamlit as st
import db

st.set_page_config(page_title="Cost Codes", page_icon="🏷️", layout="wide")
db.init_db()

st.title("🏷️ Cost Codes")
st.caption(
    "Two tiers: **Primary** is *where* the cost belongs (Building / Pools / Exterior). "
    "**Secondary** is *what* trade/material it is (Μπετά, Τοιχοποιία, Η/Μ...). "
    "Every budget line and transaction picks one of each."
)

# ==================== PRIMARY COST CODES ====================
st.header("1️⃣ Primary cost codes — \"where\"")

primary_codes = db.df_primary_cost_codes()

if primary_codes.empty:
    st.caption("No primary cost codes yet — add one below.")
else:
    for _, row in primary_codes.iterrows():
        with st.expander(f"**{row['name']}**" + (f" ({row['name_en']})" if row["name_en"] else "")):
            with st.form(f"edit_primary_{row['id']}"):
                c1, c2 = st.columns(2)
                name = c1.text_input("Name", value=row["name"], key=f"pname_{row['id']}")
                name_en = c2.text_input("English label (optional)", value=row["name_en"] or "", key=f"pen_{row['id']}")
                notes = st.text_area("Notes", value=row["notes"] or "", key=f"pnotes_{row['id']}")
                save, delete = st.columns(2)
                if save.form_submit_button("💾 Save changes"):
                    db.update_primary_cost_code(row["id"], name, name_en, notes)
                    st.success("Saved.")
                    st.rerun()
                if delete.form_submit_button("🗑️ Delete", type="secondary"):
                    try:
                        db.delete_primary_cost_code(row["id"])
                        st.success("Deleted.")
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))

st.subheader("Add a new primary cost code")
with st.form("add_primary", clear_on_submit=True):
    c1, c2 = st.columns(2)
    name = c1.text_input("Name (e.g. Κτίριο, Πισίνες, Εξωτερικός Χώρος, Γενικά...)")
    name_en = c2.text_input("English label (optional)")
    notes = st.text_area("Notes (optional)")
    if st.form_submit_button("➕ Add primary cost code"):
        if name.strip():
            db.add_primary_cost_code(name.strip(), name_en.strip(), notes.strip())
            st.success(f"Added '{name}'.")
            st.rerun()
        else:
            st.error("Name is required.")

st.divider()

# ==================== SECONDARY COST CODES ====================
st.header("2️⃣ Secondary cost codes — \"what\"")
st.caption("The trade/material breakdown — shared across all primary cost codes (e.g. the same 'Μπετά' applies under Building, Pools, or Exterior).")

codes = db.df_cost_codes()

if codes.empty:
    st.caption("No secondary cost codes yet — add one below.")
else:
    for _, row in codes.iterrows():
        with st.expander(f"**{row['name']}**" + (f" ({row['name_en']})" if row["name_en"] else "")):
            with st.form(f"edit_code_{row['id']}"):
                c1, c2, c3 = st.columns(3)
                name = c1.text_input("Name", value=row["name"], key=f"name_{row['id']}")
                name_en = c2.text_input("English label (optional)", value=row["name_en"] or "", key=f"en_{row['id']}")
                vat = c3.number_input("Default VAT rate", value=float(row["default_vat_rate"]), step=0.01, format="%.2f", key=f"vat_{row['id']}")
                notes = st.text_area("Notes", value=row["notes"] or "", key=f"notes_{row['id']}")
                save, delete = st.columns(2)
                if save.form_submit_button("💾 Save changes"):
                    db.update_cost_code(row["id"], name, name_en, vat, notes)
                    st.success("Saved.")
                    st.rerun()
                if delete.form_submit_button("🗑️ Delete", type="secondary"):
                    try:
                        db.delete_cost_code(row["id"])
                        st.success("Deleted.")
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))

st.subheader("Add a new secondary cost code")
with st.form("add_code", clear_on_submit=True):
    c1, c2, c3 = st.columns(3)
    name = c1.text_input("Name (e.g. Μπετά)")
    name_en = c2.text_input("English label (optional)")
    vat = c3.number_input("Default VAT rate", value=0.24, step=0.01, format="%.2f")
    notes = st.text_area("Notes (optional)")
    if st.form_submit_button("➕ Add secondary cost code"):
        if name.strip():
            db.add_cost_code(name.strip(), name_en.strip(), vat, notes.strip())
            st.success(f"Added '{name}'.")
            st.rerun()
        else:
            st.error("Name is required.")

st.divider()

# ==================== COST TYPES ====================
st.header("3️⃣ Cost types")
st.caption("Materials / Labor / Equipment / Other — a third, independent dimension used alongside the two cost codes.")

types = db.df_cost_types()
tc1, tc2 = st.columns([2, 1])
with tc1:
    st.dataframe(types[["name"]].rename(columns={"name": "Cost type"}), hide_index=True, use_container_width=True)
with tc2:
    with st.form("add_type", clear_on_submit=True):
        new_type = st.text_input("New cost type")
        if st.form_submit_button("➕ Add"):
            if new_type.strip():
                db.add_cost_type(new_type.strip())
                st.rerun()

if not types.empty:
    del_id = st.selectbox("Delete a cost type", options=[None] + types["id"].tolist(),
                           format_func=lambda i: "—" if i is None else types.loc[types["id"] == i, "name"].values[0])
    if del_id and st.button("🗑️ Delete selected cost type"):
        try:
            db.delete_cost_type(del_id)
            st.rerun()
        except ValueError as e:
            st.error(str(e))

import streamlit as st
import db

st.set_page_config(page_title="Vendors", page_icon="🏢", layout="wide")
db.init_db()

st.title("🏢 Vendors & Subcontractors")
st.caption("Everyone you pay: suppliers, subcontractors, the accountant, utility companies, etc.")

vendors = db.df_vendors()

st.subheader("Existing vendors")
if vendors.empty:
    st.caption("No vendors yet — add one below.")
else:
    for _, row in vendors.iterrows():
        subtitle = row["vendor_type"]
        if row["phone"]:
            subtitle += f" · 📞 {row['phone']}"
        if row["email"]:
            subtitle += f" · ✉️ {row['email']}"
        with st.expander(f"**{row['name']}** — {subtitle}"):
            with st.form(f"edit_vendor_{row['id']}"):
                c1, c2 = st.columns(2)
                name = c1.text_input("Name", value=row["name"], key=f"vn_{row['id']}")
                vtype = c2.selectbox(
                    "Type", ["Vendor", "Subcontractor", "Other"],
                    index=["Vendor", "Subcontractor", "Other"].index(row["vendor_type"]) if row["vendor_type"] in ["Vendor", "Subcontractor", "Other"] else 0,
                    key=f"vt_{row['id']}",
                )
                c3, c4 = st.columns(2)
                phone = c3.text_input("Phone", value=row["phone"] or "", key=f"vp_{row['id']}")
                email = c4.text_input("Email", value=row["email"] or "", key=f"ve_{row['id']}")
                notes = st.text_area("Notes", value=row["notes"] or "", key=f"vnotes_{row['id']}")
                save, delete = st.columns(2)
                if save.form_submit_button("💾 Save changes"):
                    db.update_vendor(row["id"], name, vtype, phone, email, notes)
                    st.success("Saved.")
                    st.rerun()
                if delete.form_submit_button("🗑️ Delete"):
                    try:
                        db.delete_vendor(row["id"])
                        st.success("Deleted.")
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))

st.divider()
st.subheader("Add a new vendor")
with st.form("add_vendor", clear_on_submit=True):
    c1, c2 = st.columns(2)
    name = c1.text_input("Name")
    vtype = c2.selectbox("Type", ["Vendor", "Subcontractor", "Other"])
    c3, c4 = st.columns(2)
    phone = c3.text_input("Phone (optional)")
    email = c4.text_input("Email (optional)")
    notes = st.text_area("Notes (optional)")
    if st.form_submit_button("➕ Add vendor"):
        if name.strip():
            db.add_vendor(name.strip(), vtype, phone.strip(), email.strip(), notes.strip())
            st.success(f"Added '{name}'.")
            st.rerun()
        else:
            st.error("Name is required.")

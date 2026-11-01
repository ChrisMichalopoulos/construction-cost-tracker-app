"""Reusable 'attach a file' widget for budget lines and transactions."""

import streamlit as st
import db


def render_attachments_section(entity_type: str, entity_id: int, key_prefix: str):
    """entity_type: 'budget_line' or 'transaction'. key_prefix must be unique per call site."""
    atts = db.df_attachments(entity_type, entity_id)

    if atts.empty:
        st.caption("No files attached yet.")
    else:
        for _, row in atts.iterrows():
            c1, c2, c3 = st.columns([5, 1, 1])
            label = f"📄 {row['file_name']}"
            if row["notes"]:
                label += f" — _{row['notes']}_"
            c1.markdown(f"{label}  \n<span style='opacity:0.6;font-size:0.85em'>uploaded {row['uploaded_at']}</span>",
                        unsafe_allow_html=True)
            file_name, data = db.get_attachment_bytes(int(row["id"]))
            if data is not None:
                c2.download_button("⬇️", data=data, file_name=file_name, mime=db.guess_mime(file_name),
                                    key=f"{key_prefix}_dl_{row['id']}")
            else:
                c2.caption("missing")
            if c3.button("🗑️", key=f"{key_prefix}_del_{row['id']}"):
                db.delete_attachment(int(row["id"]))
                st.rerun()

    with st.form(f"{key_prefix}_upload_form", clear_on_submit=True):
        files = st.file_uploader(
            "Add file(s) — contract, invoice, receipt, photo...",
            accept_multiple_files=True,
            key=f"{key_prefix}_uploader",
        )
        note = st.text_input("Note (optional)", key=f"{key_prefix}_note")
        if st.form_submit_button("📤 Upload"):
            if files:
                for f in files:
                    db.add_attachment(entity_type, entity_id, f.name, f.getvalue(), note)
                st.success(f"Uploaded {len(files)} file(s).")
                st.rerun()
            else:
                st.warning("Choose a file first.")

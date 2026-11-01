import io
import zipfile
from datetime import datetime

import streamlit as st
import db

st.set_page_config(page_title="Backup", page_icon="💾", layout="wide")
db.init_db()

st.title("💾 Backup")
st.caption(
    f"Your data lives only at `{db.APP_DATA_DIR}` — it is **not** part of git. "
    "Download a backup here periodically and save it somewhere else (an external drive, "
    "OneDrive/Google Drive, etc.)."
)

DB_FILE = db.DB_PATH
ATTACH_DIR = db.ATTACHMENTS_DIR

# ---------------- Current state ----------------
st.subheader("What's in your data right now")

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Cost codes", len(db.df_cost_codes()))
c2.metric("Vendors", len(db.df_vendors()))
c3.metric("Budget lines", len(db.df_budget_lines()))
c4.metric("Transactions", len(db.df_transactions()))
c5.metric("Payments", len(db.df_payments()))

attachment_files = list(ATTACH_DIR.rglob("*")) if ATTACH_DIR.exists() else []
attachment_files = [f for f in attachment_files if f.is_file()]
total_attachment_size = sum(f.stat().st_size for f in attachment_files)
db_size = DB_FILE.stat().st_size if DB_FILE.exists() else 0

st.caption(
    f"Database file: **{db_size / 1024:,.1f} KB** · "
    f"Attached files: **{len(attachment_files)}** ({total_attachment_size / 1024 / 1024:,.2f} MB)"
)
if DB_FILE.exists():
    last_modified = datetime.fromtimestamp(DB_FILE.stat().st_mtime)
    st.caption(f"Database last changed: {last_modified.strftime('%Y-%m-%d %H:%M')}")

st.divider()

# ---------------- Create backup ----------------
st.subheader("Download a backup")
st.caption("Bundles the database and every attached file into a single .zip.")

if st.button("📦 Create backup now", type="primary"):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        if DB_FILE.exists():
            zf.write(DB_FILE, arcname="tracker.db")
        for f in attachment_files:
            zf.write(f, arcname=str(Path("attachments") / f.relative_to(ATTACH_DIR)))
    buffer.seek(0)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    st.session_state["backup_zip"] = buffer.getvalue()
    st.session_state["backup_name"] = f"cost_tracker_backup_{timestamp}.zip"

if "backup_zip" in st.session_state:
    st.download_button(
        f"⬇️ Download {st.session_state['backup_name']}",
        data=st.session_state["backup_zip"],
        file_name=st.session_state["backup_name"],
        mime="application/zip",
        type="primary",
    )
    st.success("Backup ready — save it somewhere other than this computer (cloud drive, USB stick, etc.).")

st.divider()

# ---------------- Restore instructions ----------------
st.subheader("Restoring from a backup")
st.caption(
    "There's no restore button yet, to avoid accidentally overwriting live data by mistake. "
    "To restore manually: close the app, extract the zip, and replace the `app_data` folder in the "
    "project directory with its contents (`tracker.db` + the `attachments` folder), then restart the app."
)

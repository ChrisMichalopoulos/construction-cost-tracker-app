"""
Database layer for the construction cost tracker.

SQLite file lives at <data dir>/tracker.db (kept separate from the `data/`
folder, which holds your existing documents/invoices/photos).

By default <data dir> is `app_data/` next to this file. To point the app at
a different location (e.g. a OneDrive-synced folder, so you can move between
your own devices), either:
  - set the environment variable COST_TRACKER_DATA_DIR to the folder path, or
  - create a file named `data_location.txt` next to this file, containing
    just the folder path on its own line.
Both are checked before falling back to the default `app_data/`.

Schema
------
primary_cost_codes : the "where" (e.g. Κτίριο/Building, Πισίνες/Pools, Εξωτερικός Χώρος/Exterior).
                      A budget line/transaction's primary + secondary code together answer
                      "which part of the project, and which trade on it".
cost_codes     : the "what" / trade breakdown (e.g. Μπετά, Τοιχοποιία, Η/Μ...) — referred to as
                 the secondary cost code in the UI once primary codes exist
cost_types     : Υλικά (Materials) / Εργατικά (Labor) / Εξοπλισμός (Equipment) / Άλλο (Other)
vendors        : suppliers & subcontractors
budget_lines   : planned cost, per primary+secondary cost code (+ optional cost type), optional qty/unit
transactions   : actual costs & committed costs (POs/agreements not yet invoiced)
payments       : one or more payments made against a transaction (supports partial payments)
attachments    : files (contracts, invoices, receipts, photos) attached to a budget line,
                 transaction, or individual payment, stored under app_data/attachments/
                 and tracked here by metadata
"""

import os
import sqlite3
import uuid
import mimetypes
from pathlib import Path
from datetime import date, datetime
import pandas as pd


def _resolve_app_data_dir() -> Path:
    """Where tracker.db + attachments/ live. Override via the COST_TRACKER_DATA_DIR
    env var, or a `data_location.txt` file next to this one (see module docstring)."""
    env_value = os.environ.get("COST_TRACKER_DATA_DIR", "").strip()
    if env_value:
        return Path(env_value).expanduser()

    config_file = Path(__file__).parent / "data_location.txt"
    if config_file.exists():
        configured = config_file.read_text(encoding="utf-8").strip()
        if configured:
            return Path(configured).expanduser()

    return Path(__file__).parent / "app_data"


APP_DATA_DIR = _resolve_app_data_dir()
DB_PATH = APP_DATA_DIR / "tracker.db"
ATTACHMENTS_DIR = APP_DATA_DIR / "attachments"

DEFAULT_COST_CODES = [
    # (name, name_en, default_vat_rate, notes)
    ("Χωματουργικά", "Earthworks", 0.24, ""),
    ("Μπετά", "Concrete", 0.24, ""),
    ("Σιδερά", "Rebar / Ironwork", 0.24, ""),
    ("Τοιχοποιία", "Masonry", 0.24, ""),
    ("Ηλεκτρολογικά", "Electrical", 0.24, ""),
    ("Υδραυλικά", "Plumbing", 0.24, ""),
    ("Πισίνες", "Pool", 0.24, ""),
    ("Εξωτερικοί Χώροι", "Outdoor areas", 0.24, ""),
    ("Επενδύσεις", "Finishes / Cladding", 0.24, ""),
    ("ΔΕΔΔΗΕ / Συνδέσεις", "Utility connections", 0.24, ""),
    ("Διοικητικά / Φορολογικά", "Admin / Tax", 0.24, ""),
    ("Λοιπά", "Other / Extra", 0.24, ""),
]

DEFAULT_COST_TYPES = ["Υλικά (Materials)", "Εργατικά (Labor)", "Εξοπλισμός (Equipment)", "Άλλο (Other)"]

DEFAULT_PRIMARY_CODES = [
    # (name, name_en)
    ("Κτίριο", "Building"),
    ("Πισίνες", "Pools"),
    ("Εξωτερικός Χώρος", "Exterior"),
]


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS cost_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            name_en TEXT DEFAULT '',
            default_vat_rate REAL NOT NULL DEFAULT 0.24,
            sort_order INTEGER DEFAULT 0,
            notes TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS cost_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            sort_order INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS primary_cost_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            name_en TEXT DEFAULT '',
            sort_order INTEGER DEFAULT 0,
            notes TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS vendors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            vendor_type TEXT DEFAULT 'Vendor',
            contact TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            email TEXT DEFAULT '',
            notes TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS budget_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            primary_cost_code_id INTEGER REFERENCES primary_cost_codes(id),
            cost_code_id INTEGER NOT NULL REFERENCES cost_codes(id),
            cost_type_id INTEGER REFERENCES cost_types(id),
            description TEXT DEFAULT '',
            quantity REAL,
            unit TEXT DEFAULT '',
            unit_price REAL,
            amount REAL NOT NULL DEFAULT 0,
            vat_rate REAL NOT NULL DEFAULT 0.24,
            notes TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            primary_cost_code_id INTEGER REFERENCES primary_cost_codes(id),
            cost_code_id INTEGER NOT NULL REFERENCES cost_codes(id),
            cost_type_id INTEGER REFERENCES cost_types(id),
            vendor_id INTEGER REFERENCES vendors(id),
            description TEXT DEFAULT '',
            quantity REAL,
            unit TEXT DEFAULT '',
            net_amount REAL NOT NULL DEFAULT 0,
            vat_applicable INTEGER NOT NULL DEFAULT 1,
            vat_rate REAL NOT NULL DEFAULT 0.24,
            gross_amount REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'actual' CHECK(status IN ('committed','actual')),
            invoice_number TEXT DEFAULT '',
            document_ref TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            given_to_accountant INTEGER NOT NULL DEFAULT 0,
            given_to_accountant_date TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
            date TEXT NOT NULL,
            amount REAL NOT NULL DEFAULT 0,
            reference TEXT DEFAULT '',
            notes TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL CHECK(entity_type IN ('budget_line','transaction','payment')),
            entity_id INTEGER NOT NULL,
            file_name TEXT NOT NULL,
            stored_name TEXT NOT NULL,
            uploaded_at TEXT NOT NULL,
            notes TEXT DEFAULT ''
        );
        """
    )
    conn.commit()

    # Migrate older databases whose `attachments` CHECK constraint predates 'payment'
    att_sql = cur.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='attachments'"
    ).fetchone()
    if att_sql and "'payment'" not in att_sql["sql"]:
        cur.executescript(
            """
            ALTER TABLE attachments RENAME TO attachments_old;
            CREATE TABLE attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL CHECK(entity_type IN ('budget_line','transaction','payment')),
                entity_id INTEGER NOT NULL,
                file_name TEXT NOT NULL,
                stored_name TEXT NOT NULL,
                uploaded_at TEXT NOT NULL,
                notes TEXT DEFAULT ''
            );
            INSERT INTO attachments (id, entity_type, entity_id, file_name, stored_name, uploaded_at, notes)
                SELECT id, entity_type, entity_id, file_name, stored_name, uploaded_at, notes FROM attachments_old;
            DROP TABLE attachments_old;
            """
        )
        conn.commit()

    # Migrate older databases created before `phone`/`email` existed on vendors
    existing_cols = {row["name"] for row in cur.execute("PRAGMA table_info(vendors)").fetchall()}
    if "phone" not in existing_cols:
        cur.execute("ALTER TABLE vendors ADD COLUMN phone TEXT DEFAULT ''")
    if "email" not in existing_cols:
        cur.execute("ALTER TABLE vendors ADD COLUMN email TEXT DEFAULT ''")
    if "phone" not in existing_cols or "email" not in existing_cols:
        # Best-effort backfill from the old free-text `contact` field
        for row in cur.execute(
            "SELECT id, contact FROM vendors WHERE contact != '' AND (phone = '' OR phone IS NULL) AND (email = '' OR email IS NULL)"
        ).fetchall():
            contact = (row["contact"] or "").strip()
            if "@" in contact:
                cur.execute("UPDATE vendors SET email=? WHERE id=?", (contact, row["id"]))
            else:
                cur.execute("UPDATE vendors SET phone=? WHERE id=?", (contact, row["id"]))
    conn.commit()

    # Migrate older databases created before the accountant hand-off marker existed
    tx_cols = {row["name"] for row in cur.execute("PRAGMA table_info(transactions)").fetchall()}
    if "given_to_accountant" not in tx_cols:
        cur.execute("ALTER TABLE transactions ADD COLUMN given_to_accountant INTEGER NOT NULL DEFAULT 0")
    if "given_to_accountant_date" not in tx_cols:
        cur.execute("ALTER TABLE transactions ADD COLUMN given_to_accountant_date TEXT DEFAULT ''")
    conn.commit()

    # Migrate older databases created before primary cost codes (Building/Pools/Exterior) existed
    tx_cols = {row["name"] for row in cur.execute("PRAGMA table_info(transactions)").fetchall()}
    if "primary_cost_code_id" not in tx_cols:
        cur.execute("ALTER TABLE transactions ADD COLUMN primary_cost_code_id INTEGER REFERENCES primary_cost_codes(id)")
    bl_cols = {row["name"] for row in cur.execute("PRAGMA table_info(budget_lines)").fetchall()}
    if "primary_cost_code_id" not in bl_cols:
        cur.execute("ALTER TABLE budget_lines ADD COLUMN primary_cost_code_id INTEGER REFERENCES primary_cost_codes(id)")
    conn.commit()

    # Seed defaults only on first run (empty tables)
    if cur.execute("SELECT COUNT(*) FROM cost_codes").fetchone()[0] == 0:
        for i, (name, name_en, vat, notes) in enumerate(DEFAULT_COST_CODES):
            cur.execute(
                "INSERT INTO cost_codes (name, name_en, default_vat_rate, sort_order, notes) VALUES (?,?,?,?,?)",
                (name, name_en, vat, i, notes),
            )
    if cur.execute("SELECT COUNT(*) FROM cost_types").fetchone()[0] == 0:
        for i, name in enumerate(DEFAULT_COST_TYPES):
            cur.execute("INSERT INTO cost_types (name, sort_order) VALUES (?,?)", (name, i))
    if cur.execute("SELECT COUNT(*) FROM primary_cost_codes").fetchone()[0] == 0:
        for i, (name, name_en) in enumerate(DEFAULT_PRIMARY_CODES):
            cur.execute(
                "INSERT INTO primary_cost_codes (name, name_en, sort_order) VALUES (?,?,?)", (name, name_en, i)
            )
    conn.commit()
    conn.close()


def _compute_gross(net_amount: float, vat_applicable: bool, vat_rate: float) -> float:
    net_amount = net_amount or 0
    vat_rate = vat_rate or 0
    return round(net_amount * (1 + vat_rate), 2) if vat_applicable else round(net_amount, 2)


# ---------- Cost codes ----------

def df_cost_codes() -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM cost_codes ORDER BY sort_order, name", conn)
    conn.close()
    return df


def add_cost_code(name, name_en, default_vat_rate, notes=""):
    conn = get_connection()
    max_order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) FROM cost_codes").fetchone()[0]
    conn.execute(
        "INSERT INTO cost_codes (name, name_en, default_vat_rate, sort_order, notes) VALUES (?,?,?,?,?)",
        (name, name_en, default_vat_rate, max_order + 1, notes),
    )
    conn.commit()
    conn.close()


def update_cost_code(id_, name, name_en, default_vat_rate, notes=""):
    conn = get_connection()
    conn.execute(
        "UPDATE cost_codes SET name=?, name_en=?, default_vat_rate=?, notes=? WHERE id=?",
        (name, name_en, default_vat_rate, notes, id_),
    )
    conn.commit()
    conn.close()


def delete_cost_code(id_):
    conn = get_connection()
    in_use = conn.execute(
        "SELECT (SELECT COUNT(*) FROM budget_lines WHERE cost_code_id=?) + "
        "(SELECT COUNT(*) FROM transactions WHERE cost_code_id=?)",
        (id_, id_),
    ).fetchone()[0]
    if in_use:
        conn.close()
        raise ValueError("This cost code is used by existing budget lines or transactions and can't be deleted.")
    conn.execute("DELETE FROM cost_codes WHERE id=?", (id_,))
    conn.commit()
    conn.close()


# ---------- Primary cost codes ("where": Building / Pools / Exterior) ----------

def df_primary_cost_codes() -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM primary_cost_codes ORDER BY sort_order, name", conn)
    conn.close()
    return df


def add_primary_cost_code(name, name_en, notes=""):
    conn = get_connection()
    max_order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) FROM primary_cost_codes").fetchone()[0]
    conn.execute(
        "INSERT INTO primary_cost_codes (name, name_en, sort_order, notes) VALUES (?,?,?,?)",
        (name, name_en, max_order + 1, notes),
    )
    conn.commit()
    conn.close()


def update_primary_cost_code(id_, name, name_en, notes=""):
    conn = get_connection()
    conn.execute(
        "UPDATE primary_cost_codes SET name=?, name_en=?, notes=? WHERE id=?",
        (name, name_en, notes, id_),
    )
    conn.commit()
    conn.close()


def delete_primary_cost_code(id_):
    conn = get_connection()
    in_use = conn.execute(
        "SELECT (SELECT COUNT(*) FROM budget_lines WHERE primary_cost_code_id=?) + "
        "(SELECT COUNT(*) FROM transactions WHERE primary_cost_code_id=?)",
        (id_, id_),
    ).fetchone()[0]
    if in_use:
        conn.close()
        raise ValueError("This primary cost code is used by existing budget lines or transactions and can't be deleted.")
    conn.execute("DELETE FROM primary_cost_codes WHERE id=?", (id_,))
    conn.commit()
    conn.close()


# ---------- Cost types ----------

def df_cost_types() -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM cost_types ORDER BY sort_order, name", conn)
    conn.close()
    return df


def add_cost_type(name):
    conn = get_connection()
    max_order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) FROM cost_types").fetchone()[0]
    conn.execute("INSERT INTO cost_types (name, sort_order) VALUES (?,?)", (name, max_order + 1))
    conn.commit()
    conn.close()


def delete_cost_type(id_):
    conn = get_connection()
    in_use = conn.execute(
        "SELECT (SELECT COUNT(*) FROM budget_lines WHERE cost_type_id=?) + "
        "(SELECT COUNT(*) FROM transactions WHERE cost_type_id=?)",
        (id_, id_),
    ).fetchone()[0]
    if in_use:
        conn.close()
        raise ValueError("This cost type is used by existing budget lines or transactions and can't be deleted.")
    conn.execute("DELETE FROM cost_types WHERE id=?", (id_,))
    conn.commit()
    conn.close()


# ---------- Vendors ----------

def df_vendors() -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM vendors ORDER BY name", conn)
    conn.close()
    return df


def add_vendor(name, vendor_type, phone="", email="", notes=""):
    conn = get_connection()
    conn.execute(
        "INSERT INTO vendors (name, vendor_type, phone, email, notes) VALUES (?,?,?,?,?)",
        (name, vendor_type, phone, email, notes),
    )
    conn.commit()
    conn.close()


def update_vendor(id_, name, vendor_type, phone="", email="", notes=""):
    conn = get_connection()
    conn.execute(
        "UPDATE vendors SET name=?, vendor_type=?, phone=?, email=?, notes=? WHERE id=?",
        (name, vendor_type, phone, email, notes, id_),
    )
    conn.commit()
    conn.close()


def delete_vendor(id_):
    conn = get_connection()
    in_use = conn.execute("SELECT COUNT(*) FROM transactions WHERE vendor_id=?", (id_,)).fetchone()[0]
    if in_use:
        conn.close()
        raise ValueError("This vendor is used by existing transactions and can't be deleted.")
    conn.execute("DELETE FROM vendors WHERE id=?", (id_,))
    conn.commit()
    conn.close()


# ---------- Budget lines ----------

def df_budget_lines() -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query(
        """
        SELECT bl.*, cc.name AS cost_code, ct.name AS cost_type, pc.name AS primary_cost_code
        FROM budget_lines bl
        JOIN cost_codes cc ON cc.id = bl.cost_code_id
        LEFT JOIN cost_types ct ON ct.id = bl.cost_type_id
        LEFT JOIN primary_cost_codes pc ON pc.id = bl.primary_cost_code_id
        ORDER BY cc.sort_order, bl.id
        """,
        conn,
    )
    conn.close()
    if not df.empty:
        df["gross_amount"] = (df["amount"] * (1 + df["vat_rate"])).round(2)
    return df


def add_budget_line(primary_cost_code_id, cost_code_id, cost_type_id, description, quantity, unit, unit_price, amount, vat_rate, notes=""):
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO budget_lines
           (primary_cost_code_id, cost_code_id, cost_type_id, description, quantity, unit, unit_price, amount, vat_rate, notes)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (primary_cost_code_id, cost_code_id, cost_type_id, description, quantity, unit, unit_price, amount, vat_rate, notes),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def update_budget_line(id_, primary_cost_code_id, cost_code_id, cost_type_id, description, quantity, unit, unit_price, amount, vat_rate, notes=""):
    conn = get_connection()
    conn.execute(
        """UPDATE budget_lines SET primary_cost_code_id=?, cost_code_id=?, cost_type_id=?, description=?, quantity=?, unit=?,
           unit_price=?, amount=?, vat_rate=?, notes=? WHERE id=?""",
        (primary_cost_code_id, cost_code_id, cost_type_id, description, quantity, unit, unit_price, amount, vat_rate, notes, id_),
    )
    conn.commit()
    conn.close()


def delete_budget_line(id_):
    _delete_attachments_for("budget_line", id_)
    conn = get_connection()
    conn.execute("DELETE FROM budget_lines WHERE id=?", (id_,))
    conn.commit()
    conn.close()


# ---------- Transactions ----------

def df_transactions() -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query(
        """
        SELECT t.*, cc.name AS cost_code, ct.name AS cost_type, v.name AS vendor_name,
               pc.name AS primary_cost_code
        FROM transactions t
        JOIN cost_codes cc ON cc.id = t.cost_code_id
        LEFT JOIN cost_types ct ON ct.id = t.cost_type_id
        LEFT JOIN vendors v ON v.id = t.vendor_id
        LEFT JOIN primary_cost_codes pc ON pc.id = t.primary_cost_code_id
        ORDER BY t.date DESC, t.id DESC
        """,
        conn,
    )
    if not df.empty:
        paid = pd.read_sql_query(
            "SELECT transaction_id, COALESCE(SUM(amount),0) AS paid_amount FROM payments GROUP BY transaction_id",
            conn,
        )
        df = df.merge(paid, left_on="id", right_on="transaction_id", how="left")
        df["paid_amount"] = pd.to_numeric(df["paid_amount"], errors="coerce").fillna(0.0)
        df.drop(columns=[c for c in ["transaction_id"] if c in df.columns], inplace=True)

        def pay_status(row):
            if row["paid_amount"] <= 0:
                return "Unpaid"
            if row["paid_amount"] + 0.01 >= row["gross_amount"]:
                return "Overpaid" if row["paid_amount"] > row["gross_amount"] + 0.01 else "Paid"
            return "Partially Paid"

        df["payment_status"] = df.apply(pay_status, axis=1)
        df["balance_due"] = (df["gross_amount"] - df["paid_amount"]).round(2)
    conn.close()
    return df


def add_transaction(date_, primary_cost_code_id, cost_code_id, cost_type_id, vendor_id, description, quantity, unit,
                     net_amount, vat_applicable, vat_rate, status, invoice_number, document_ref, notes=""):
    gross = _compute_gross(net_amount, vat_applicable, vat_rate)
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO transactions
           (date, primary_cost_code_id, cost_code_id, cost_type_id, vendor_id, description, quantity, unit, net_amount,
            vat_applicable, vat_rate, gross_amount, status, invoice_number, document_ref, notes)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (date_, primary_cost_code_id, cost_code_id, cost_type_id, vendor_id, description, quantity, unit, net_amount,
         int(vat_applicable), vat_rate, gross, status, invoice_number, document_ref, notes),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def update_transaction(id_, date_, primary_cost_code_id, cost_code_id, cost_type_id, vendor_id, description, quantity, unit,
                        net_amount, vat_applicable, vat_rate, status, invoice_number, document_ref, notes=""):
    gross = _compute_gross(net_amount, vat_applicable, vat_rate)
    conn = get_connection()
    conn.execute(
        """UPDATE transactions SET date=?, primary_cost_code_id=?, cost_code_id=?, cost_type_id=?, vendor_id=?, description=?,
           quantity=?, unit=?, net_amount=?, vat_applicable=?, vat_rate=?, gross_amount=?, status=?,
           invoice_number=?, document_ref=?, notes=? WHERE id=?""",
        (date_, primary_cost_code_id, cost_code_id, cost_type_id, vendor_id, description, quantity, unit, net_amount,
         int(vat_applicable), vat_rate, gross, status, invoice_number, document_ref, notes, id_),
    )
    conn.commit()
    conn.close()


def set_given_to_accountant(transaction_ids, given: bool, date_=None):
    """Mark one or more transactions as handed to the accountant (or un-mark them)."""
    if not transaction_ids:
        return
    date_value = (date_ or date.today().isoformat()) if given else ""
    conn = get_connection()
    conn.executemany(
        "UPDATE transactions SET given_to_accountant=?, given_to_accountant_date=? WHERE id=?",
        [(int(given), date_value, int(tid)) for tid in transaction_ids],
    )
    conn.commit()
    conn.close()


def delete_transaction(id_):
    _delete_attachments_for("transaction", id_)
    conn = get_connection()
    conn.execute("DELETE FROM transactions WHERE id=?", (id_,))
    conn.commit()
    conn.close()


# ---------- Payments ----------

def df_payments(transaction_id=None) -> pd.DataFrame:
    conn = get_connection()
    if transaction_id is not None:
        df = pd.read_sql_query(
            "SELECT * FROM payments WHERE transaction_id=? ORDER BY date", conn, params=(transaction_id,)
        )
    else:
        df = pd.read_sql_query(
            """
            SELECT p.*, t.description AS transaction_description, t.date AS transaction_date,
                   cc.name AS cost_code, t.gross_amount
            FROM payments p
            JOIN transactions t ON t.id = p.transaction_id
            JOIN cost_codes cc ON cc.id = t.cost_code_id
            ORDER BY p.date DESC, p.id DESC
            """,
            conn,
        )
    conn.close()
    return df


def add_payment(transaction_id, date_, amount, reference="", notes=""):
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO payments (transaction_id, date, amount, reference, notes) VALUES (?,?,?,?,?)",
        (transaction_id, date_, amount, reference, notes),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def update_payment(id_, date_, amount, reference="", notes=""):
    conn = get_connection()
    conn.execute(
        "UPDATE payments SET date=?, amount=?, reference=?, notes=? WHERE id=?",
        (date_, amount, reference, notes, id_),
    )
    conn.commit()
    conn.close()


def delete_payment(id_):
    _delete_attachments_for("payment", id_)
    conn = get_connection()
    conn.execute("DELETE FROM payments WHERE id=?", (id_,))
    conn.commit()
    conn.close()


# ---------- Attachments (contracts, invoices, etc.) ----------
#
# Files are stored on disk under app_data/attachments/<entity_type>/<entity_id>/<stored_name>,
# keeping the SQLite file small. This is separate from the `document_ref` text field, which
# still works as a pointer into your existing `data/` folder for files already filed there.

def _entity_dir(entity_type: str, entity_id: int) -> Path:
    d = ATTACHMENTS_DIR / entity_type / str(entity_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def add_attachment(entity_type: str, entity_id: int, file_name: str, data: bytes, notes: str = "") -> int:
    stored_name = f"{uuid.uuid4().hex}{Path(file_name).suffix}"
    path = _entity_dir(entity_type, entity_id) / stored_name
    path.write_bytes(data)

    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO attachments (entity_type, entity_id, file_name, stored_name, uploaded_at, notes) VALUES (?,?,?,?,?,?)",
        (entity_type, entity_id, file_name, stored_name, datetime.now().isoformat(timespec="seconds"), notes),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def df_attachments(entity_type: str, entity_id: int) -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT * FROM attachments WHERE entity_type=? AND entity_id=? ORDER BY uploaded_at",
        conn, params=(entity_type, entity_id),
    )
    conn.close()
    return df


def attachment_count(entity_type: str, entity_id: int) -> int:
    conn = get_connection()
    n = conn.execute(
        "SELECT COUNT(*) FROM attachments WHERE entity_type=? AND entity_id=?", (entity_type, entity_id)
    ).fetchone()[0]
    conn.close()
    return n


def attachment_counts(entity_type: str) -> pd.DataFrame:
    """entity_id -> number of attachments, for badging a list/table."""
    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT entity_id, COUNT(*) AS n FROM attachments WHERE entity_type=? GROUP BY entity_id",
        conn, params=(entity_type,),
    )
    conn.close()
    return df


def get_attachment_bytes(attachment_id: int):
    """Returns (file_name, bytes) for one attachment, or (None, None) if missing."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM attachments WHERE id=?", (attachment_id,)).fetchone()
    conn.close()
    if row is None:
        return None, None
    path = ATTACHMENTS_DIR / row["entity_type"] / str(row["entity_id"]) / row["stored_name"]
    if not path.exists():
        return row["file_name"], None
    return row["file_name"], path.read_bytes()


def delete_attachment(attachment_id: int):
    conn = get_connection()
    row = conn.execute("SELECT * FROM attachments WHERE id=?", (attachment_id,)).fetchone()
    if row is not None:
        path = ATTACHMENTS_DIR / row["entity_type"] / str(row["entity_id"]) / row["stored_name"]
        path.unlink(missing_ok=True)
        conn.execute("DELETE FROM attachments WHERE id=?", (attachment_id,))
        conn.commit()
    conn.close()


def _delete_attachments_for(entity_type: str, entity_id: int):
    """Cascade-delete all attachments (DB rows + files) for a budget line/transaction being deleted."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id FROM attachments WHERE entity_type=? AND entity_id=?", (entity_type, entity_id)
    ).fetchall()
    conn.close()
    for r in rows:
        delete_attachment(r["id"])


def guess_mime(file_name: str) -> str:
    mime, _ = mimetypes.guess_type(file_name)
    return mime or "application/octet-stream"


# ---------- Summaries for dashboard ----------

def budget_vs_actual_by_costcode() -> pd.DataFrame:
    """One row per cost code: budget (gross), actual (gross), committed (gross)."""
    conn = get_connection()
    budget = pd.read_sql_query(
        "SELECT cost_code_id, SUM(amount * (1 + vat_rate)) AS budget FROM budget_lines GROUP BY cost_code_id",
        conn,
    )
    actual = pd.read_sql_query(
        "SELECT cost_code_id, SUM(gross_amount) AS actual FROM transactions WHERE status='actual' GROUP BY cost_code_id",
        conn,
    )
    committed = pd.read_sql_query(
        "SELECT cost_code_id, SUM(gross_amount) AS committed FROM transactions WHERE status='committed' GROUP BY cost_code_id",
        conn,
    )
    codes = pd.read_sql_query("SELECT id AS cost_code_id, name AS cost_code, sort_order FROM cost_codes", conn)
    conn.close()

    df = codes.merge(budget, on="cost_code_id", how="left")
    df = df.merge(actual, on="cost_code_id", how="left")
    df = df.merge(committed, on="cost_code_id", how="left")
    for col in ["budget", "actual", "committed"]:
        df[col] = df[col].fillna(0).round(2)
    df["spent"] = (df["actual"] + df["committed"]).round(2)
    df["remaining"] = (df["budget"] - df["spent"]).clip(lower=0).round(2)
    df["overrun"] = (df["spent"] - df["budget"]).clip(lower=0).round(2)
    df = df.sort_values("sort_order")
    return df


def spend_by_costtype() -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query(
        """
        SELECT ct.name AS cost_type, SUM(t.gross_amount) AS amount
        FROM transactions t
        LEFT JOIN cost_types ct ON ct.id = t.cost_type_id
        WHERE t.status = 'actual'
        GROUP BY ct.name
        """,
        conn,
    )
    conn.close()
    df["cost_type"] = df["cost_type"].fillna("Unassigned")
    df["amount"] = df["amount"].fillna(0).round(2)
    return df.sort_values("amount", ascending=False)


def overall_kpis() -> dict:
    df = budget_vs_actual_by_costcode()
    return {
        "budget": float(df["budget"].sum()),
        "actual": float(df["actual"].sum()),
        "committed": float(df["committed"].sum()),
        "spent": float(df["spent"].sum()),
        "remaining": float((df["budget"].sum() - df["spent"].sum())),
    }

# Construction Cost Tracker

A local, single-user Streamlit app for tracking budget vs. actual costs on a
self-build construction project — replacing a scattered collection of Excel
files and a Power BI dashboard that became hard to maintain.

All data is stored locally in a SQLite database. Nothing is sent anywhere.

## Contents

- [Quick start](#quick-start)
- [How the data is organized](#how-the-data-is-organized)
- [Pages](#pages)
- [VAT handling](#vat-handling)
- [Committed vs. Actual](#committed-vs-actual)
- [Payments](#payments)
- [File attachments](#file-attachments)
- [Accountant hand-off tracking](#accountant-hand-off-tracking)
- [Backup](#backup)
- [Changing where `app_data` lives](#changing-where-app_data-lives)
- [Project structure](#project-structure)
- [Tech stack](#tech-stack)

## Quick start

```
pip install -r requirements.txt
streamlit run app.py
```

Opens at `http://localhost:8501`. The database is created automatically on
first run at `app_data/tracker.db`, pre-seeded with a default set of cost
codes and cost types.

## How the data is organized

Every cost in the project is classified along **three independent
dimensions**, plus optionally a vendor:

| Dimension                     | Answers                   | Examples                                                                                                                | Managed on      |
| ----------------------------- | ------------------------- | ----------------------------------------------------------------------------------------------------------------------- | --------------- |
| **Primary cost code**   | *Where*                 | Κτίριο (Building), Πισίνες (Pools), Εξωτερικός Χώρος (Exterior)                             | Cost Codes page |
| **Secondary cost code** | *What* (trade/material) | Μπετά, Σιδερά, Τοιχοποιία, Ηλεκτρολογικά, Υδραυλικά, Επενδύσεις... | Cost Codes page |
| **Cost type**           | *What kind*             | Υλικά (Materials), Εργατικά (Labor), Εξοπλισμός (Equipment), Άλλο (Other)                    | Cost Codes page |

The secondary cost code list is **shared** across all primary codes — e.g.
"Μπετά" is one single entity, selectable under Building, Pools, or Exterior
alike, not a separate copy per area.

On top of that:

- **Budget lines** (Budget page) — your planned cost per primary + secondary
  cost code (+ optional cost type), optionally broken down by quantity × unit
  price (matching how the original Excel budget was built — e.g. m³ of
  concrete, m² of tiling).
- **Transactions** (Transactions page) — every real cost: an actual invoiced
  cost, or a committed cost you've agreed to but not yet invoiced. Each one
  carries net amount, VAT, status, vendor, invoice number, and an optional
  document reference.
- **Payments** (Payments page) — one or more payments recorded against a
  transaction, so partial payments over time are tracked properly rather than
  a single paid/unpaid flag.
- **Vendors** — suppliers and subcontractors, each with phone/email contact
  details.

## Pages

| Page                        | Purpose                                                                                                                                                                                             |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Home** (`app.py`) | Dashboard: budget vs. actual vs. committed, by primary cost code and by secondary cost code; spend by cost type; cost-to-complete table; filterable by primary code, secondary code, and cost type. |
| **Cost Codes**        | Manage primary cost codes, secondary cost codes (with a default VAT rate each), and cost types.                                                                                                     |
| **Vendors**           | Manage suppliers/subcontractors — name, type, phone, email, notes.                                                                                                                                 |
| **Budget**            | Add/edit/delete budget lines; attach files (e.g. a quote) to a line.                                                                                                                                |
| **Transactions**      | Add/edit/delete actual and committed costs; search/filter; bulk "mark as given to accountant"; attach files (e.g. an invoice) to a transaction; export to CSV.                                      |
| **Payments**          | Record payments against a transaction (supports partial payments); see outstanding balances; attach files (e.g. a bank transfer receipt) to a payment.                                              |
| **Backup**            | Download a `.zip` of the database + every attached file.                                                                                                                                          |

## VAT handling

Every transaction stores:

- **Net amount** (before VAT)
- **VAT applicable** — a checkbox
- **VAT rate** — defaults to the secondary cost code's default rate, editable per line

Gross amount = `net × (1 + VAT rate)` when VAT applies, otherwise gross = net.
Unchecking "VAT applicable" is how you record a cash/no-invoice payment
(what the original spreadsheets called "μαύρα") — it sets VAT to 0% for that
one line without touching the default rate used elsewhere.

## Committed vs. Actual

Every transaction has a `status`:

- **Actual (invoiced)** — you have a real invoice/receipt. The cost is
  confirmed and final.
- **Committed** — you've agreed a price (signed contract, verbal deal, PO)
  but don't have an invoice yet.

Both count toward the dashboard's cost-to-complete calculation
(`Budget − (Actual + Committed) = remaining`), so a committed cost you
haven't been invoiced for yet still reduces how much budget you think you
have left. Once the real invoice arrives, edit the row and flip its status
to Actual.

This is independent of **payment status** (Unpaid / Partially Paid / Paid /
Overpaid), which tracks whether you've actually handed over the money —
visible on both the Transactions and Payments pages.

## Payments

Payments are their own records, one-to-many against a transaction, so a
transaction can be paid off in several partial installments over time (as
seen in the original spreadsheets' running-total payment logs). Payment
status is derived automatically by comparing the sum of its payments to its
gross amount.

## File attachments

Contracts, invoices, receipts, and photos can be attached directly to a
**budget line**, a **transaction**, or an individual **payment** — uploaded
through the app and stored under `app_data/attachments/`, tracked in the
database by metadata (original filename, upload date, notes). Each one shows
a 📎 file count in its respective grid, with a dedicated "Attachments"
section per page to upload/download/delete.

This is separate from the `document_ref` text field on a transaction, which
is just a free-text pointer into an existing folder of documents you already
keep organized outside the app.

## Accountant hand-off tracking

Each transaction can be marked `given_to_accountant` with a date. The
Transactions page shows a running marker — *"Last handed to the accountant:
\<date> — N given so far, M not yet given"* — plus a filter and a one-click
"mark these N shown transactions as given today" bulk action, so you always
know exactly what's left to hand over for the next batch.

## Backup

Your data lives **only** on this computer (or wherever you've pointed it —
see below) and is **not** part of git: `app_data/` is git-ignored on purpose,
since a SQLite file and binary attachments don't belong in version control,
and the data itself can include sensitive financial documents.

Use the **Backup** page to download a `.zip` of the database + all attached
files whenever you want a snapshot, and save it somewhere else (a cloud
drive, a USB stick). There's deliberately no one-click restore button — see
the Backup page for manual restore instructions.

## Changing where `app_data` lives

By default, the database and attachments live at `app_data/` right next to
the app's code (`db.py`'s folder). You can point the app at a different
folder instead — e.g. a OneDrive-synced folder, a different drive, a NAS
mount — without touching any code, using either of two methods. The app
checks them in this order, falling back to the default `app_data/` if
neither is set:

**Method 1 — a config file (simplest):**

1. Create a plain text file named `data_location.txt` in the same folder as `db.py`
2. Put the full folder path on the first line, nothing else, e.g.:
   ```
   C:\Users\xrism\OneDrive\CostTrackerData
   ```
3. Restart the app — it will now read/write `tracker.db` and `attachments/`
   under that folder instead of the local `app_data/`

**Method 2 — an environment variable:**

Set `COST_TRACKER_DATA_DIR` to the target folder before launching the app, e.g.:

```
set COST_TRACKER_DATA_DIR=C:\Users\xrism\OneDrive\CostTrackerData
streamlit run app.py
```

(`data_location.txt` is simpler for a one-time setup; the environment
variable is handy if you want to script the launch, e.g. from a `.bat` file.)

**Moving existing data:** changing the path only changes where the app
*looks* — it doesn't move your existing files for you. If you already have
data in the local `app_data/`, move (not copy) `app_data/tracker.db` and
`app_data/attachments/` into the new folder yourself before switching, so
you don't end up with two separate databases.

`data_location.txt` is specific to each computer (your laptop and desktop
might use different drive letters/usernames), so it's excluded from git —
create it separately on each device, pointing at the same shared folder if
you're using one.

**Important caveat if you point this at a cloud-synced folder (OneDrive,
etc.):** SQLite and cloud file-sync don't mix well under concurrent access.
Only ever run the app on **one device at a time** — fully close it and wait
for the sync client to finish (green checkmark) before opening it on another
device. This works fine as a way to move your single working copy between
your own computers; it is **not** a way to get true simultaneous
multi-device access. For that, you'd run the app on one always-on machine
and access it from other devices over the network/browser instead.

## Project structure

```
app.py                  Home dashboard
db.py                   SQLite schema, migrations, and all data access
ui_helpers.py            Currency formatting + chart color palette
attachments_ui.py       Shared "attach a file" widget (used by 3 pages)
pages/
  1_Cost_Codes.py        Primary/secondary cost codes + cost types
  2_Vendors.py            Vendors (name, type, phone, email, notes)
  3_Budget.py             Budget lines
  4_Transactions.py       Actual/committed costs, accountant hand-off
  5_Payments.py           Payments against transactions
  6_Backup.py             Database + attachments backup download
requirements.txt
.gitignore
```

The database schema evolves through small, additive migrations in
`db.init_db()` — each one checks whether a column/table already exists
before adding it, so upgrading to a newer version of the app never loses
existing data.

## Tech stack

- [Streamlit](https://streamlit.io/) — UI, in pure Python, no separate frontend
- [SQLite](https://www.sqlite.org/) (via the standard library `sqlite3`) — local database
- [pandas](https://pandas.pydata.org/) — data wrangling between the database and the UI
- [Plotly](https://plotly.com/python/) — dashboard charts

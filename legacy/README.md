# legacy/ (reference only)

Code from the first MVP draft (PR #1), written for the previous 9-table schema
(`price_sources`, `materials`, `price_observations`, `boq_items`, `match_events`, ...).
It does **not** run against the current database (`schema.sql`, 4 tables) and is not
called by `main.py`.

Kept so the team can copy useful pieces into the new modules, for example:

- `boq_platform/cleansing.py`: unit and text normalisation, price validation
- `boq_platform/ingest.py`: reading BOQ `.xlsx`/`.csv` files (`read_boq_excel`)
- `boq_platform/analytics.py`, `dashboard.py`: report and console-table ideas
- `boq_platform/matching.py`: matching BOQ names to materials

Contents: `boq_platform/` (package), `main_old.py` (old menu), `notebooks/`,
`docs/Data_Cleansing.md`, `schema_old.sql` (the schema this code expects).

When you copy code out, rewrite its SQL for the new tables and use `db.get_connection()`.

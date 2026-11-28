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

---

The sections below are the first draft's README text, describing how `main_old.py` worked.

### Main menu

1. Create a project using `house`, `room`, or `item` scope.
2. Import Dataset 2 from the TPSO monthly JSON file (option 1, recommended). A copy is kept in `data_raw/`; re-importing is safe (unchanged rows are skipped, corrected prices update the same row).
3. Import retailer prices or quotations using `templates/retail_prices_template.csv`. Re-importing the same file is safe: unchanged rows are skipped and corrected prices update the existing row.
4. Import a BOQ file, `.xlsx` or `.csv` (required fields: item/material name, quantity, unit; optional specification, unit price, room and MOC material code). `templates/boq_template.csv` can be filled in and imported directly.
5. Enter BOQ lines manually; type `DONE` to finish.
6. Read/update/soft-delete BOQ lines. Soft delete keeps match evidence and audit history. When editing, leave a field blank to keep it or type `-` to clear the BOQ unit price.
7. Display SQL-based cost insights: BOQ vs official Dataset 2 price, top-cost lines, retailer Top 3 and action plans.
8. Review observations held for a human quality decision.
9. Check row counts against the course's 30-row rule.
10. Match retailer prices that could not be tied to a material. The store SKU is remembered, so the next snapshot from that store matches automatically.

### Comparison rules

- **BOQ vs official price (Dataset 2):** each matched BOQ line is compared with the latest official monthly price (plus VAT) for the same material, unit and project area. Use project area code `10` for the ส่วนกลาง file. Units are never converted: steel is priced per ตัน in Dataset 2, so a BOQ line in เส้น will not be compared until its unit matches. The fastest way to match is to put the 16-digit TPSO code in the BOQ `material_code` column. BOQ prices more than 10% above it raise `NEGOTIATE_PRICE`; more than 10% below raise `CHECK_UNDERBUDGET`.
- **Getting retailer prices into Top 3:** a retailer row is matched only by (1) a store SKU already confirmed for that store, (2) the `moc_com_code` column in the CSV, or (3) an exact MOC name/alias with the same unit. Store product names rarely equal MOC names, so fill `moc_com_code`, or confirm unmatched rows once in menu 10.
- Retailer comparisons require a matched canonical material, identical normalized unit, a fresh snapshot, a VAT-inclusive price and matching project province (or an explicitly unlocated online snapshot when the project has no province).
- A store can be ranked by total basket only if it has comparable prices for every active matched BOQ line. Partial coverage is shown but is not called the cheapest total basket.
- Retailer basket totals are product-price subtotals and exclude shipping, which can be order/branch-specific. Estimated savings are calculated only against BOQ lines with reference prices and a complete comparable retailer basket. This is an estimate, not realized savings; verify stock, specifications and delivery with the seller.
- Exact code/name/alias matches with compatible units can be auto-matched. Fuzzy names are suggestions requiring user review. Every candidate decision is stored in `match_events` and appended to `logs/match_audit.jsonl`.

### Append-only logs and output

- `logs/audit.jsonl`: imports, rejects, project/BOQ changes and application events.
- `logs/match_audit.jsonl`: each candidate match, evidence, score and user/system decision.
- Both files append one JSON event per line. Do not clear them during the demo.
- Events raised inside a database transaction are written after it ends; if it was rolled back, the line carries `"transaction": "rolled_back"`, so the log never claims a change that is not in the database.
- Excel insight exports go to `exports/`.
- Raw downloaded official responses go to `data_raw/`; those folders are git-ignored.

### MVP limitations

- Menu 9 reports row counts. The course brief expects 30+ rows in each non-reference table. Populate with genuine historical prices, real BOQ lines and observed matching decisions; never create synthetic records to reach the threshold. The small price-source registry is a limited reference table.
- Retail prices are snapshots supplied by a user-maintained CSV or quotation; site automation is not included.
- Unit conversion is intentionally conservative. Unverified package conversions are not performed.
- The official API price is a provincial average and is not the same as an individual retailer's delivered quote.
- No quantity takeoff from PDF drawings is included. Users must provide quantities in BOQ/Excel or enter them.

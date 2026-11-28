# BOQ Intelligence Platform - MVP

Python + MySQL workflow for importing a BOQ, comparing its material lines with official and retailer price observations, recording explainable matching evidence, and presenting SQL-based insights with next actions. The primary interface is `main.py`; the Jupyter notebook demonstrates the same modules. No Streamlit application is included.

## Data scope

- **Official source (Dataset 2):** TPSO/MOC monthly construction-material prices, imported from a saved JSON file in the TPSO monthly price layout (`commodityCode`, `commodityNameTH`, `unitName`, `curYear` (พ.ศ.), `curMonth`, `priceCur`, `type`, `typeName`). The file used for development is `10.json`: area `10` = ส่วนกลาง, October 2569 (2026), 5,461 commodities. Prices are cash prices **excluding VAT and delivery**; the system adds 7% VAT (`VAT_RATE`) before comparing them with BOQ prices.
  - Put the file in `data_raw/` (git-ignored, per the team rule) and import it with menu 2 → option 1. Every team member needs their own copy of the file.
  - The online endpoint `dataapi.moc.go.th/csi-indexes` was tested on 2026-11-23: it returns a national price **index** (`index_id`, `price_index`, base year 2015) and ignores `province_code`/`com_code`, so it cannot supply unit prices. Menu 2 → option 2 is kept only for reference.
  - With one month of data, month-to-month trend actions (`MONITOR_PRICE`) appear only after a second month's file is imported.
- **Retail price snapshots:** Thai Watsadu, HomePro, DoHome, Global House and Hiachet. The MVP imports a standardized CSV snapshot or user quote. It does not scrape websites. Store pages, branch, observation date, product specification, unit, VAT and shipping must be recorded before prices are compared.
- The monthly price file follows the TPSO layout of Dataset 1/8 (index.tpso.go.th); it is loaded once, as the official Dataset 2 source, and never a second time from another feed. National construction material index (Dataset 3) and standard construction prices (Dataset 4) are not mixed into the unit-price table. BOQCraft is a workflow reference, not a dataset.

Retailer links:

- <https://www.thaiwatsadu.com/>
- <https://www.homepro.co.th/>
- <https://www.dohome.co.th/>
- <https://globalhouse.co.th/>
- <https://www.hiachet.com/>

## Setup

1. Install Python 3.10+ and MySQL 8+. (Check with `python -V` inside the virtual environment.)
2. Create and activate a virtual environment, then install dependencies:

   ```bash
   python -m venv .venv
   # Windows PowerShell: .venv\Scripts\Activate.ps1
   # macOS/Linux: source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and enter the MySQL connection settings.
4. Set `DB_NAME=boq_intelligence` in `.env`, then build the database one of two ways (see [Database](#database)):
   - from a teammate's dump file (structure + data), or
   - from `schema.sql` (structure only, empty tables).
5. Start the integrated Python interface:

   ```bash
   python main.py
   ```

6. To demonstrate the complete workflow in Jupyter:

   ```bash
   jupyter lab notebooks/BOQ_Intelligence_MVP.ipynb
   ```

## Database

> **Schema changed (2026-11-28).** `schema.sql` now holds the Workbench design: `master_product`, `tpso_price`, `material_prices_long`, `user_input_batch` (diagram: `docs/er_diagram.png`, model: `docs/boq_model.mwb`, notes: `docs/ER_Diagram.md`). The Python code in `boq_platform/`, `main.py` and `menus/` was written for the previous 9-table schema (`price_sources`, `materials`, `price_observations`, `boq_items`, …) and **will not run against the new database until it is rewritten**. The previous schema is in git history (commit `d98bc44`).

Each team member runs MySQL 8 on their own computer. Git carries the structure (`schema.sql`); data moves between team members as a dump file.

**Create empty tables from `schema.sql`.** In MySQL Workbench: File → Open SQL Script → `schema.sql` → Execute (⚡). Or:

```bash
mysql -u root -p < schema.sql
```

**Export a dump (the person who has the data).** In Workbench: Server → Data Export → tick `boq_intelligence` → Export to Self-Contained File → tick Include Create Schema → Start Export. Or:

```bash
mysqldump -u root -p --databases boq_intelligence --no-tablespaces --set-gtid-purged=OFF > boq_intelligence_dump.sql
```

**Import a dump.** In Workbench: Server → Data Import → Import from Self-Contained File → Start Import. Or:

```bash
mysql -u root -p < boq_intelligence_dump.sql
```

Rules:

- Change tables only by editing `schema.sql` (and the Workbench model) on your branch and opening a pull request. Do not change tables only in your own MySQL.
- After a schema change is merged, make a new dump; everyone re-imports it.
- Dumps must contain real data only. Share a dump over 50 MB through Google Drive instead of git (GitHub rejects files over 100 MB).
- `.env` (your MySQL password) is never committed.

## Main menu

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

## Comparison rules

- **BOQ vs official price (Dataset 2):** each matched BOQ line is compared with the latest official monthly price (plus VAT) for the same material, unit and project area. Use project area code `10` for the ส่วนกลาง file. Units are never converted: steel is priced per ตัน in Dataset 2, so a BOQ line in เส้น will not be compared until its unit matches. The fastest way to match is to put the 16-digit TPSO code in the BOQ `material_code` column. BOQ prices more than 10% above it raise `NEGOTIATE_PRICE`; more than 10% below raise `CHECK_UNDERBUDGET`.
- **Getting retailer prices into Top 3:** a retailer row is matched only by (1) a store SKU already confirmed for that store, (2) the `moc_com_code` column in the CSV, or (3) an exact MOC name/alias with the same unit. Store product names rarely equal MOC names, so fill `moc_com_code`, or confirm unmatched rows once in menu 10.
- Retailer comparisons require a matched canonical material, identical normalized unit, a fresh snapshot, a VAT-inclusive price and matching project province (or an explicitly unlocated online snapshot when the project has no province).
- A store can be ranked by total basket only if it has comparable prices for every active matched BOQ line. Partial coverage is shown but is not called the cheapest total basket.
- Retailer basket totals are product-price subtotals and exclude shipping, which can be order/branch-specific. Estimated savings are calculated only against BOQ lines with reference prices and a complete comparable retailer basket. This is an estimate, not realized savings; verify stock, specifications and delivery with the seller.
- Exact code/name/alias matches with compatible units can be auto-matched. Fuzzy names are suggestions requiring user review. Every candidate decision is stored in `match_events` and appended to `logs/match_audit.jsonl`.

## Append-only logs and output

- `logs/audit.jsonl`: imports, rejects, project/BOQ changes and application events.
- `logs/match_audit.jsonl`: each candidate match, evidence, score and user/system decision.
- Both files append one JSON event per line. Do not clear them during the demo.
- Events raised inside a database transaction are written after it ends; if it was rolled back, the line carries `"transaction": "rolled_back"`, so the log never claims a change that is not in the database.
- Excel insight exports go to `exports/`.
- Raw downloaded official responses go to `data_raw/`; those folders are git-ignored.

## MVP limitations

- Menu 9 reports row counts. The course brief expects 30+ rows in each non-reference table. Populate with genuine historical prices, real BOQ lines and observed matching decisions; never create synthetic records to reach the threshold. The small price-source registry is a limited reference table.
- Retail prices are snapshots supplied by a user-maintained CSV or quotation; site automation is not included.
- Unit conversion is intentionally conservative. Unverified package conversions are not performed.
- The official API price is a provincial average and is not the same as an individual retailer's delivered quote.
- No quantity takeoff from PDF drawings is included. Users must provide quantities in BOQ/Excel or enter them.

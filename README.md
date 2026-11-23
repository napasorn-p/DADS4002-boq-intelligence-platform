# BOQ Intelligence Platform - MVP

Python + MySQL workflow for importing a BOQ, comparing its material lines with official and retailer price observations, recording explainable matching evidence, and presenting SQL-based insights with next actions. The primary interface is `main.py`; the Jupyter notebook demonstrates the same modules. No Streamlit application is included.

## Data scope

- **Official source:** Dataset 2, MOC Open Data CSI Product Indexes. It provides monthly province-level average construction material prices, product codes, names and units. API documentation: <https://data.moc.go.th/OpenData/CSIProductIndexes>.
- **Retail price snapshots:** Thai Watsadu, HomePro, DoHome, Global House and Hiachet. The MVP imports a standardized CSV snapshot or user quote. It does not scrape websites. Store pages, branch, observation date, product specification, unit, VAT and shipping must be recorded before prices are compared.
- Dataset 1/8 are references/API documentation for TPSO and are not loaded as a duplicate of Dataset 2. National construction material index (Dataset 3) and standard construction prices (Dataset 4) are not mixed into the unit-price table. BOQCraft is a workflow reference, not a dataset.

Retailer links:

- <https://www.thaiwatsadu.com/>
- <https://www.homepro.co.th/>
- <https://www.dohome.co.th/>
- <https://globalhouse.co.th/>
- <https://www.hiachet.com/>

## Setup

1. Install Python 3.10+ and MySQL 8+.
2. Create and activate a virtual environment, then install dependencies:

   ```bash
   python -m venv .venv
   # Windows PowerShell: .venv\Scripts\Activate.ps1
   # macOS/Linux: source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and enter the MySQL connection settings.
4. Run `schema.sql` in MySQL. It creates the database, tables, and the official/retailer source registry.
5. Start the integrated Python interface:

   ```bash
   python main.py
   ```

6. To demonstrate the complete workflow in Jupyter:

   ```bash
   jupyter lab notebooks/BOQ_Intelligence_MVP.ipynb
   ```

## Main menu

1. Create a project using `house`, `room`, or `item` scope.
2. Import Dataset 2 using province code and Gregorian year range. The raw API response is saved under `data_raw/`.
3. Import retailer prices or quotations using `templates/retail_prices_template.csv`.
4. Import a BOQ Excel file (required fields: item/material name, quantity, unit; optional specification, unit price and room).
5. Enter BOQ lines manually; type `DONE` to finish.
6. Read/update/soft-delete BOQ lines. Soft delete keeps match evidence and audit history.
7. Display SQL-based cost insights, retailer price rankings and action plans.
8. Review observations held for a human quality decision.

## Comparison rules

- Retailer comparisons require a matched canonical material, identical normalized unit, a fresh snapshot, a VAT-inclusive price and matching project province (or an explicitly unlocated online snapshot when the project has no province).
- A store can be ranked by total basket only if it has comparable prices for every active matched BOQ line. Partial coverage is shown but is not called the cheapest total basket.
- Retailer basket totals are product-price subtotals and exclude shipping, which can be order/branch-specific. Estimated savings are calculated only against BOQ lines with reference prices and a complete comparable retailer basket. This is an estimate, not realized savings; verify stock, specifications and delivery with the seller.
- Exact code/name/alias matches with compatible units can be auto-matched. Fuzzy names are suggestions requiring user review. Every candidate decision is stored in `match_events` and appended to `logs/match_audit.jsonl`.

## Append-only logs and output

- `logs/audit.jsonl`: imports, rejects, project/BOQ changes and application events.
- `logs/match_audit.jsonl`: each candidate match, evidence, score and user/system decision.
- Both files append one JSON event per line. Do not clear them during the demo.
- Excel insight exports go to `exports/`.
- Raw downloaded official responses go to `data_raw/`; those folders are git-ignored.

## MVP limitations

- Menu 9 reports row counts. The course brief expects 30+ rows in each non-reference table. Populate with genuine historical prices, real BOQ lines and observed matching decisions; never create synthetic records to reach the threshold. The small price-source registry is a limited reference table.
- Retail prices are snapshots supplied by a user-maintained CSV or quotation; site automation is not included.
- Unit conversion is intentionally conservative. Unverified package conversions are not performed.
- The official API price is a provincial average and is not the same as an individual retailer's delivered quote.
- No quantity takeoff from PDF drawings is included. Users must provide quantities in BOQ/Excel or enter them.

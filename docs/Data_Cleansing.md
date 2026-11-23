# Dataset choices and cleansing sequence

## Final MVP sources

1. **MOC Open Data CSI Product Indexes (Dataset 2):** primary official monthly price data. API fields include province, product code/name, unit, year/month and average price.
2. **Retail snapshots:** Thai Watsadu, HomePro, DoHome, Global House and Hiachet. Import through the CSV template or capture a user quote. No unattended scraping is performed.

Dataset 1 and Dataset 8 document TPSO material prices/API. They should be cross-checked against Dataset 2 before combining; overlapping records must not be counted twice. Dataset 3 is a national index; Dataset 4 is a standard construction cost publication; Dataset 7 is a BOQ product, not a price dataset. These are outside the MVP price fact table.

## Eight-step sequence implemented in `boq_platform/cleansing.py` and `ingest.py`

1. **Preserve raw:** save the official response in `data_raw/`; preserve source row fields in `price_observations.raw_fields`.
2. **Normalize labels and codes:** normalize Unicode/whitespace for matching, preserve source names and product codes.
3. **Normalize units conservatively:** map known exact synonyms; do not convert package sizes without documented quantities.
4. **Parse price fields:** use decimal arithmetic, separate sale/list price, VAT and delivery fee; reject missing, invalid or nonpositive current prices.
5. **Normalize time and location:** parse observation date, month and province; convert Buddhist years to Gregorian while retaining raw fields.
6. **Deduplicate idempotently:** build a stable SHA-256 source-row key so the same snapshot can be re-imported without duplicating it.
7. **Flag quality issues:** record missing data and extreme prices for review; do not delete outliers automatically.
8. **Retain lineage and decisions:** store quality status, source URL, raw payload and append import/match events to JSONL audit files.

Retail records without a capture date, valid unit or positive price are rejected. A retail observation is eligible for a project comparison only when its material mapping, unit, project region and freshness meet the comparison query's conditions.

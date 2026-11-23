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
6. **Deduplicate idempotently:** build a SHA-256 identity key from source + product code (or name when there is no code) + date + province + branch + unit. Price is *not* part of the key: re-importing the same row is counted as unchanged, and a corrected price for the same product/area/month updates the existing row (`quality_note` keeps `revised_from:<old price>` and `logs/audit.jsonl` gets a `price_revised` event) instead of creating a second row for the same month.
7. **Flag quality issues:** record missing data and extreme prices for review; do not delete outliers automatically.
8. **Retain lineage and decisions:** store quality status, source URL, raw payload and append import/match events to JSONL audit files.

Dataset 2 API field names are mapped through `MOC_FIELD_ALIASES` in `boq_platform/ingest.py`. They have not yet been verified against a live API response: if every row of an import is rejected, the error lists the field names actually received so the mapping can be corrected. A saved response can be re-imported with `import_moc_file()` without calling the API again.

Retail records without a capture date, valid unit or positive price are rejected. A retail observation is eligible for a project comparison only when its material mapping, unit, project region and freshness meet the comparison query's conditions.

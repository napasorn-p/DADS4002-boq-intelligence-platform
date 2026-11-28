"""Import a TPSO monthly price file into master_product and tpso_price.

Usage:
    python import_data.py data_raw/<file>.json [more files ...]

The file is the TPSO monthly price JSON (index-api.tpso.go.th, CmiPrice/Month layout):
a list of rows, or {"data": [...]}, each with commodityCode, commodityNameTH, unitName,
curYear (Buddhist year), curMonth, priceCur, type (area code, 10 = ส่วนกลาง), typeName.

Each valid row becomes one master_product row (source = 'TPSO') and one tpso_price row
with the same id. Rows already imported (same commodityCode, curYear, curMonth, type)
are skipped, so running the same file twice is safe. Rows without a usable price,
month or year are not imported and are counted as rejected.
"""

import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from db import get_connection

# Fixed values written to master_product for every TPSO row. TPSO prices are
# cash prices excluding VAT and delivery (see README, Data scope).
TPSO_STORE_NAME = "TPSO"
TPSO_AVAILABILITY = "available"
TPSO_PRICE_BASIS = "cash_ex_vat_ex_delivery"


def read_rows(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if isinstance(payload, dict):
        for key in ("data", "result", "results", "items", "rows"):
            if isinstance(payload.get(key), list):
                return payload[key]
    if isinstance(payload, list):
        return payload
    raise ValueError(f"{path}: no list of price rows found")


def clean_row(raw):
    """Return a cleaned dict, or None when the row cannot be imported."""
    try:
        code = str(raw["commodityCode"]).strip()
        name = str(raw["commodityNameTH"]).strip()
        unit = str(raw["unitName"]).strip()
        year_be = int(raw["curYear"])
        month = int(raw["curMonth"])
        price = Decimal(str(raw["priceCur"]))
        area = int(raw["type"])
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return None
    if not code or not name or not unit or not 1 <= month <= 12 or price < 0:
        return None
    year_ce = year_be - 543 if year_be > 2400 else year_be
    return {
        "code": code,
        "name": name,
        "unit": unit,
        "year_be": year_be,
        "month": month,
        "price": price,
        "area": area,
        "area_name": str(raw.get("typeName") or "").strip(),
        "period": f"{year_ce:04d}-{month:02d}",
    }


def import_file(conn, path):
    cursor = conn.cursor()
    cursor.execute("SELECT commodityCode, curYear, curMonth, type FROM tpso_price")
    existing = {tuple(r) for r in cursor.fetchall()}
    cursor.execute("SELECT COALESCE(MAX(id), 0) FROM master_product FOR UPDATE")
    next_id = cursor.fetchone()[0] + 1

    master_rows, tpso_rows = [], []
    rejected = skipped = 0
    today, now = date.today(), datetime.now()
    for raw in read_rows(path):
        row = clean_row(raw)
        if row is None:
            rejected += 1
            continue
        key = (row["code"], row["year_be"], row["month"], row["area"])
        if key in existing:
            skipped += 1
            continue
        existing.add(key)
        master_rows.append((next_id, "TPSO", TPSO_STORE_NAME, row["code"], row["name"],
                            row["unit"], row["price"], TPSO_AVAILABILITY, TPSO_PRICE_BASIS,
                            row["period"], today))
        tpso_rows.append((next_id, row["area"], row["area_name"], row["code"], row["name"],
                          row["unit"], row["month"], row["year_be"], row["price"], now))
        next_id += 1

    cursor.executemany(
        "INSERT INTO master_product (id, source, store_name, commodity_code, product_name,"
        " unit, price, availability, price_basis, price_period, retrieved_date)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", master_rows)
    cursor.executemany(
        "INSERT INTO tpso_price (id, type, typeName, commodityCode, commodityNameTH,"
        " unitName, curMonth, curYear, priceCur, createdAt)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", tpso_rows)
    cursor.close()
    return len(master_rows), skipped, rejected


def main(paths):
    if not paths:
        print(__doc__)
        return 1
    conn = get_connection()
    try:
        for path in paths:
            try:
                inserted, skipped, rejected = import_file(conn, path)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            print(f"{path}: inserted {inserted}, already in database {skipped}, rejected {rejected}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

"""Import a TPSO monthly price file into master_product and tpso_price.

Usage:
    python import_data.py data_raw/<file>.json [more files ...]

The file is the TPSO monthly price JSON (index-api.tpso.go.th, CmiPrice/Month layout):
a list of rows, or {"data": [...]}, each with commodityCode, commodityNameTH, unitName,
curYear (Buddhist year), curMonth, priceCur, type (area code, 10 = ส่วนกลาง), typeName.

Each valid row becomes one tpso_price row (a copy of the file's fields) and one
master_product row with the same id, filled the same way as the team's existing data:
  id              = the TPSO record id from the file
  store_name      = "สนค. (<typeName>)", e.g. "สนค. (ส่วนกลาง)"
  availability    = "available", price_basis = "tpso_reference"
  price_period    = "<curYear>-<MM>" in the Buddhist year, e.g. "2569-10"
  retrieved_date  = the date part of createdAt
Rows whose id is already in the database are skipped, so running the same file twice
is safe. Rows without a usable id, price, month or year are rejected and counted.
"""

import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from db import get_connection

# Fixed values written to master_product for every TPSO row (same as existing data).
TPSO_AVAILABILITY = "available"
TPSO_PRICE_BASIS = "tpso_reference"


def read_rows(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if isinstance(payload, dict):
        for key in ("data", "result", "results", "items", "rows"):
            if isinstance(payload.get(key), list):
                return payload[key]
    if isinstance(payload, list):
        return payload
    raise ValueError(f"{path}: no list of price rows found")


def parse_created_at(value):
    """TPSO createdAt, e.g. "2026-11-02T01:55:53.996295" (a trailing Z is allowed)."""
    text = str(value).strip().replace("Z", "").replace(" ", "T")
    if "." in text:  # MySQL DATETIME(6) keeps at most 6 fraction digits
        head, frac = text.split(".", 1)
        text = f"{head}.{frac[:6]}"
    return datetime.fromisoformat(text)


def clean_row(raw):
    """Return a cleaned dict, or None when the row cannot be imported."""
    try:
        row_id = int(raw["id"])
        code = str(raw["commodityCode"]).strip()
        name = str(raw["commodityNameTH"]).strip()
        unit = str(raw["unitName"]).strip()
        year = int(raw["curYear"])
        month = int(raw["curMonth"])
        price = Decimal(str(raw["priceCur"]))
        area = int(raw["type"])
        area_name = str(raw["typeName"]).strip()
        created_at = parse_created_at(raw["createdAt"])
        price_vat = raw.get("priceVAT")
        price_vat = None if price_vat in (None, "") else Decimal(str(price_vat))
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return None
    if not code or not name or not unit or not area_name or not 1 <= month <= 12 or price < 0:
        return None
    return {
        "id": row_id, "code": code, "name": name, "unit": unit, "year": year,
        "month": month, "price": price, "price_vat": price_vat, "area": area,
        "area_name": area_name, "created_at": created_at,
        "store_name": f"สนค. ({area_name})",
        "period": f"{year:04d}-{month:02d}",
    }


def import_file(conn, path):
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM master_product")
    existing = {r[0] for r in cursor.fetchall()}

    master_rows, tpso_rows = [], []
    rejected = skipped = 0
    for raw in read_rows(path):
        row = clean_row(raw)
        if row is None:
            rejected += 1
            continue
        if row["id"] in existing:
            skipped += 1
            continue
        existing.add(row["id"])
        master_rows.append((row["id"], "TPSO", row["store_name"], row["code"], row["name"],
                            row["unit"], row["price"], TPSO_AVAILABILITY, TPSO_PRICE_BASIS,
                            row["period"], row["created_at"].date()))
        tpso_rows.append((row["id"], row["area"], row["area_name"], row["code"], row["name"],
                          row["unit"], row["month"], row["year"], row["price"],
                          row["price_vat"], row["created_at"]))

    cursor.executemany(
        "INSERT INTO master_product (id, source, store_name, commodity_code, product_name,"
        " unit, price, availability, price_basis, price_period, retrieved_date)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", master_rows)
    cursor.executemany(
        "INSERT INTO tpso_price (id, type, typeName, commodityCode, commodityNameTH,"
        " unitName, curMonth, curYear, priceCur, priceVAT, createdAt)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", tpso_rows)
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

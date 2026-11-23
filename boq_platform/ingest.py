"""Official API, retailer snapshot and BOQ workbook ingestion."""
from datetime import datetime
from pathlib import Path
import csv
import json
import shutil
import uuid

import requests
from openpyxl import load_workbook

from .audit import append_event
from .cleansing import clean_price_record, normalize_text, normalize_unit, parse_decimal
from .config import MOC_API_BASE
from .db import connection


SOURCE_URLS = {
    "Thai Watsadu": "https://www.thaiwatsadu.com/",
    "HomePro": "https://www.homepro.co.th/",
    "DoHome": "https://www.dohome.co.th/",
    "Global House": "https://globalhouse.co.th/",
    "Hiachet": "https://www.hiachet.com/",
}


def get_source(cursor, source_name):
    cursor.execute("SELECT source_id, source_kind FROM price_sources WHERE source_name=%s AND is_active=1", (source_name,))
    row = cursor.fetchone()
    if not row:
        raise ValueError(f"ไม่พบแหล่งข้อมูล {source_name}; ให้รัน schema.sql ก่อน")
    return row


def ensure_official_material(cursor, code, name, unit):
    if code:
        cursor.execute("""INSERT INTO materials (material_code, canonical_name, standard_unit)
            VALUES (%s,%s,%s) ON DUPLICATE KEY UPDATE canonical_name=VALUES(canonical_name), standard_unit=VALUES(standard_unit)""",
                       (str(code), name, unit))
        cursor.execute("SELECT material_id FROM materials WHERE material_code=%s", (str(code),))
        material_id = cursor.fetchone()[0]
    else:
        cursor.execute("SELECT material_id FROM materials WHERE canonical_name=%s AND standard_unit=%s LIMIT 1", (name, unit))
        found = cursor.fetchone()
        if found:
            material_id = found[0]
        else:
            cursor.execute("INSERT INTO materials (canonical_name, standard_unit) VALUES (%s,%s)", (name, unit))
            material_id = cursor.lastrowid
    normalized = normalize_text(name)
    cursor.execute("""SELECT alias_id FROM material_aliases WHERE material_id=%s AND alias_normalized=%s LIMIT 1""",
                   (material_id, normalized))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO material_aliases (material_id, alias_text, alias_normalized, source_product_code) VALUES (%s,%s,%s,%s)",
                       (material_id, name, normalized, str(code) if code else None))
    return material_id


_OBS_COLUMNS = ("source_id", "material_id", "source_record_hash", "source_product_code",
                "product_name", "brand", "specification", "province_code", "province_name",
                "branch_name", "observation_date", "period_year", "period_month", "unit", "price",
                "regular_price", "vat_included", "shipping_fee", "stock_status", "promotion_label",
                "product_url", "quality_status", "quality_note", "raw_fields")


def _insert_observation(cursor, record, material_id=None):
    """Insert one observation, or update it when the same identity is re-imported.

    Returns (observation_id, change): "inserted", "revised" (same product, area and
    date but a new price) or "unchanged". A human quality decision on an existing
    row is kept unless the price itself changed.
    """
    record = {**record, "material_id": material_id}
    cursor.execute("""SELECT observation_id, price FROM price_observations
        WHERE source_id=%s AND source_record_hash=%s""",
        (record["source_id"], record["source_record_hash"]))
    existing = cursor.fetchone()
    if existing is None:
        columns = ",".join(_OBS_COLUMNS)
        values = ",".join(f"%({name})s" for name in _OBS_COLUMNS)
        cursor.execute(f"INSERT INTO price_observations ({columns}) VALUES ({values})", record)
        return cursor.lastrowid, "inserted"
    observation_id, old_price = existing
    if old_price == record["price"]:
        cursor.execute("""UPDATE price_observations
            SET material_id=COALESCE(material_id,%s), raw_fields=%s, retrieved_at=CURRENT_TIMESTAMP
            WHERE observation_id=%s""", (material_id, record["raw_fields"], observation_id))
        return observation_id, "unchanged"
    note = ",".join(filter(None, [record.get("quality_note"), f"revised_from:{old_price}"]))
    cursor.execute("""UPDATE price_observations
        SET price=%s, regular_price=%s, vat_included=%s, shipping_fee=%s, stock_status=%s,
            promotion_label=%s, material_id=COALESCE(material_id,%s), quality_status=%s,
            quality_note=%s, raw_fields=%s, retrieved_at=CURRENT_TIMESTAMP
        WHERE observation_id=%s""",
        (record["price"], record["regular_price"], record["vat_included"], record["shipping_fee"],
         record["stock_status"], record["promotion_label"], material_id, record["quality_status"],
         note, record["raw_fields"], observation_id))
    return observation_id, "revised"


def _flag_historical_outlier(cursor, record, material_id):
    """Use the same source/material/unit/region history; flag IQR outliers for review."""
    if material_id is None or record.get("price") is None:
        return False
    cursor.execute("""SELECT price FROM price_observations
        WHERE source_id=%s AND material_id=%s AND unit=%s
          AND province_code <=> %s AND quality_status='valid'
        ORDER BY observation_date DESC LIMIT 60""",
        (record["source_id"], material_id, record["unit"], record["province_code"]))
    history = sorted(float(row[0]) for row in cursor.fetchall())
    if len(history) < 5:
        return False
    mid = len(history) // 2
    lower = history[:mid]
    upper = history[mid:] if len(history) % 2 == 0 else history[mid + 1:]
    q1 = lower[len(lower) // 2]
    q3 = upper[len(upper) // 2]
    iqr = q3 - q1
    value = float(record["price"])
    if iqr == 0:
        median = history[len(history) // 2]
        outlier = median > 0 and (value > median * 1.5 or value < median / 1.5)
    else:
        low, high = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        outlier = value < low or value > high
    if outlier:
        record["quality_status"] = "review"
        old_note = record.get("quality_note") or ""
        record["quality_note"] = ",".join(filter(None, [old_note, "historical_iqr_outlier"]))
        return True
    return False


# The MOC API field names have not been verified against a live response yet.
# Each canonical field accepts several spellings; check data_raw/moc_*.json after
# the first run and add the real key here if the import reports unknown fields.
MOC_FIELD_ALIASES = {
    "com_code": ("com_code", "comcode", "commodity_code", "product_code", "code"),
    "com_name_th": ("com_name_th", "com_name", "comnameth", "commodity_name", "product_name", "name_th", "name"),
    "unit": ("unit", "unit_name", "unitname", "unit_th", "com_unit"),
    "province_code": ("province_code", "provincecode", "prov_code", "province_id"),
    "province_name": ("province_name", "province_name_th", "provincename", "province"),
    "year": ("year", "price_year", "cur_year", "curyear", "yr"),
    "month": ("month", "price_month", "cur_month", "curmonth", "mn"),
    "price": ("price", "avg_price", "price_avg", "price_value", "pricecur", "value"),
}


def _pick(raw, names):
    lowered = {str(key).lower(): value for key, value in raw.items()}
    for name in names:
        if name in lowered and lowered[name] not in (None, ""):
            return lowered[name]
    return None


def _moc_rows(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "result", "results", "items", "records", "rows"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict):  # e.g. {"result": {"data": [...]}}
                nested = _moc_rows(value)
                if nested:
                    return nested
    return None


def import_moc_prices(province_code, from_year, to_year, com_code="0000000000000000"):
    """Download Dataset 2 via MOC API and store observed material prices."""
    params = {"province_code": str(province_code), "com_code": str(com_code),
              "from_year": int(from_year), "to_year": int(to_year)}
    response = requests.get(MOC_API_BASE, params=params, timeout=(10, 60))
    response.raise_for_status()
    payload = response.json()
    run_id = uuid.uuid4().hex[:12]
    raw_dir = Path(__file__).resolve().parents[1] / "data_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"moc_{province_code}_{from_year}_{to_year}_{run_id}.json"
    raw_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = _moc_rows(payload)
    if rows is None:
        raise ValueError(f"รูปแบบ API ไม่ใช่รายการข้อมูลที่คาดไว้; ดู response ดิบที่ {raw_path.name}")
    return import_moc_rows(rows, province_code, run_id=run_id, raw_name=raw_path.name,
                           from_year=from_year, to_year=to_year)


def import_moc_file(json_path, province_code):
    """Re-import a saved Dataset 2 response (data_raw/moc_*.json) without calling the API."""
    json_path = Path(json_path)
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    rows = _moc_rows(payload)
    if rows is None:
        raise ValueError("ไฟล์ไม่มีรายการข้อมูลในรูปแบบที่รองรับ")
    return import_moc_rows(rows, province_code, run_id=uuid.uuid4().hex[:12], raw_name=json_path.name)


def import_moc_rows(rows, province_code, *, run_id, raw_name, from_year=None, to_year=None):
    from .matching import log_match_event
    counts = {"inserted": 0, "revised": 0, "unchanged": 0}
    rejected = 0
    with connection() as conn:
        cursor = conn.cursor()
        try:
            source_id, _ = get_source(cursor, "MOC Open Data CSI")
            for raw in rows:
                normalized = {field: _pick(raw, names) for field, names in MOC_FIELD_ALIASES.items()}
                normalized["province_code"] = normalized["province_code"] or province_code
                record, issues = clean_price_record(normalized, source_id, official=True)
                if issues:
                    rejected += 1
                    append_event("price_row_rejected", run_id=run_id, source="MOC Open Data CSI",
                                 reason=issues, source_product_code=record["source_product_code"])
                    continue
                material_id = ensure_official_material(cursor, record["source_product_code"],
                                                       record["product_name"], record["unit"])
                if _flag_historical_outlier(cursor, record, material_id):
                    append_event("price_quality_review", run_id=run_id, source="MOC Open Data CSI",
                                 product_code=record["source_product_code"], reason=record["quality_note"])
                observation_id, change = _insert_observation(cursor, record, material_id)
                counts[change] += 1
                if change == "revised":
                    append_event("price_revised", run_id=run_id, source="MOC Open Data CSI",
                                 observation_id=observation_id, product_code=record["source_product_code"],
                                 period=f"{record['period_year']}-{record['period_month']:02d}",
                                 new_price=record["price"])
                if change == "inserted":
                    # Matching evidence for the official-code-to-canonical-material mapping.
                    log_match_event(cursor, input_name=record["product_name"], input_specification=None,
                                    input_unit=record["unit"], candidate_material_id=material_id,
                                    candidate_name=record["product_name"], match_method="official_code",
                                    confidence=1.0, status="AUTO_MATCHED",
                                    evidence={"com_code": record["source_product_code"],
                                              "observation_id": observation_id, "source": "MOC Open Data CSI"},
                                    observation_id=observation_id)
        finally:
            cursor.close()
    if rows and rejected == len(rows):
        keys = sorted(rows[0].keys()) if isinstance(rows[0], dict) else type(rows[0]).__name__
        append_event("moc_import_failed", run_id=run_id, raw_file=raw_name, rows_read=len(rows),
                     reason="all_rows_rejected", sample_keys=keys)
        raise ValueError(f"ทุกแถวถูกปฏิเสธ — ชื่อฟิลด์จาก API อาจไม่ตรงกับที่โค้ดรู้จัก "
                         f"(ฟิลด์ที่พบ: {keys}); เพิ่มชื่อใน MOC_FIELD_ALIASES ใน ingest.py")
    saved = counts["inserted"] + counts["revised"]
    append_event("moc_import", run_id=run_id, source="MOC Open Data CSI", raw_file=raw_name,
                 province_code=str(province_code), from_year=from_year, to_year=to_year,
                 rows_read=len(rows), rows_inserted=counts["inserted"], rows_revised=counts["revised"],
                 rows_unchanged=counts["unchanged"], rows_rejected=rejected)
    return {"run_id": run_id, "rows_read": len(rows), "rows_saved": saved,
            "rows_inserted": counts["inserted"], "rows_revised": counts["revised"],
            "rows_unchanged": counts["unchanged"],
            "rows_rejected": rejected, "raw_file": Path(raw_name)}


def _resolve_material(cursor, source_id, source_product_code, moc_code, product_name, unit):
    """Exact-only resolution, in the agreed order; anything else stays unmatched.

    1. store SKU already confirmed for this store (material_aliases.source_product_code)
    2. MOC commodity code typed in the CSV (moc_com_code) with the same unit
    3. exact canonical name + unit, 4. exact confirmed alias + unit
    Retail product names rarely equal MOC names, so fill moc_com_code or confirm
    unmatched rows once in menu 10; the SKU is then remembered for later imports.
    """
    unit = normalize_unit(unit)
    if source_product_code:
        cursor.execute("""SELECT m.material_id, m.standard_unit FROM material_aliases a
            JOIN materials m ON m.material_id=a.material_id
            WHERE a.source_id=%s AND a.source_product_code=%s""", (source_id, source_product_code))
        rows = [row for row in cursor.fetchall() if normalize_unit(row[1]) == unit]
        if len({row[0] for row in rows}) == 1:
            return rows[0][0], "store_sku_alias"
    if moc_code:
        cursor.execute("SELECT material_id,standard_unit FROM materials WHERE material_code=%s", (str(moc_code).strip(),))
        row = cursor.fetchone()
        if row and normalize_unit(row[1]) == unit:
            return row[0], "official_code"
    cursor.execute("""SELECT material_id FROM materials WHERE LOWER(canonical_name)=LOWER(%s)
        AND standard_unit=%s LIMIT 1""", (product_name.strip(), unit))
    row = cursor.fetchone()
    if row:
        return row[0], "exact_name_unit"
    cursor.execute("""SELECT m.material_id FROM material_aliases a JOIN materials m ON m.material_id=a.material_id
        WHERE a.alias_normalized=%s AND m.standard_unit=%s LIMIT 1""", (normalize_text(product_name), unit))
    row = cursor.fetchone()
    return (row[0], "exact_alias_unit") if row else (None, "unmatched")


def remember_store_sku(cursor, material_id, source_id, product_name, source_product_code):
    """Store a confirmed store SKU so the next snapshot from that store auto-matches."""
    if not (material_id and source_product_code):
        return
    cursor.execute("""SELECT alias_id FROM material_aliases
        WHERE material_id=%s AND source_id=%s AND source_product_code=%s LIMIT 1""",
        (material_id, source_id, source_product_code))
    if not cursor.fetchone():
        cursor.execute("""INSERT INTO material_aliases
            (material_id,source_id,alias_text,alias_normalized,source_product_code)
            VALUES (%s,%s,%s,%s,%s)""",
            (material_id, source_id, product_name, normalize_text(product_name), source_product_code))


def import_retail_csv(csv_path):
    """Import a captured retailer price snapshot; no website scraping is performed."""
    from .matching import log_match_event
    csv_path = Path(csv_path)
    run_id = uuid.uuid4().hex[:12]
    raw_dir = Path(__file__).resolve().parents[1] / "data_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_copy = raw_dir / f"retail_{run_id}_{csv_path.name}"
    shutil.copy2(csv_path, raw_copy)
    rows_saved = rows_revised = rows_unchanged = rows_rejected = rows_unmatched = 0
    with csv_path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    with connection() as conn:
        cursor = conn.cursor()
        try:
            for row_no, raw in enumerate(rows, start=2):
                source_name = (raw.get("source_name") or "").strip()
                # A savepoint per row: a failing row is undone completely, others are kept.
                cursor.execute("SAVEPOINT retail_row")
                try:
                    source_id, source_kind = get_source(cursor, source_name)
                    if source_kind != "retailer":
                        raise ValueError("source_kind_not_retailer")
                    record, issues = clean_price_record(raw, source_id, official=False)
                    if issues:
                        rows_rejected += 1
                        append_event("retail_row_rejected", run_id=run_id, file=csv_path.name,
                                     row_no=row_no, source=source_name, reason=issues)
                        continue
                    material_id, method = _resolve_material(
                        cursor, source_id, record["source_product_code"], raw.get("moc_com_code"),
                        record["product_name"], record["unit"])
                    remember_store_sku(cursor, material_id, source_id, record["product_name"],
                                       record["source_product_code"])
                    if _flag_historical_outlier(cursor, record, material_id):
                        append_event("price_quality_review", run_id=run_id, source=source_name,
                                     product_code=record["source_product_code"], reason=record["quality_note"])
                    observation_id, change = _insert_observation(cursor, record, material_id)
                    if change == "unchanged":
                        rows_unchanged += 1
                        continue
                    if change == "revised":
                        rows_revised += 1
                        append_event("price_revised", run_id=run_id, source=source_name,
                                     observation_id=observation_id, row_no=row_no, new_price=record["price"])
                        continue
                    rows_saved += 1
                    if material_id is None:
                        rows_unmatched += 1
                    log_match_event(cursor, input_name=record["product_name"],
                                    input_specification=record["specification"], input_unit=record["unit"],
                                    candidate_material_id=material_id,
                                    candidate_name=record["product_name"] if material_id else None,
                                    match_method=method if material_id else "no_exact_candidate",
                                    confidence=1.0 if material_id else None,
                                    status="AUTO_MATCHED" if material_id else "UNMATCHED",
                                    evidence={"source": source_name, "observation_id": observation_id,
                                              "moc_com_code": raw.get("moc_com_code"),
                                              "store_sku": record["source_product_code"], "row_no": row_no},
                                    observation_id=observation_id)
                except Exception as exc:
                    cursor.execute("ROLLBACK TO SAVEPOINT retail_row")
                    rows_rejected += 1
                    append_event("retail_row_rejected", run_id=run_id, file=csv_path.name,
                                 row_no=row_no, error=str(exc)[:300])
        finally:
            cursor.close()
    append_event("retail_import", run_id=run_id, file=csv_path.name, raw_copy=raw_copy.name,
                 rows_read=len(rows), rows_saved=rows_saved, rows_revised=rows_revised,
                 rows_unchanged=rows_unchanged, rows_rejected=rows_rejected, rows_unmatched=rows_unmatched)
    return {"run_id": run_id, "rows_read": len(rows), "rows_saved": rows_saved,
            "rows_revised": rows_revised, "rows_unchanged": rows_unchanged,
            "rows_rejected": rows_rejected, "rows_unmatched": rows_unmatched}


BOQ_HEADER_ALIASES = {
    "item_name": {"item_name", "material", "material_name", "description", "รายการ", "ชื่อวัสดุ", "ชื่อรายการ"},
    "specification": {"specification", "spec", "size", "สเปก", "รายละเอียด", "ขนาด"},
    "quantity": {"quantity", "qty", "จำนวน", "ปริมาณ"},
    "unit": {"unit", "หน่วย"},
    "budget_unit_price": {"budget_unit_price", "unit_price", "price", "ราคาต่อหน่วย", "ราคา/หน่วย"},
    "room_name": {"room_name", "room", "area", "ห้อง", "พื้นที่"},
    "material_code": {"material_code", "com_code", "รหัสวัสดุ", "รหัสสินค้า"},
    "source_product_code": {"source_product_code", "sku", "รหัสร้าน"},
}


def _read_table(path):
    """Return (header list, iterator of row tuples) for .xlsx or .csv files."""
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.reader(stream))
        return (rows[0] if rows else []), rows[1:]
    if path.suffix.lower() not in {".xlsx", ".xlsm"}:
        raise ValueError("รองรับไฟล์ BOQ เฉพาะ .xlsx หรือ .csv (ไฟล์ .xls รุ่นเก่าให้ Save As เป็น .xlsx ก่อน)")
    workbook = load_workbook(path, data_only=True, read_only=True)
    try:
        rows = [tuple(row) for row in workbook.active.iter_rows(values_only=True)]
    finally:
        workbook.close()
    return (list(rows[0]) if rows else []), rows[1:]


def read_boq_excel(file_path):
    """Read a BOQ .xlsx or .csv file and map common Thai/English headers to MVP columns."""
    header, body = _read_table(Path(file_path))
    raw_headers = [str(value or "").strip().lower() for value in header]
    mapping = {}
    for idx, name in enumerate(raw_headers):
        for field, choices in BOQ_HEADER_ALIASES.items():
            if name in choices and field not in mapping:
                mapping[field] = idx
    if not {"item_name", "quantity", "unit"} <= mapping.keys():
        raise ValueError("ไฟล์ BOQ ต้องมีคอลัมน์ ชื่อวัสดุ/รายการ, จำนวน และหน่วย")
    results = []
    for row_no, row in enumerate(body, start=2):
        if not any(value not in (None, "") for value in row):
            continue
        item = {field: (row[idx] if idx < len(row) else None) for field, idx in mapping.items()}
        item = {key: (None if value == "" else value) for key, value in item.items()}
        item["source_row_no"] = row_no
        results.append(item)
    return results

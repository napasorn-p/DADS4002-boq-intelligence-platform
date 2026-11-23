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


def _insert_observation(cursor, record, material_id=None):
    cursor.execute("""INSERT INTO price_observations
        (source_id, material_id, source_record_hash, source_product_code, product_name, brand,
         specification, province_code, province_name, branch_name, observation_date,
         period_year, period_month, unit, price, regular_price, vat_included, shipping_fee,
         stock_status, promotion_label, product_url, quality_status, quality_note, raw_fields)
        VALUES (%(source_id)s,%(material_id)s,%(source_record_hash)s,%(source_product_code)s,
         %(product_name)s,%(brand)s,%(specification)s,%(province_code)s,%(province_name)s,
         %(branch_name)s,%(observation_date)s,%(period_year)s,%(period_month)s,%(unit)s,
         %(price)s,%(regular_price)s,%(vat_included)s,%(shipping_fee)s,%(stock_status)s,
         %(promotion_label)s,%(product_url)s,%(quality_status)s,%(quality_note)s,%(raw_fields)s)
        ON DUPLICATE KEY UPDATE observation_id=LAST_INSERT_ID(observation_id)""", {**record, "material_id": material_id})
    return cursor.lastrowid


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


def import_moc_prices(province_code, from_year, to_year, com_code="0000000000000000"):
    """Download Dataset 2 via MOC API and store observed material prices."""
    params = {"province_code": str(province_code), "com_code": str(com_code),
              "from_year": int(from_year), "to_year": int(to_year)}
    response = requests.get(MOC_API_BASE, params=params, timeout=(10, 60))
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict):
        rows = payload.get("data") or payload.get("result") or payload.get("items") or []
    else:
        rows = payload
    if not isinstance(rows, list):
        raise ValueError("รูปแบบ API ไม่ใช่รายการข้อมูลที่คาดไว้; เก็บ response ดิบไว้ตรวจสอบ")
    run_id = uuid.uuid4().hex[:12]
    inserted = rejected = 0
    raw_dir = Path(__file__).resolve().parents[1] / "data_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"moc_{province_code}_{from_year}_{to_year}_{run_id}.json"
    raw_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    with connection() as conn:
        cursor = conn.cursor()
        try:
            source_id, _ = get_source(cursor, "MOC Open Data CSI")
            for raw in rows:
                normalized = {"com_code": raw.get("com_code"), "com_name_th": raw.get("com_name_th"),
                              "unit": raw.get("unit"), "province_code": raw.get("province_code", province_code),
                              "province_name": raw.get("province_name"), "year": raw.get("year"),
                              "month": raw.get("month"), "price": raw.get("price")}
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
                observation_id = _insert_observation(cursor, record, material_id)
                inserted += 1
                # Keep a matching audit trail for official-code-to-canonical-material mapping.
                from .matching import log_match_event
                log_match_event(cursor, input_name=record["product_name"], input_specification=None,
                                input_unit=record["unit"], candidate_material_id=material_id,
                                candidate_name=record["product_name"], match_method="official_code",
                                confidence=1.0, status="AUTO_MATCHED", evidence={"com_code": record["source_product_code"],
                                "observation_id": observation_id, "source": "MOC Open Data CSI"}, observation_id=observation_id)
        finally:
            cursor.close()
    append_event("moc_import", run_id=run_id, source="MOC Open Data CSI", raw_file=str(raw_path.name),
                 province_code=str(province_code), from_year=from_year, to_year=to_year,
                 rows_read=len(rows), rows_saved=inserted, rows_rejected=rejected)
    return {"run_id": run_id, "rows_read": len(rows), "rows_saved": inserted,
            "rows_rejected": rejected, "raw_file": raw_path}


def _resolve_material(cursor, moc_code, product_name, unit):
    if moc_code:
        cursor.execute("SELECT material_id,standard_unit FROM materials WHERE material_code=%s", (str(moc_code).strip(),))
        row = cursor.fetchone()
        if row and normalize_unit(row[1]) == normalize_unit(unit):
            return row[0], "official_code"
    normalized = normalize_text(product_name)
    cursor.execute("""SELECT m.material_id FROM materials m WHERE LOWER(m.canonical_name)=LOWER(%s)
        AND LOWER(m.standard_unit)=LOWER(%s) LIMIT 1""", (product_name.strip(), unit))
    row = cursor.fetchone()
    if row:
        return row[0], "exact_name_unit"
    cursor.execute("""SELECT m.material_id FROM material_aliases a JOIN materials m ON m.material_id=a.material_id
        WHERE a.alias_normalized=%s AND LOWER(m.standard_unit)=LOWER(%s) LIMIT 1""", (normalized, unit))
    row = cursor.fetchone()
    return (row[0], "exact_alias_unit") if row else (None, "unmatched")


def import_retail_csv(csv_path):
    """Import a captured retailer price snapshot; no website scraping is performed."""
    csv_path = Path(csv_path)
    run_id = uuid.uuid4().hex[:12]
    raw_dir = Path(__file__).resolve().parents[1] / "data_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_copy = raw_dir / f"retail_{run_id}_{csv_path.name}"
    shutil.copy2(csv_path, raw_copy)
    rows_read = rows_saved = rows_rejected = rows_unmatched = 0
    with csv_path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    rows_read = len(rows)
    with connection() as conn:
        cursor = conn.cursor()
        try:
            for row_no, raw in enumerate(rows, start=2):
                source_name = (raw.get("source_name") or "").strip()
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
                    material_id, method = _resolve_material(cursor, raw.get("moc_com_code"),
                                                           record["product_name"], record["unit"])
                    if material_id and record["source_product_code"]:
                        cursor.execute("""SELECT alias_id FROM material_aliases
                            WHERE material_id=%s AND source_id=%s AND source_product_code=%s LIMIT 1""",
                            (material_id, source_id, record["source_product_code"]))
                        if not cursor.fetchone():
                            cursor.execute("""INSERT INTO material_aliases
                                (material_id,source_id,alias_text,alias_normalized,source_product_code)
                                VALUES (%s,%s,%s,%s,%s)""",
                                (material_id, source_id, record["product_name"],
                                 normalize_text(record["product_name"]), record["source_product_code"]))
                    if _flag_historical_outlier(cursor, record, material_id):
                        append_event("price_quality_review", run_id=run_id, source=source_name,
                                     product_code=record["source_product_code"], reason=record["quality_note"])
                    observation_id = _insert_observation(cursor, record, material_id)
                    rows_saved += 1
                    if material_id is None:
                        rows_unmatched += 1
                        from .matching import log_match_event
                        log_match_event(cursor, input_name=record["product_name"],
                                        input_specification=record["specification"], input_unit=record["unit"],
                                        candidate_material_id=None, candidate_name=None,
                                        match_method="no_exact_candidate", confidence=None,
                                        status="UNMATCHED", evidence={"source": source_name,
                                        "observation_id": observation_id, "row_no": row_no},
                                        observation_id=observation_id)
                    else:
                        from .matching import log_match_event
                        log_match_event(cursor, input_name=record["product_name"],
                                        input_specification=record["specification"], input_unit=record["unit"],
                                        candidate_material_id=material_id, candidate_name=record["product_name"],
                                        match_method=method, confidence=1.0, status="AUTO_MATCHED",
                                        evidence={"source": source_name, "observation_id": observation_id,
                                                  "moc_com_code": raw.get("moc_com_code"), "row_no": row_no},
                                        observation_id=observation_id)
                except Exception as exc:
                    rows_rejected += 1
                    append_event("retail_row_rejected", run_id=run_id, file=csv_path.name,
                                 row_no=row_no, error=str(exc)[:300])
        finally:
            cursor.close()
    append_event("retail_import", run_id=run_id, file=csv_path.name, raw_copy=raw_copy.name, rows_read=rows_read,
                 rows_saved=rows_saved, rows_rejected=rows_rejected, rows_unmatched=rows_unmatched)
    return {"run_id": run_id, "rows_read": rows_read, "rows_saved": rows_saved,
            "rows_rejected": rows_rejected, "rows_unmatched": rows_unmatched}


def read_boq_excel(file_path):
    """Read an Excel workbook and map common Thai/English headers to MVP columns."""
    path = Path(file_path)
    workbook = load_workbook(path, data_only=True, read_only=True)
    sheet = workbook.active
    raw_headers = [str(cell.value or "").strip().lower() for cell in next(sheet.iter_rows(min_row=1, max_row=1))]
    aliases = {
        "item_name": {"item_name", "material", "material_name", "description", "รายการ", "ชื่อวัสดุ", "ชื่อรายการ"},
        "specification": {"specification", "spec", "size", "สเปก", "รายละเอียด", "ขนาด"},
        "quantity": {"quantity", "qty", "จำนวน", "ปริมาณ"},
        "unit": {"unit", "หน่วย"},
        "budget_unit_price": {"budget_unit_price", "unit_price", "price", "ราคาต่อหน่วย", "ราคา/หน่วย"},
        "room_name": {"room_name", "room", "area", "ห้อง", "พื้นที่"},
        "material_code": {"material_code", "com_code", "รหัสวัสดุ", "รหัสสินค้า"},
        "source_product_code": {"source_product_code", "sku", "รหัสร้าน"},
    }
    mapping = {}
    for idx, header in enumerate(raw_headers):
        for field, choices in aliases.items():
            if header in choices:
                mapping[field] = idx
    if "item_name" not in mapping or "quantity" not in mapping or "unit" not in mapping:
        workbook.close()
        raise ValueError("Excel ต้องมีคอลัมน์ ชื่อวัสดุ/รายการ, จำนวน และหน่วย")
    results = []
    for row_no, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
        if not any(value is not None for value in row):
            continue
        item = {field: (row[idx] if idx < len(row) else None) for field, idx in mapping.items()}
        item["source_row_no"] = row_no
        results.append(item)
    workbook.close()
    return results

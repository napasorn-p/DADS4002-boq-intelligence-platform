"""Eight-step, traceable cleaning pipeline shared by the notebook and CLI."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
import unicodedata


UNIT_MAP = {
    "หน่วย": "ชิ้น", "unit": "ชิ้น", "each": "ชิ้น", "ea": "ชิ้น",
    "item": "ชิ้น", "piece": "ชิ้น", "pieces": "ชิ้น", "pcs": "ชิ้น",
    "เส้น": "เส้น", "line": "เส้น", "ท่อน": "ท่อน", "เมตร": "เมตร",
    "m": "เมตร", "ม.": "เมตร", "กก.": "กิโลกรัม", "กก": "กิโลกรัม", "kg": "กิโลกรัม",
    "กิโลกรัม": "กิโลกรัม", "ถุง": "ถุง", "กระสอบ": "ถุง", "แผ่น": "แผ่น",
    "กล่อง": "กล่อง", "ชุด": "ชุด", "ลูกบาศก์เมตร": "ลบ.ม.", "คิว": "ลบ.ม.",
    "ลบ.ม.": "ลบ.ม.", "ตัน": "ตัน", "ม้วน": "ม้วน", "อัน": "ชิ้น",
}


def normalize_text(value):
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).strip().lower()
    text = re.sub(r"[\s\u200b\u00a0]+", " ", text)
    text = re.sub(r"\s*([x×/,])\s*", r"\1", text)
    return text


def normalize_unit(value):
    raw = normalize_text(value)
    return UNIT_MAP.get(raw, raw)


def parse_decimal(value):
    if value is None or str(value).strip() == "":
        return None
    cleaned = str(value).strip().replace(",", "").replace("฿", "").replace("บาท", "")
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def parse_bool(value):
    if value is None or str(value).strip() == "":
        return None
    value = normalize_text(value)
    if value in {"true", "yes", "y", "1", "รวม", "รวม vat", "มี vat"}:
        return True
    if value in {"false", "no", "n", "0", "ไม่รวม", "ไม่รวม vat", "ไม่มี vat"}:
        return False
    return None


def parse_date(value, year=None, month=None):
    if value:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        text = str(value).strip()
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m"):
            try:
                parsed = datetime.strptime(text, fmt).date()
                if parsed.year >= 2400:
                    parsed = parsed.replace(year=parsed.year - 543)
                return parsed
            except ValueError:
                pass
    if year and month:
        y = int(year)
        if y >= 2400:
            y -= 543
        return date(y, int(month), 1)
    return None


def source_hash(source_id, record):
    stable = {
        "source_id": source_id,
        "code": record.get("source_product_code"),
        "name": normalize_text(record.get("product_name")),
        "date": str(record.get("observation_date")),
        "province": record.get("province_code"),
        "branch": normalize_text(record.get("branch_name")),
        "unit": normalize_unit(record.get("unit")),
        "price": str(record.get("price")),
        "regular_price": str(record.get("regular_price")),
        "vat_included": record.get("vat_included"),
        "shipping_fee": str(record.get("shipping_fee")),
        "promotion": record.get("promotion_label"),
        "stock_status": record.get("stock_status"),
    }
    payload = json.dumps(stable, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def clean_price_record(raw, source_id, *, official=False):
    """Return (cleaned record, issue list); preserve original fields in JSON."""
    # Step 1: retain raw fields for traceability.
    original = dict(raw)
    # Step 2: normalize source names/codes and product labels.
    product_name = str(raw.get("product_name") or raw.get("com_name_th") or "").strip()
    code = raw.get("source_product_code") or raw.get("com_code") or raw.get("moc_com_code")
    unit = normalize_unit(raw.get("unit") or raw.get("unit_name"))
    # Step 3: normalize units and parse numeric values without inventing values.
    price = parse_decimal(raw.get("price") or raw.get("priceCur"))
    regular = parse_decimal(raw.get("regular_price"))
    shipping = parse_decimal(raw.get("shipping_fee"))
    vat_value = parse_bool(raw.get("vat_included"))
    # Step 4: normalize year/month/date, converting Buddhist years when present.
    obs_date = parse_date(raw.get("observed_at") or raw.get("observation_date"),
                          raw.get("year") or raw.get("curYear"),
                          raw.get("month") or raw.get("curMonth"))
    # Step 5: validate required fields and allowed values.
    issues = []
    if not product_name:
        issues.append("missing_product_name")
    if not unit:
        issues.append("missing_unit")
    if not obs_date:
        issues.append("missing_observation_date")
    if price is None:
        issues.append("invalid_price")
    elif price <= 0:
        issues.append("nonpositive_price")
    if raw.get("regular_price") not in (None, "") and regular is None:
        issues.append("invalid_regular_price")
    if raw.get("shipping_fee") not in (None, "") and shipping is None:
        issues.append("invalid_shipping_fee")
    if raw.get("vat_included") not in (None, "") and vat_value is None:
        issues.append("invalid_vat_flag")
    # Step 6: flag duplicates by a stable hash; DB import uses this as an idempotency key.
    cleaned = {
        "source_id": source_id,
        "material_id": None,
        "source_product_code": str(code).strip() if code else None,
        "product_name": product_name,
        "brand": str(raw.get("brand") or "").strip() or None,
        "specification": str(raw.get("specification") or "").strip() or None,
        "province_code": str(raw.get("province_code") or "").strip() or None,
        "province_name": str(raw.get("province_name") or "").strip() or None,
        "branch_name": str(raw.get("branch_name") or "").strip() or None,
        "observation_date": obs_date,
        "period_year": obs_date.year if official else None,
        "period_month": obs_date.month if official else None,
        "unit": unit,
        "price": price,
        "regular_price": regular,
        "vat_included": vat_value,
        "shipping_fee": shipping,
        "stock_status": str(raw.get("stock_status") or "").strip() or None,
        "promotion_label": str(raw.get("promotion_label") or "").strip() or None,
        "product_url": str(raw.get("product_url") or "").strip() or None,
        "quality_status": "valid" if not issues else "rejected",
        "quality_note": ",".join(issues) or None,
        "raw_fields": json.dumps(original, ensure_ascii=False, default=str),
    }
    # Step 7: historical outliers are flagged in ingest.py using same-source IQR; never auto-delete.
    # Step 8: preserve normalized row, raw row and quality status together.
    cleaned["source_record_hash"] = source_hash(source_id, cleaned)
    return cleaned, issues

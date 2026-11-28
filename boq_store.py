"""BOQ input: create, read, update and delete user batches and lines.

Shared by the GUI (app_gui.py) and any CLI menu. Users may change only
user_input_batch and user_input_line. The price tables (master_product,
tpso_price, material_prices_long) are read here, never written.

A batch is one BOQ input session: typed in by hand (input_method 'manual') or
uploaded from a CSV file ('csv'). Status flow: draft / validated / has_error,
then confirmed. A confirmed batch is locked; set it back to draft to edit it.
"""

import csv
import io
from decimal import Decimal, InvalidOperation
from pathlib import Path

from db import get_connection, query

STATUSES = ("draft", "validated", "has_error", "confirmed")

# CSV columns. Only item_name, unit and quantity are required. Header names are
# matched case-insensitively; the aliases accept the older templates/boq_template.csv.
CSV_COLUMNS = ("item_name", "unit", "quantity", "unit_price", "commodity_code", "note")
CSV_ALIASES = {
    "item_name": ("item_name", "name", "รายการ", "ชื่อวัสดุ"),
    "unit": ("unit", "หน่วย"),
    "quantity": ("quantity", "qty", "จำนวน"),
    "unit_price": ("unit_price", "budget_unit_price", "price", "ราคาต่อหน่วย"),
    "commodity_code": ("commodity_code", "material_code", "รหัสสินค้า"),
    "note": ("note", "specification", "หมายเหตุ"),
}


# ---------- validation ----------

def clean_line(item_name, unit, quantity, unit_price=None, note=None):
    """Check one BOQ line. Returns (values, errors); errors is a list of Thai messages."""
    errors = []
    item_name = (item_name or "").strip()
    unit = (unit or "").strip()
    note = (note or "").strip() or None
    if not item_name:
        errors.append("ต้องมีชื่อรายการ")
    elif len(item_name) > 255:
        errors.append("ชื่อรายการยาวเกิน 255 ตัวอักษร")
    if not unit:
        errors.append("ต้องมีหน่วย")
    elif len(unit) > 30:
        errors.append("หน่วยยาวเกิน 30 ตัวอักษร")
    qty = _to_decimal(quantity)
    if qty is None:
        errors.append("จำนวนต้องเป็นตัวเลข")
    elif qty <= 0:
        errors.append("จำนวนต้องมากกว่า 0")
    price = None
    if unit_price not in (None, ""):
        price = _to_decimal(unit_price)
        if price is None:
            errors.append("ราคาต่อหน่วยต้องเป็นตัวเลข")
        elif price < 0:
            errors.append("ราคาต่อหน่วยติดลบไม่ได้")
    if note and len(note) > 500:
        errors.append("หมายเหตุยาวเกิน 500 ตัวอักษร")
    values = {"item_name": item_name, "unit": unit, "quantity": qty,
              "unit_price": price, "note": note}
    return values, errors


def _to_decimal(value):
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


# ---------- read-only price lookups ----------

def search_products(text, limit=100):
    """Find priced products whose name contains text (TPSO and retail)."""
    return query(
        "SELECT id, source, store_name, product_name, unit, price, price_period"
        " FROM master_product WHERE product_name LIKE %s AND price IS NOT NULL"
        " ORDER BY source DESC, product_name LIMIT %s",
        (f"%{text.strip()}%", int(limit)))


def product_by_code(commodity_code):
    """Latest TPSO price row for a 16-digit commodity code, or None."""
    rows = query(
        "SELECT id, product_name, unit, price FROM master_product"
        " WHERE source = 'TPSO' AND commodity_code = %s"
        " ORDER BY price_period DESC LIMIT 1", (commodity_code.strip(),))
    return rows[0] if rows else None


# ---------- batches ----------

def list_batches():
    return query(
        "SELECT b.batch_id, b.project_name, b.input_method, b.file_name, b.created_by,"
        " b.created_at, b.total_rows, b.error_rows, b.status,"
        " COUNT(l.line_id) AS line_count,"
        " SUM(l.quantity * l.unit_price) AS total_amount"
        " FROM user_input_batch b LEFT JOIN user_input_line l ON l.batch_id = b.batch_id"
        " GROUP BY b.batch_id ORDER BY b.batch_id DESC")


def get_batch(batch_id):
    rows = query("SELECT * FROM user_input_batch WHERE batch_id = %s", (batch_id,))
    if not rows:
        raise ValueError(f"ไม่พบชุดข้อมูลหมายเลข {batch_id}")
    return rows[0]


def create_batch(project_name, created_by, input_method="manual", file_name=None):
    project_name = (project_name or "").strip() or None
    created_by = (created_by or "").strip()
    if not created_by:
        raise ValueError("ต้องระบุชื่อผู้บันทึก")
    if input_method not in ("manual", "csv"):
        raise ValueError("input_method ต้องเป็น manual หรือ csv")
    if input_method == "csv" and not file_name:
        raise ValueError("การนำเข้า CSV ต้องมีชื่อไฟล์")
    return _execute(
        "INSERT INTO user_input_batch (input_method, project_name, file_name, created_by, status)"
        " VALUES (%s, %s, %s, %s, 'draft')",
        (input_method, project_name, file_name, created_by))


def rename_batch(batch_id, project_name):
    _require_editable(batch_id)
    _execute("UPDATE user_input_batch SET project_name = %s WHERE batch_id = %s",
             ((project_name or "").strip() or None, batch_id))


def set_status(batch_id, status):
    if status not in STATUSES:
        raise ValueError(f"สถานะต้องเป็นหนึ่งใน {', '.join(STATUSES)}")
    get_batch(batch_id)
    _execute("UPDATE user_input_batch SET status = %s WHERE batch_id = %s", (status, batch_id))


def delete_batch(batch_id):
    """Delete a batch and all its lines."""
    get_batch(batch_id)
    _execute("DELETE FROM user_input_batch WHERE batch_id = %s", (batch_id,))


# ---------- lines ----------

def list_lines(batch_id):
    """Lines of a batch with the linked product's price (if any) and line totals."""
    return query(
        "SELECT l.line_id, l.line_no, l.item_name, l.unit, l.quantity, l.unit_price, l.note,"
        " l.product_id, p.product_name, p.store_name, p.unit AS product_unit,"
        " p.price AS product_price, p.price_period,"
        " l.quantity * l.unit_price AS line_total,"
        " CASE WHEN p.unit = l.unit THEN l.quantity * p.price END AS product_total"
        " FROM user_input_line l LEFT JOIN master_product p ON p.id = l.product_id"
        " WHERE l.batch_id = %s ORDER BY l.line_no", (batch_id,))


def add_line(batch_id, item_name, unit, quantity, unit_price=None, product_id=None, note=None):
    _require_editable(batch_id)
    values, errors = clean_line(item_name, unit, quantity, unit_price, note)
    if errors:
        raise ValueError("; ".join(errors))
    _check_product(product_id)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        line_id = _insert_line(cursor, batch_id, values, product_id)
        _refresh_counts(cursor, batch_id)
        conn.commit()
        return line_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def update_line(line_id, item_name, unit, quantity, unit_price=None, product_id=None, note=None):
    batch_id = _batch_of_line(line_id)
    _require_editable(batch_id)
    values, errors = clean_line(item_name, unit, quantity, unit_price, note)
    if errors:
        raise ValueError("; ".join(errors))
    _check_product(product_id)
    _execute(
        "UPDATE user_input_line SET item_name = %s, unit = %s, quantity = %s, unit_price = %s,"
        " product_id = %s, note = %s WHERE line_id = %s",
        (values["item_name"], values["unit"], values["quantity"], values["unit_price"],
         product_id, values["note"], line_id))


def delete_line(line_id):
    batch_id = _batch_of_line(line_id)
    _require_editable(batch_id)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM user_input_line WHERE line_id = %s", (line_id,))
        _refresh_counts(cursor, batch_id)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------- CSV ----------

def read_csv(source):
    """Parse a BOQ CSV (path or text). Returns (rows, errors).

    rows: list of dicts ready for add_line (with product_id resolved from commodity_code).
    errors: list of (csv_row_number, message); the header is row 1.
    Accepts UTF-8 (with or without BOM, as Excel saves it) and Thai Windows (cp874) files.
    """
    text = _read_text(source)
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("ไฟล์ว่าง หรือไม่มีแถวหัวตาราง")
    mapping = _map_headers(reader.fieldnames)
    missing = [c for c in ("item_name", "unit", "quantity") if c not in mapping]
    if missing:
        raise ValueError("ไม่พบคอลัมน์ที่ต้องมี: " + ", ".join(missing)
                         + f" (คอลัมน์ในไฟล์: {', '.join(reader.fieldnames)})")
    rows, errors = [], []
    for raw in reader:
        number = reader.line_num  # line in the file, as Excel shows it
        get = lambda col: (raw.get(mapping[col]) or "").strip() if col in mapping else ""
        if not any((value or "").strip() for value in raw.values() if isinstance(value, str)):
            continue  # skip blank lines
        values, problems = clean_line(get("item_name"), get("unit"), get("quantity"),
                                      get("unit_price"), get("note"))
        product_id = None
        code = get("commodity_code")
        if code:
            product = product_by_code(code)
            if product:
                product_id = product["id"]
            else:
                problems.append(f"ไม่พบรหัสสินค้า {code} ในราคา สนค.")
        if problems:
            errors.append((number, "; ".join(problems)))
        else:
            rows.append(dict(values, product_id=product_id))
    return rows, errors


def import_csv(path, created_by, project_name=None):
    """Create a csv batch from a file. Valid rows are saved; invalid rows are reported.

    Returns (batch_id, saved_count, errors). Status is 'validated' when every row was
    valid, otherwise 'has_error' (error_rows = number of rejected rows).
    """
    path = Path(path)
    rows, errors = read_csv(path)
    if not rows and not errors:
        raise ValueError("ไม่มีรายการในไฟล์")
    created_by = (created_by or "").strip()
    if not created_by:
        raise ValueError("ต้องระบุชื่อผู้บันทึก")
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO user_input_batch (input_method, project_name, file_name, created_by,"
            " total_rows, error_rows, status) VALUES ('csv', %s, %s, %s, %s, %s, %s)",
            ((project_name or "").strip() or path.stem, path.name[:255], created_by,
             len(rows) + len(errors), len(errors), "has_error" if errors else "validated"))
        batch_id = cursor.lastrowid
        for values in rows:
            _insert_line(cursor, batch_id, values, values["product_id"])
        conn.commit()
        return batch_id, len(rows), errors
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def write_csv_template(path):
    """Write an empty CSV with the expected header (for users to fill in)."""
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        csv.writer(handle).writerow(CSV_COLUMNS)


# ---------- helpers ----------

def _execute(sql, params):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        conn.commit()
        return cursor.lastrowid or cursor.rowcount
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _insert_line(cursor, batch_id, values, product_id):
    cursor.execute("SELECT COALESCE(MAX(line_no), 0) + 1 FROM user_input_line WHERE batch_id = %s",
                   (batch_id,))
    line_no = cursor.fetchone()[0]
    cursor.execute(
        "INSERT INTO user_input_line (batch_id, line_no, product_id, item_name, unit, quantity,"
        " unit_price, note) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (batch_id, line_no, product_id, values["item_name"], values["unit"],
         values["quantity"], values["unit_price"], values["note"]))
    return cursor.lastrowid


def _refresh_counts(cursor, batch_id):
    """Keep total_rows equal to saved lines + rejected CSV rows."""
    cursor.execute(
        "UPDATE user_input_batch SET total_rows = error_rows +"
        " (SELECT COUNT(*) FROM user_input_line WHERE batch_id = %s) WHERE batch_id = %s",
        (batch_id, batch_id))


def _require_editable(batch_id):
    if get_batch(batch_id)["status"] == "confirmed":
        raise ValueError("ชุดข้อมูลนี้ยืนยันแล้ว แก้ไขไม่ได้ (ยกเลิกการยืนยันก่อน)")


def _batch_of_line(line_id):
    rows = query("SELECT batch_id FROM user_input_line WHERE line_id = %s", (line_id,))
    if not rows:
        raise ValueError(f"ไม่พบรายการหมายเลข {line_id}")
    return rows[0]["batch_id"]


def _check_product(product_id):
    if product_id is not None and not query("SELECT 1 FROM master_product WHERE id = %s",
                                            (product_id,)):
        raise ValueError(f"ไม่พบสินค้าหมายเลข {product_id}")


def _read_text(source):
    is_path = isinstance(source, Path) or (
        isinstance(source, str) and "\n" not in source and Path(source).is_file())
    if is_path:
        data = Path(source).read_bytes()
        for encoding in ("utf-8-sig", "cp874"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise ValueError("อ่านไฟล์ไม่ได้: ต้องเป็น CSV แบบ UTF-8 หรือ Windows Thai")
    return str(source)


def _map_headers(fieldnames):
    lowered = {name.strip().lower(): name for name in fieldnames if name}
    mapping = {}
    for column, aliases in CSV_ALIASES.items():
        for alias in aliases:
            if alias.lower() in lowered:
                mapping[column] = lowered[alias.lower()]
                break
    return mapping

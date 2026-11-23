"""Project, room and BOQ item services used by the CLI and Jupyter notebook."""
from decimal import Decimal

from .audit import append_event
from .cleansing import normalize_unit, parse_decimal
from .db import connection, query
from .matching import find_candidates, log_candidate_set, log_match_event


def create_project(project_name, scope_type, province_code=None, province_name=None, budget_total=None):
    if scope_type not in {"house", "room", "item"}:
        raise ValueError("scope_type ต้องเป็น house, room หรือ item")
    if not project_name or not project_name.strip():
        raise ValueError("กรุณาระบุชื่อโครงการ")
    budget = parse_decimal(budget_total)
    if budget_total not in (None, "") and budget is None:
        raise ValueError("งบประมาณรวมต้องเป็นตัวเลข")
    with connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""INSERT INTO boq_projects
            (project_name,scope_type,province_code,province_name,budget_total)
            VALUES (%s,%s,%s,%s,%s)""",
            (project_name.strip(), scope_type, province_code or None, province_name or None, budget))
        project_id = cursor.lastrowid
    append_event("project_created", project_id=project_id, project_name=project_name,
                 scope_type=scope_type, province_code=province_code)
    return project_id


def add_room(project_id, room_name, floor_label=None):
    with connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""INSERT INTO project_rooms (project_id,room_name,floor_label)
            VALUES (%s,%s,%s) ON DUPLICATE KEY UPDATE room_id=LAST_INSERT_ID(room_id)""",
            (project_id, room_name.strip(), floor_label or None))
        return cursor.lastrowid


def add_boq_item(project_id, *, input_name, quantity, unit, specification=None,
                 budget_unit_price=None, room_id=None, source_product_code=None,
                 source_row_no=None, actor="user"):
    qty = parse_decimal(quantity)
    if not input_name or not str(input_name).strip():
        raise ValueError("กรุณาระบุชื่อวัสดุ")
    if qty is None or qty <= 0:
        raise ValueError("จำนวนต้องเป็นตัวเลขมากกว่า 0")
    normalized_unit = normalize_unit(unit)
    if not normalized_unit:
        raise ValueError("กรุณาระบุหน่วย")
    budget = parse_decimal(budget_unit_price)
    if budget_unit_price not in (None, "") and budget is None:
        raise ValueError("ราคา BOQ ต้องเป็นตัวเลข")
    if budget is not None and budget < 0:
        raise ValueError("ราคา BOQ ต้องไม่ติดลบ")
    with connection() as conn:
        cursor = conn.cursor()
        candidates = find_candidates(cursor, input_name, specification, normalized_unit, source_product_code)
        exact = candidates[0] if candidates and candidates[0]["exact"] else None
        status = "AUTO_MATCHED" if exact else ("NEEDS_REVIEW" if candidates else "UNMATCHED")
        material_id = exact["material_id"] if exact else None
        cursor.execute("""INSERT INTO boq_items
            (project_id,room_id,material_id,source_row_no,source_product_code,input_name,
             input_specification,quantity,input_unit,budget_unit_price,match_status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (project_id, room_id, material_id, source_row_no, source_product_code,
             input_name.strip(), specification or None, qty, normalized_unit, budget, status))
        item_id = cursor.lastrowid
        log_candidate_set(cursor, input_name=input_name, input_specification=specification,
                          input_unit=normalized_unit, candidates=candidates,
                          project_id=project_id, item_id=item_id, actor=actor)
    append_event("boq_item_created", project_id=project_id, item_id=item_id,
                 match_status=status, source_row_no=source_row_no)
    return {"item_id": item_id, "match_status": status,
            "material_id": material_id, "candidates": candidates}


def confirm_boq_match(item_id, material_id, actor="user"):
    with connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT project_id,input_name,input_specification,input_unit FROM boq_items WHERE item_id=%s AND is_deleted=0", (item_id,))
        item = cursor.fetchone()
        if not item:
            raise ValueError(f"ไม่พบ BOQ item {item_id}")
        project_id, input_name, input_spec, input_unit = item
        cursor.execute("SELECT canonical_name,standard_unit,specification FROM materials WHERE material_id=%s AND is_active=1", (material_id,))
        material = cursor.fetchone()
        if not material:
            raise ValueError("ไม่พบวัสดุปลายทาง")
        if normalize_unit(material[1]) != normalize_unit(input_unit):
            raise ValueError("หน่วยวัสดุไม่ตรงกัน จึงยืนยันการจับคู่ไม่ได้")
        if input_spec and material[2] and input_spec.strip().lower() != material[2].strip().lower():
            raise ValueError("สเปกวัสดุไม่ตรงกัน จึงยืนยันการจับคู่ไม่ได้")
        cursor.execute("UPDATE boq_items SET material_id=%s,match_status='USER_CONFIRMED' WHERE item_id=%s", (material_id, item_id))
        log_match_event(cursor, input_name=input_name, input_specification=input_spec,
                        input_unit=input_unit, candidate_material_id=material_id,
                        candidate_name=material[0], match_method="user_confirmation",
                        confidence=1.0, status="USER_CONFIRMED",
                        evidence={"candidate_specification": material[2], "unit_verified": True},
                        project_id=project_id, item_id=item_id, actor=actor)
    append_event("boq_match_confirmed", item_id=item_id, material_id=material_id, actor=actor)


def import_boq_rows(project_id, rows):
    imported = rejected = 0
    rooms = {}
    for row in rows:
        try:
            room_id = None
            room_name = row.get("room_name")
            if room_name:
                room_key = str(room_name).strip()
                if room_key not in rooms:
                    rooms[room_key] = add_room(project_id, room_key)
                room_id = rooms[room_key]
            result = add_boq_item(project_id,
                input_name=str(row.get("item_name") or "").strip(),
                specification=str(row.get("specification") or "").strip() or None,
                quantity=row.get("quantity"), unit=row.get("unit"),
                budget_unit_price=row.get("budget_unit_price"), room_id=room_id,
                source_product_code=row.get("material_code") or row.get("source_product_code"),
                source_row_no=row.get("source_row_no"), actor="excel_import")
            if result["item_id"]:
                imported += 1
        except Exception as exc:
            rejected += 1
            append_event("boq_row_rejected", project_id=project_id,
                         source_row_no=row.get("source_row_no"), reason=str(exc)[:300])
    append_event("boq_import", project_id=project_id, rows_read=len(rows),
                 rows_saved=imported, rows_rejected=rejected)
    return {"rows_read": len(rows), "rows_saved": imported, "rows_rejected": rejected}


def list_boq_items(project_id):
    return query("""SELECT bi.item_id, pr.room_name, bi.input_name, bi.input_specification,
        bi.quantity, bi.input_unit, bi.budget_unit_price, m.material_id,
        m.canonical_name, bi.match_status
        FROM boq_items bi LEFT JOIN project_rooms pr ON pr.room_id=bi.room_id
        LEFT JOIN materials m ON m.material_id=bi.material_id
        WHERE bi.project_id=%s AND bi.is_deleted=0 ORDER BY bi.item_id""", (project_id,))


def update_boq_item(item_id, *, quantity=None, unit=None, budget_unit_price=None,
                    input_name=None, specification=None):
    parsed_budget = parse_decimal(budget_unit_price) if budget_unit_price is not None else None
    if budget_unit_price not in (None, "") and parsed_budget is None:
        raise ValueError("ราคา BOQ ต้องเป็นตัวเลข")
    allowed = {"quantity": quantity, "input_unit": normalize_unit(unit) if unit else None,
               "budget_unit_price": parsed_budget,
               "input_name": input_name.strip() if input_name is not None else None,
               "input_specification": specification.strip() if specification is not None else None}
    fields = [(key, value) for key, value in allowed.items() if value is not None]
    if not fields:
        return 0
    if "quantity" in dict(fields):
        parsed_quantity = parse_decimal(dict(fields)["quantity"])
        if parsed_quantity is None or parsed_quantity <= 0:
            raise ValueError("จำนวนต้องเป็นตัวเลขมากกว่า 0")
        fields = [(key, parsed_quantity if key == "quantity" else value) for key, value in fields]
    if "budget_unit_price" in dict(fields) and dict(fields)["budget_unit_price"] is not None and dict(fields)["budget_unit_price"] < 0:
        raise ValueError("ราคา BOQ ต้องไม่ติดลบ")
    assignments = ",".join(f"{key}=%s" for key, _ in fields)
    params = [value for _, value in fields]
    rematch = any(k in {"input_name", "input_specification", "input_unit"} for k, _ in fields)
    if rematch:
        assignments += ",material_id=NULL,match_status='UNMATCHED'"
    params.append(item_id)
    with connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE boq_items SET {assignments} WHERE item_id=%s AND is_deleted=0", params)
        updated = cursor.rowcount
        if rematch and updated:
            cursor.execute("""SELECT project_id,input_name,input_specification,input_unit,source_product_code
                FROM boq_items WHERE item_id=%s""", (item_id,))
            project_id, name, spec, item_unit, product_code = cursor.fetchone()
            candidates = find_candidates(cursor, name, spec, item_unit, product_code)
            exact = candidates[0] if candidates and candidates[0]["exact"] else None
            status = "AUTO_MATCHED" if exact else ("NEEDS_REVIEW" if candidates else "UNMATCHED")
            cursor.execute("UPDATE boq_items SET material_id=%s,match_status=%s WHERE item_id=%s",
                           (exact["material_id"] if exact else None, status, item_id))
            log_candidate_set(cursor, input_name=name, input_specification=spec,
                              input_unit=item_unit, candidates=candidates,
                              project_id=project_id, item_id=item_id, actor="update_rematch")
    append_event("boq_item_updated", item_id=item_id, changed_fields=[k for k, _ in fields])
    return updated


def delete_boq_item(item_id, confirmed=False):
    if not confirmed:
        raise ValueError("ต้องยืนยัน confirmed=True ก่อนลบรายการ")
    with connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE boq_items SET is_deleted=1 WHERE item_id=%s AND is_deleted=0", (item_id,))
        deleted = cursor.rowcount
    append_event("boq_item_deleted", item_id=item_id, deleted=bool(deleted))
    return deleted

"""Main Python entry point for the BOQ Intelligence Platform MVP."""
from pathlib import Path

from boq_platform.analytics import generate_insights
from boq_platform.audit import append_event
from boq_platform.dashboard import print_dashboard
from boq_platform.db import connection, query
from boq_platform.ingest import import_boq_rows, import_moc_prices, import_retail_csv, read_boq_excel
from boq_platform.projects import (add_boq_item, add_room, confirm_boq_match,
                                  create_project, delete_boq_item, list_boq_items,
                                  update_boq_item)
from boq_platform.quality_review import list_price_review_queue, resolve_price_review


def _input_int(label, default=None):
    value = input(f"{label}{f' [{default}]' if default is not None else ''}: ").strip()
    return int(value or default) if value or default is not None else None


def _project_id():
    projects = query("SELECT project_id,project_name,scope_type,created_at FROM boq_projects ORDER BY project_id DESC LIMIT 20")
    if not projects:
        print("ยังไม่มีโครงการ กรุณาสร้างโครงการก่อน")
        return None
    print("\nโครงการล่าสุด")
    for row in projects:
        print(f"{row['project_id']}: {row['project_name']} [{row['scope_type']}] - {row['created_at']}")
    return _input_int("Project ID")


def _create_project():
    print("ขอบเขต: 1 บ้านทั้งหลัง | 2 ห้อง/พื้นที่ | 3 รายชิ้น")
    scope = {"1": "house", "2": "room", "3": "item"}.get(input("เลือก: ").strip())
    if not scope:
        print("ตัวเลือกไม่ถูกต้อง")
        return
    name = input("ชื่อโครงการ: ").strip() or "BOQ Project"
    province_code = input("รหัสจังหวัด MOC (เว้นว่างได้): ").strip() or None
    province_name = input("ชื่อจังหวัด (เว้นว่างได้): ").strip() or None
    budget_total = input("งบประมาณรวม (เว้นว่างได้): ").strip() or None
    project_id = create_project(name, scope, province_code, province_name, budget_total)
    print(f"สร้างโครงการแล้ว: Project ID {project_id}")


def _import_official():
    province = input("รหัสจังหวัด (ตัวอย่าง 10 = กรุงเทพฯ): ").strip()
    if not province:
        print("ต้องระบุรหัสจังหวัด")
        return
    from_year = _input_int("ปีเริ่มต้น ค.ศ.")
    to_year = _input_int("ปีสิ้นสุด ค.ศ.")
    result = import_moc_prices(province, from_year, to_year)
    print(f"นำเข้า {result['rows_saved']} แถว, ปฏิเสธ {result['rows_rejected']} แถว; raw: {result['raw_file'].name}")


def _import_retail():
    path = input("พาธไฟล์ CSV ตาม templates/retail_prices_template.csv: ").strip().strip('"')
    if not Path(path).is_file():
        print("ไม่พบไฟล์")
        return
    result = import_retail_csv(path)
    print(f"นำเข้า {result['rows_saved']} แถว, ไม่ผ่าน {result['rows_rejected']} แถว, "
          f"ยังไม่จับคู่ {result['rows_unmatched']} แถว")


def _import_excel():
    project_id = _project_id()
    if not project_id:
        return
    path = input("พาธ Excel BOQ: ").strip().strip('"')
    if not Path(path).is_file():
        print("ไม่พบไฟล์")
        return
    rows = read_boq_excel(path)
    result = import_boq_rows(project_id, rows)
    print(f"นำเข้า {result['rows_saved']}/{result['rows_read']} แถว; ผิดพลาด {result['rows_rejected']} แถว")


def _manual_entry():
    project_id = _project_id()
    if not project_id:
        return
    room_id = None
    room = input("ชื่อห้อง/พื้นที่ (เว้นว่างได้): ").strip()
    if room:
        room_id = add_room(project_id, room)
    print("เพิ่มรายการวัสดุทีละรายการ พิมพ์ DONE ที่ชื่อวัสดุเพื่อจบ")
    while True:
        name = input("ชื่อวัสดุ: ").strip()
        if name.lower() == "done":
            break
        if not name:
            continue
        spec = input("สเปก/ขนาด (ถ้ามี): ").strip() or None
        qty = input("จำนวน: ").strip()
        unit = input("หน่วย: ").strip()
        budget = input("ราคา BOQ ต่อหน่วย (เว้นว่างได้): ").strip() or None
        result = add_boq_item(project_id, input_name=name, specification=spec,
                              quantity=qty, unit=unit, budget_unit_price=budget,
                              room_id=room_id)
        print(f"บันทึกรายการ {result['item_id']} สถานะ {result['match_status']}")
        if result["candidates"] and not result["candidates"][0]["exact"]:
            for i, candidate in enumerate(result["candidates"], start=1):
                print(f" {i}. {candidate['canonical_name']} / {candidate['standard_unit']} "
                      f"({candidate['confidence_score']:.0%})")
            choice = input("เลือกวัสดุที่ตรง (เลข 1-5) หรือเว้นว่างไว้ตรวจภายหลัง: ").strip()
            if choice.isdigit() and 1 <= int(choice) <= len(result["candidates"]):
                confirm_boq_match(result["item_id"], result["candidates"][int(choice)-1]["material_id"])
                print("ยืนยันการจับคู่แล้ว")


def _show_items():
    project_id = _project_id()
    if not project_id:
        return
    rows = list_boq_items(project_id)
    for row in rows:
        print(f"{row['item_id']}: {row['input_name']} | {row['quantity']} {row['input_unit']} | "
              f"BOQ ฿{row['budget_unit_price'] or 0} | {row['match_status']} | {row['canonical_name'] or 'ยังไม่จับคู่'}")
    if not rows:
        print("ไม่มีรายการ")
        return
    action = input("แก้รายการ (U), ลบรายการ (D), หรือ Enter กลับ: ").strip().lower()
    if action == "u":
        item_id = _input_int("Item ID")
        quantity = input("จำนวนใหม่ (เว้นว่าง=เดิม): ").strip() or None
        budget = input("ราคา BOQ ใหม่ (เว้นว่าง=เดิม): ").strip() or None
        update_boq_item(item_id, quantity=quantity, budget_unit_price=budget)
        print("อัปเดตรายการแล้ว")
    elif action == "d":
        item_id = _input_int("Item ID")
        if input(f"พิมพ์ DELETE {item_id} เพื่อยืนยัน: ").strip() == f"DELETE {item_id}":
            delete_boq_item(item_id, confirmed=True)
            print("ลบรายการแล้ว")
        else:
            print("ยกเลิกการลบ")


def _show_dashboard():
    project_id = _project_id()
    if project_id:
        print_dashboard(generate_insights(project_id))


def _review_prices():
    rows = list_price_review_queue()
    if not rows:
        print("ไม่มีรายการรอตรวจ")
        return
    for row in rows:
        print(f"{row['observation_id']}: {row['source_name']} | {row['product_name']} | "
              f"{row['price']} {row['unit']} | {row['observation_date']} | {row['quality_note']}")
    observation_id = _input_int("Observation ID ที่ต้องการตรวจ")
    decision = input("ยืนยัน valid / rejected: ").strip().lower()
    if resolve_price_review(observation_id, decision):
        print("บันทึกผลตรวจแล้ว")
    else:
        print("ไม่พบรายการที่รอตรวจตาม ID นี้")


def _check_row_counts():
    tables = [
        ("materials", "วัสดุ"),
        ("material_aliases", "ชื่อเรียกวัสดุ"),
        ("price_observations", "ประวัติราคา"),
        ("boq_projects", "โครงการ"),
        ("project_rooms", "ห้อง/พื้นที่"),
        ("boq_items", "รายการ BOQ (ไม่นับ soft delete)"),
        ("match_events", "หลักฐานการจับคู่"),
    ]
    print("\nตรวจจำนวนแถวสำหรับเกณฑ์รายวิชา (เป้าหมาย 30 แถว)")
    for table, label in tables:
        where = " WHERE is_deleted=0" if table == "boq_items" else ""
        row = query(f"SELECT COUNT(*) AS n FROM {table}{where}")
        count = row[0]["n"]
        status = "ผ่าน" if count >= 30 else f"ยังขาด {30-count}"
        print(f"{label}: {count} — {status}")
    print("price_sources เป็นตารางอ้างอิงแหล่งข้อมูลที่มีจำนวนจำกัด")


def _health():
    with connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT VERSION()")
        version = cursor.fetchone()[0]
    print(f"เชื่อมต่อ MySQL แล้ว (version {version})")


def main():
    try:
        _health()
    except Exception as exc:
        print("เชื่อมต่อฐานข้อมูลไม่ได้ กรุณาตรวจ .env และรัน schema.sql ก่อน")
        print(f"รายละเอียด: {exc}")
        return
    append_event("application_started", entry_point="main.py")
    actions = {
        "1": ("สร้างโครงการ", _create_project),
        "2": ("ดึงราคาทางการ Dataset 2 จาก MOC API", _import_official),
        "3": ("นำเข้าราคาจากร้านค้า CSV snapshot", _import_retail),
        "4": ("นำเข้า BOQ จาก Excel", _import_excel),
        "5": ("เพิ่ม BOQ แบบกรอกเอง (จบด้วย DONE)", _manual_entry),
        "6": ("ดู / แก้ไข / ลบ BOQ items", _show_items),
        "7": ("Dashboard + Insight + Action Plan", _show_dashboard),
        "8": ("ตรวจ/อนุมัติราคาที่ถูกพักรอตรวจ", _review_prices),
        "9": ("ตรวจจำนวนแถวตามเกณฑ์รายวิชา", _check_row_counts),
    }
    while True:
        print("\n=== BOQ Intelligence Platform ===")
        for key, (label, _) in actions.items():
            print(f"{key}. {label}")
        print("0. ออกจากระบบ")
        choice = input("เลือกเมนู: ").strip()
        if choice == "0":
            append_event("application_stopped", entry_point="main.py")
            print("จบการทำงาน")
            break
        action = actions.get(choice)
        if not action:
            print("ไม่พบเมนูนี้")
            continue
        try:
            action[1]()
        except KeyboardInterrupt:
            print("\nยกเลิกการทำงานรายการนี้")
            append_event("operation_cancelled", menu=choice)
        except Exception as exc:
            print(f"ทำรายการไม่สำเร็จ: {exc}")
            append_event("operation_error", menu=choice, error=str(exc)[:500])


if __name__ == "__main__":
    main()

"""BOQ Intelligence Platform: main menu. Run with `python main.py`.

Each menu item calls one module. To add your feature, edit only your own line in MENU
(and your own file). Errors inside a feature are logged and shown, and the menu keeps
running, so one unfinished feature does not stop the others.
"""

import sys

import analytics
from db import get_connection, query
from logger import get_logger
from menus import basket, exporter, search

log = get_logger("main")


def run_report():
    """List the reports registered in analytics.REPORTS and run the chosen one."""
    if not analytics.REPORTS:
        print("ยังไม่มีรายงาน (ลงทะเบียนรายงานใน analytics/__init__.py)")
        return
    for number, report in enumerate(analytics.REPORTS, start=1):
        print(f"  {number}. {report['title']}")
    choice = input("เลือกรายงาน: ").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(analytics.REPORTS):
        analytics.REPORTS[int(choice) - 1]["run"]()
    else:
        print("ไม่มีรายงานหมายเลขนี้")


def show_database_status():
    """Row count of each table and the TPSO months loaded: a quick setup check."""
    for table in ("master_product", "tpso_price", "material_prices_long", "user_input_batch"):
        count = query(f"SELECT COUNT(*) AS n FROM {table}")[0]["n"]
        print(f"  {table:<22} {count:>8,} แถว")
    months = query("SELECT DISTINCT price_period FROM master_product"
                   " WHERE source = 'TPSO' ORDER BY price_period")
    print("  เดือนที่มีราคา สนค.:", ", ".join(m["price_period"] for m in months) or "-")


# (key, label, function). Each person edits only their own line.
MENU = [
    ("1", "ค้นหาวัสดุและราคา", search.run),
    ("2", "ประมาณราคา BOQ", basket.run),
    ("3", "รายงานวิเคราะห์", run_report),
    ("4", "ส่งออกข้อมูล", exporter.run),
    ("5", "ตรวจสถานะฐานข้อมูล", show_database_status),
]


def check_connection():
    try:
        get_connection().close()
        return True
    except Exception as error:
        print("เชื่อมต่อฐานข้อมูลไม่ได้:", error)
        print("ตรวจ .env (DB_HOST, DB_USER, DB_PASSWORD, DB_NAME=boq_intelligence)")
        print("และ import db/boq_intelligence_dump.sql เข้า MySQL แล้วหรือยัง (ดู README)")
        return False


def main():
    if not check_connection():
        return 1
    while True:
        print("\n=== BOQ Intelligence Platform ===")
        for key, label, _ in MENU:
            print(f"  {key}. {label}")
        print("  0. ออก")
        try:
            choice = input("เลือกเมนู: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if choice == "0":
            return 0
        action = next((func for key, _, func in MENU if key == choice), None)
        if action is None:
            print("ไม่มีเมนูนี้")
            continue
        try:
            action()
        except KeyboardInterrupt:
            print("\nยกเลิก กลับเมนูหลัก")
        except Exception as error:
            log.exception("menu %s failed", choice)
            print(f"เกิดข้อผิดพลาด: {error} (รายละเอียดใน logs/app.log)")


if __name__ == "__main__":
    sys.exit(main())

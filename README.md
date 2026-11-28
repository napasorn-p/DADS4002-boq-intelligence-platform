# BOQ Intelligence Platform

DADS 4002 Programming Project 1/2569 (Python + MySQL, กลุ่ม 3 คน). ระบบวิเคราะห์ราคาวัสดุก่อสร้างและประมาณราคา BOQ จากข้อมูลราคาจริงของ สนค. (index-api.tpso.go.th) และราคาร้านค้า ใช้งานได้ 2 แบบ: หน้าต่างโปรแกรม (GUI) สำหรับกรอกราคา BOQ `python app_gui.py` และเมนูบน command line `python main.py`

## เริ่มต้นสำหรับสมาชิกทีม

**ทางที่ 1: GitHub Codespaces (แนะนำ ไม่ต้องติดตั้งอะไร)**

1. ที่หน้า repo บน GitHub กด **Code → Codespaces → Create codespace on main**
2. รอครั้งแรกประมาณ 3–5 นาที ระบบติดตั้ง MySQL 8, ไลบรารี Python, import ฐานข้อมูลทีม และสร้าง `.env` ให้เอง
3. เปิด Terminal แล้วรัน:

   ```bash
   python main.py
   ```

   เลือกเมนู 5 ต้องเห็น `master_product 5,535 แถว`

- เปิด Codespace ครั้งต่อไป MySQL จะเปิดเอง
- `git pull` แล้ว dump ใน `db/` เปลี่ยน ฐานข้อมูลจะถูก import ใหม่เอง (ตารางกลับเป็นตาม dump)
- ถ้าสร้าง Codespace ไว้ก่อนวันที่ 28 พ.ย. 2569: `git pull` แล้วกด F1 → **Codespaces: Rebuild Container** ครั้งเดียว
- ถ้ามีอะไรค้าง ให้รัน `bash scripts/setup_db.sh` (รันซ้ำได้ ไม่เสียหาย)

**ทางที่ 2: เครื่องตัวเอง (MySQL Workbench)**

1. ติดตั้ง [Git](https://git-scm.com/downloads), [Python 3.10+](https://www.python.org/downloads/) (Windows: ติ๊ก "Add Python to PATH") และ [MySQL 8 + Workbench](https://dev.mysql.com/downloads/)
2. Clone โปรเจคแล้วเข้าโฟลเดอร์:

   ```bash
   git clone https://github.com/napasorn-p/DADS4002-boq-intelligence-platform.git
   cd DADS4002-boq-intelligence-platform
   ```

3. สร้าง virtual environment แล้วติดตั้งไลบรารี:

   ```bash
   python -m venv .venv
   # Windows PowerShell: .venv\Scripts\Activate.ps1
   # macOS/Linux: source .venv/bin/activate
   pip install -r requirements.txt
   ```

4. Import ฐานข้อมูลทีม: Workbench → Server → Data Import → Import from Self-Contained File → เลือก `db/boq_intelligence_dump.sql` → Start Import (ทำใหม่ทุกครั้งที่ dump ใน `db/` เปลี่ยน)
5. คัดลอก `.env.example` เป็น `.env` แล้วใส่ `DB_USER` / `DB_PASSWORD` ของ MySQL ในเครื่องตัวเอง (`DB_NAME=boq_intelligence`)
6. รัน `python main.py` แล้วเลือกเมนู 5 ต้องเห็น `master_product 5,535 แถว`

**ทดสอบ (ทั้งสองทาง)**

```bash
python -m unittest -v
```

ต้องจบด้วย `OK` ทดสอบว่าต่อฐานได้, ข้อมูลครบ, ทุกเมนูรันได้ไม่ error และ `import_data.py` อ่านข้อมูลถูก ถ้าเมนูของใครพัง test `test_every_menu_item_runs` จะ fail (ดูรายละเอียดใน `logs/app.log`)

- ฟีเจอร์ต้องกลับเมนูได้เมื่อผู้ใช้กด Enter เปล่า ๆ ตอน test ระบบจะป้อนค่าว่างให้ทุกคำถาม
- เพิ่ม test ของฟีเจอร์ตัวเองได้ในไฟล์ใหม่ `tests/test_<ฟีเจอร์>.py`
- **ทุก pull request GitHub จะรัน test ให้เอง** (แท็บ Checks / Actions) ถ้าขึ้นสีแดง ให้แก้ก่อน merge

**ทุกครั้งที่เริ่มงาน**

```bash
git checkout main
git pull origin main
git checkout -b feature/<ชื่อ>      # ครั้งแรก; ครั้งต่อไปใช้ git checkout feature/<ชื่อ> แล้ว git merge main
```

เขียนโค้ดเฉพาะไฟล์ของตัวเอง แล้ว commit ทีละน้อย:

```bash
git add <ไฟล์ของตัวเอง>
git commit -m "อธิบายสั้น ๆ ว่าเปลี่ยนอะไร"
git push -u origin feature/<ชื่อ>
```

เสร็จแต่ละส่วน: เปิด pull request จาก `feature/<ชื่อ>` เข้า `main` บน GitHub ให้เพื่อน approve 1 คน แล้ว merge

## หน้าต่างกรอกราคา BOQ (GUI)

```bash
python app_gui.py
```

เปิดบน**เครื่องตัวเอง** (Windows / macOS) ที่ตั้งค่าตาม "ทางที่ 2" แล้ว ใน Codespaces เปิดหน้าต่างไม่ได้เพราะไม่มีหน้าจอ (ใช้ `main.py` และ test ได้ตามปกติ) Tkinter มากับ Python ไม่ต้องติดตั้งเพิ่ม

ถ้าเคย import dump ก่อนวันที่ 28 พ.ย. 2569 ให้ import `db/boq_intelligence_dump.sql` ใหม่หนึ่งครั้ง (เพิ่มตาราง `user_input_line`)

ผู้ใช้เพิ่ม/ดู/แก้/ลบได้เฉพาะข้อมูลของผู้ใช้ (`user_input_batch`, `user_input_line`) ส่วนตารางราคาใช้ค้นหาและเทียบราคาเท่านั้น ไม่ถูกแก้

- **ชุดข้อมูล BOQ (ตารางบน):** สร้างชุดใหม่, นำเข้า CSV, แก้ชื่อโครงการ, ยืนยัน/ยกเลิกยืนยัน (ชุดที่ยืนยันแล้วแก้รายการไม่ได้), ลบชุด (ลบรายการในชุดด้วย)
- **รายการ (ตารางล่าง + ฟอร์ม):** กรอกชื่อรายการ, หน่วย, จำนวน, ราคาต่อหน่วย แล้วกด "เพิ่มรายการ" คลิกรายการในตารางเพื่อแก้หรือลบ "ค้นหาราคา..." ผูกรายการกับราคา สนค./ร้านค้า แล้วตารางจะแสดงราคาอ้างอิงและยอดรวมเทียบกัน (เทียบเฉพาะรายการที่หน่วยตรงกัน)
- **CSV:** กด "บันทึกแม่แบบ CSV..." หรือใช้ `templates/boq_input_template.csv` คอลัมน์ที่ต้องมี `item_name`, `unit`, `quantity` ไม่บังคับ `unit_price`, `commodity_code` (รหัส สนค. 16 หลัก ผูกราคาให้อัตโนมัติ), `note` รับไฟล์ UTF-8 (Excel: CSV UTF-8) และ Windows Thai แถวที่ผิดจะไม่ถูกบันทึก และโปรแกรมบอกเลขแถวกับสาเหตุ ชุดนั้นจะมีสถานะ "มีแถวผิด"

โค้ดแยกเป็น 2 ชั้น: `boq_store.py` (ตรวจข้อมูล + SQL ทั้งหมด, มี test) และ `app_gui.py` (หน้าต่างเท่านั้น) เมนู CLI ใช้ `boq_store` ตัวเดียวกันได้

## กติกาการทำงานร่วมกัน

- ทุกคนทำงานบน branch `feature/<ชื่อ>` ที่แตกจาก `main`; `main` รับเฉพาะ pull request ที่มีคน approve
- แก้เฉพาะไฟล์ที่ตนรับผิดชอบ (ตารางด้านล่าง)
- `main.py` (รายการ `MENU`) และ `analytics/__init__.py` (รายการ `REPORTS`): แก้ได้เฉพาะบรรทัดที่ลงทะเบียนฟีเจอร์ของตน
- ต่อฐานข้อมูลผ่าน `db.query()` / `db.execute()` / `db.get_connection()` และส่งค่าจากผู้ใช้ผ่าน `%s` เสมอ
- แก้โครงสร้างตารางผ่าน `schema.sql` + pull request เท่านั้น (ดู [Database](#database))
- ใช้ข้อมูลจริงเท่านั้น ห้ามใส่ราคาสมมติหรือข้อมูลทดสอบลงฐานหรือ dump
- ห้าม commit `.env` และ `data_raw/`
- commit ทีละน้อย พร้อมข้อความที่บอกว่าเปลี่ยนอะไร

## ผู้รับผิดชอบ

| คน | ชื่อ | ไฟล์ | Insight |
|---|---|---|---|
| 1 |  | `schema.sql`, `db.py`, `import_data.py`, `db/` (ฐานข้อมูลและการนำเข้า) |  |
| 2 |  | `app_gui.py`, `boq_store.py`, `menus/search.py`, `menus/basket.py` (หน้าต่างกรอก BOQ, ค้นหา, ประมาณราคา) |  |
| 3 |  | `analytics/`, `menus/exporter.py` (รายงานวิเคราะห์, ส่งออก) |  |

## โครงสร้างโปรเจค

```
app_gui.py            หน้าต่างกรอกราคา BOQ (Tkinter): python app_gui.py
boq_store.py          เพิ่ม/อ่าน/แก้/ลบ ชุดและรายการ BOQ, อ่าน CSV (ใช้ร่วมกันทั้ง GUI และ CLI)
main.py               เมนูหลัก: เรียกฟีเจอร์ของแต่ละคนผ่านรายการ MENU (เมนู 5 = ตรวจฐานข้อมูล)
db.py                 get_connection(), query(), execute() ต่อ MySQL ตาม .env
logger.py             get_logger() เขียน log ไปที่ logs/app.log
import_data.py        เพิ่มราคา สนค. รายเดือนจากไฟล์ JSON
schema.sql            โครงสร้าง 4 ตาราง
db/boq_intelligence_dump.sql   ฐานข้อมูลทีม (โครงสร้าง + ข้อมูลจริง)
menus/search.py       เมนู 1 ค้นหาวัสดุและราคา   (ยังไม่ได้ทำ)
menus/basket.py       เมนู 2 ประมาณราคา BOQ      (ยังไม่ได้ทำ)
menus/exporter.py     เมนู 4 ส่งออกข้อมูล         (ยังไม่ได้ทำ)
analytics/            เมนู 3 รายงานวิเคราะห์ (ลงทะเบียนใน REPORTS)
templates/            boq_input_template.csv = แม่แบบ CSV สำหรับ GUI (ไฟล์อื่นเป็นของร่างแรก)
docs/                 ER diagram (png, Workbench model) และคำอธิบาย
legacy/               โค้ดร่างแรกสำหรับ schema เก่า: ใช้อ้างอิง/คัดลอก ไม่ได้ถูกเรียก
scripts/setup_db.sh   เปิด MySQL + import dump + สร้าง .env (Codespaces / Linux)
tests/                python -m unittest -v
.devcontainer/        ตั้งค่า Codespaces อัตโนมัติ
.github/workflows/    รัน test ทุก pull request
```

โฟลเดอร์ที่ไม่ขึ้น git: `.env`, `data_raw/`, `logs/`, `exports/`, `.venv/`

## Data scope

- **Official source (Dataset 2):** TPSO/MOC monthly construction-material prices, imported from a saved JSON file in the TPSO monthly price layout (`commodityCode`, `commodityNameTH`, `unitName`, `curYear` (พ.ศ.), `curMonth`, `priceCur`, `type`, `typeName`). The file used for development is `10.json`: area `10` = ส่วนกลาง, October 2569 (2026), 5,461 commodities. Prices are cash prices **excluding VAT and delivery**.
  - The month already loaded is in `db/boq_intelligence_dump.sql`. To add more months, put the JSON files in `data_raw/` (git-ignored) and run `import_data.py` (see [Database](#database)).
  - The online endpoint `dataapi.moc.go.th/csi-indexes` was tested on 2026-11-23: it returns a national price **index** (`index_id`, `price_index`, base year 2015) and ignores `province_code`/`com_code`, so it cannot supply unit prices.
  - Only one month (ต.ค. 2569) is loaded so far; month-to-month trends need more months.
- **Retail prices:** HomePro and เฮียเชษฐ prices read from the stores' web pages (Nov 2569), 74 rows in `material_prices_long`. Other stores (ไทวัสดุ, โกลบอลเฮ้าส์, ดูโฮม) have no verified prices yet; unverified estimates were left out. Websites are not scraped automatically.
- National construction material index (Dataset 3) and standard construction prices (Dataset 4) are not mixed into the price tables. BOQCraft is a workflow reference, not a dataset.
- **Real data only.** Never add made-up, sample or estimated prices to the database or the dump.

## Database

Tables (diagram: `docs/er_diagram.png`, model: `docs/boq_model.mwb`, notes: `docs/ER_Diagram.md`):

- `master_product`: every price, TPSO or retail (`source`), one row per product per period
- `tpso_price`: TPSO fields, same `id` as its `master_product` row
- `material_prices_long`: retail store fields, same `id` as its `master_product` row
- `user_input_batch`: one row per BOQ input session (manual or CSV); status draft / validated / has_error / confirmed
- `user_input_line`: one row per BOQ line in a batch (`line_no`, `item_name`, `unit`, `quantity`, `unit_price`, `note`, optional `product_id` → `master_product`); deleted with its batch

Each team member runs MySQL 8 on their own computer. Git carries the structure (`schema.sql`) and the team's shared data (`db/boq_intelligence_dump.sql`).

**Get the team database (start here).** Import `db/boq_intelligence_dump.sql`. It creates `boq_intelligence` with all tables and data. In Workbench: Server → Data Import → Import from Self-Contained File → choose `db/boq_intelligence_dump.sql` → Start Import. Or:

```bash
mysql -u root -p < db/boq_intelligence_dump.sql
```

Importing again replaces the tables with the dump's copy (your own changes in those tables are lost).

What the dump contains (made 2026-11-28 from the database owner's Workbench):

| Table | Rows | Content |
|---|---|---|
| `master_product` | 5,535 | 5,461 TPSO + 74 retail |
| `tpso_price` | 5,461 | TPSO ส่วนกลาง, ต.ค. 2569 (one month), cash price excl. VAT and delivery |
| `material_prices_long` | 74 | HomePro 37, เฮียเชษฐ 37, read from the stores' web pages in Nov 2569; 34 of them have no price (`not_sold`, `not_found`, `quote_only`) |
| `user_input_batch` | 0 | filled by the program |
| `user_input_line` | 0 | filled by the program (GUI) |

111 retail rows marked `estimate` (ไทวัสดุ, โกลบอลเฮ้าส์, ดูโฮม: unverified estimates from an old Excel file) and one test row in `user_input_batch` were left out, because the project uses real observed data only.

**Empty tables only.** In Workbench: File → Open SQL Script → `schema.sql` → Execute (⚡). Or:

```bash
mysql -u root -p < schema.sql
```

**Add another TPSO month.** Put the TPSO monthly price JSON file in `data_raw/`, set `.env`, then:

```bash
python import_data.py data_raw/<file>.json
```

Rows are written the same way as the existing data: `id` = the TPSO record id, `store_name` = `สนค. (<typeName>)`, `availability` = `available`, `price_basis` = `tpso_reference`, `price_period` = `<curYear>-<MM>` in the Buddhist year (e.g. `2569-10`), `retrieved_date` = date of `createdAt`, plus a `tpso_price` row with the same `id`. Rows whose `id` is already in the database are skipped, so re-running is safe; rows without a valid id, price or month are rejected and counted. Several files can be given at once. `db.py` holds the shared connection (`get_connection()`).

**Update the shared dump (database owner, after adding real data).** In Workbench: Server → Data Export → tick `boq_intelligence` → Dump Structure and Data → Export to Self-Contained File → tick Include Create Schema → Start Export. Or:

```bash
mysqldump -u root -p --databases boq_intelligence --no-tablespaces --set-gtid-purged=OFF > db/boq_intelligence_dump.sql
```

Commit it on a branch and open a pull request.

Rules:

- Change tables only by editing `schema.sql` (and the Workbench model) on your branch and opening a pull request. Do not change tables only in your own MySQL.
- After a schema change is merged, make a new dump; everyone re-imports it.
- Dumps must contain real data only. Share a dump over 50 MB through Google Drive instead of git (GitHub rejects files over 100 MB).
- `.env` (your MySQL password) is never committed.

## ฟีเจอร์ของระบบ

รอตัดสินใจ

## Insight และ action plan

รอตัดสินใจ

## การใช้ AI coding (Claude Code) และ version control

(เว้นไว้เติมบทเรียนภายหลัง)

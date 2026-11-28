"""BOQ Intelligence Platform: desktop window for entering BOQ prices.

Run on your own computer:  python app_gui.py
(Needs MySQL with the team database and .env, as for main.py. Tkinter comes with
Python on Windows and macOS.)

Users create, edit and delete their own BOQ batches and lines here, either typed in
line by line or uploaded from a CSV file. Price tables are only read (search and the
reference price column), never changed. All database work is in boq_store.py.
"""

import getpass
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from tkinter import font as tkfont

import boq_store
from db import get_connection
from logger import get_logger

log = get_logger("app_gui")

STATUS_TH = {"draft": "ร่าง", "validated": "ตรวจแล้ว", "has_error": "มีแถวผิด",
             "confirmed": "ยืนยันแล้ว"}
METHOD_TH = {"manual": "กรอกเอง", "csv": "CSV"}
THAI_FONTS = ("Tahoma", "Leelawadee UI", "Thonburi", "Sukhumvit Set", "Noto Sans Thai", "Loma")


def money(value):
    return "" if value is None else f"{value:,.2f}"


def number(value):
    return "" if value is None else f"{value:,.2f}".rstrip("0").rstrip(".")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("BOQ Intelligence Platform - รายการ BOQ")
        self.geometry("1280x760")
        self.minsize(1000, 600)
        self._setup_fonts()
        self.batch_id = None          # selected batch
        self.line_id = None           # selected line (None = new line)
        self.product_id = None        # product linked in the form
        self._build_batches()
        self._build_lines()

    # ---------- layout ----------

    def _setup_fonts(self):
        available = set(tkfont.families(self))
        family = next((f for f in THAI_FONTS if f in available), None)
        for name in ("TkDefaultFont", "TkTextFont", "TkHeadingFont", "TkMenuFont"):
            named = tkfont.nametofont(name)
            named.configure(size=11, **({"family": family} if family else {}))
        style = ttk.Style(self)
        style.configure("Treeview", rowheight=26)
        style.configure("Title.TLabel", font=(family or "TkDefaultFont", 13, "bold"))

    def _build_batches(self):
        frame = ttk.Frame(self, padding=8)
        frame.pack(fill="both", expand=False)

        top = ttk.Frame(frame)
        top.pack(fill="x")
        ttk.Label(top, text="ชุดข้อมูล BOQ", style="Title.TLabel").pack(side="left")
        ttk.Label(top, text="   ผู้บันทึก:").pack(side="left")
        self.user_var = tk.StringVar(value=getpass.getuser())
        ttk.Entry(top, textvariable=self.user_var, width=16).pack(side="left")

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(6, 4))
        for text, command in (("สร้างชุดใหม่ (กรอกเอง)", self.new_batch),
                              ("นำเข้า CSV...", self.import_csv),
                              ("แก้ชื่อโครงการ", self.rename_batch),
                              ("ยืนยัน / ยกเลิกยืนยัน", self.toggle_confirm),
                              ("ลบชุด", self.delete_batch),
                              ("บันทึกแม่แบบ CSV...", self.save_template),
                              ("รีเฟรช", self.refresh_batches)):
            ttk.Button(buttons, text=text, command=command).pack(side="left", padx=(0, 6))

        columns = (("id", "เลขที่", 60), ("project", "โครงการ", 220), ("method", "วิธีกรอก", 80),
                   ("file", "ไฟล์", 160), ("by", "ผู้บันทึก", 100), ("created", "สร้างเมื่อ", 150),
                   ("lines", "รายการ", 70), ("errors", "แถวผิด", 70), ("status", "สถานะ", 90),
                   ("total", "รวม (บาท)", 120))
        self.batch_tree = self._tree(frame, columns, height=7)
        self.batch_tree.bind("<<TreeviewSelect>>", lambda _e: self._on_batch_selected())

    def _build_lines(self):
        frame = ttk.Frame(self, padding=8)
        frame.pack(fill="both", expand=True)
        self.batch_title = ttk.Label(frame, text="เลือกชุดข้อมูลด้านบน", style="Title.TLabel")
        self.batch_title.pack(anchor="w")

        columns = (("no", "ลำดับ", 50), ("item", "รายการ", 260), ("unit", "หน่วย", 70),
                   ("qty", "จำนวน", 80), ("price", "ราคา/หน่วย", 100), ("total", "รวม", 110),
                   ("product", "สินค้าอ้างอิง", 260), ("ref_price", "ราคาอ้างอิง", 100),
                   ("ref_total", "รวมตามราคาอ้างอิง", 130), ("note", "หมายเหตุ", 150))
        self.line_tree = self._tree(frame, columns, height=10)
        self.line_tree.bind("<<TreeviewSelect>>", lambda _e: self._on_line_selected())
        self.total_label = ttk.Label(frame, text="")
        self.total_label.pack(anchor="e", pady=(2, 6))

        form = ttk.LabelFrame(frame, text="เพิ่ม / แก้ไขรายการ", padding=8)
        form.pack(fill="x")
        self.form_vars = {key: tk.StringVar() for key in ("item_name", "unit", "quantity",
                                                           "unit_price", "note")}
        fields = (("ชื่อรายการ *", "item_name", 40), ("หน่วย *", "unit", 10),
                  ("จำนวน *", "quantity", 10), ("ราคา/หน่วย", "unit_price", 12),
                  ("หมายเหตุ", "note", 30))
        for column, (label, key, width) in enumerate(fields):
            ttk.Label(form, text=label).grid(row=0, column=column, sticky="w", padx=(0, 6))
            ttk.Entry(form, textvariable=self.form_vars[key], width=width).grid(
                row=1, column=column, sticky="we", padx=(0, 6))
        form.columnconfigure(0, weight=1)

        product_row = ttk.Frame(form)
        product_row.grid(row=2, column=0, columnspan=5, sticky="we", pady=(8, 0))
        ttk.Label(product_row, text="สินค้าอ้างอิง:").pack(side="left")
        self.product_label = ttk.Label(product_row, text="(ไม่ผูก)")
        self.product_label.pack(side="left", padx=6)
        ttk.Button(product_row, text="ค้นหาราคา...", command=self.pick_product).pack(side="left")
        ttk.Button(product_row, text="ไม่ผูกสินค้า",
                   command=lambda: self._set_product(None, None)).pack(side="left", padx=6)

        actions = ttk.Frame(form)
        actions.grid(row=3, column=0, columnspan=5, sticky="w", pady=(8, 0))
        for text, command in (("เพิ่มรายการ", self.add_line), ("บันทึกการแก้ไข", self.save_line),
                              ("ลบรายการ", self.delete_line), ("ล้างฟอร์ม", self.clear_form)):
            ttk.Button(actions, text=text, command=command).pack(side="left", padx=(0, 6))

    def _tree(self, parent, columns, height):
        holder = ttk.Frame(parent)
        holder.pack(fill="both", expand=True)
        tree = ttk.Treeview(holder, columns=[c[0] for c in columns], show="headings",
                            height=height, selectmode="browse")
        for key, heading, width in columns:
            tree.heading(key, text=heading)
            tree.column(key, width=width, anchor="w", stretch=key in ("project", "item", "product"))
        scroll = ttk.Scrollbar(holder, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        return tree

    # ---------- helpers ----------

    def run(self, action, success=None):
        """Run a database action; show input problems as warnings, other errors as errors."""
        try:
            result = action()
        except ValueError as error:
            messagebox.showwarning("ตรวจสอบข้อมูล", str(error), parent=self)
            return None
        except Exception as error:
            log.exception("GUI action failed")
            messagebox.showerror("เกิดข้อผิดพลาด", f"{error}\n\n(รายละเอียดใน logs/app.log)",
                                 parent=self)
            return None
        if success:
            success(result)
        return result

    def _need_batch(self):
        if self.batch_id is None:
            messagebox.showinfo("เลือกชุดข้อมูล", "กรุณาเลือกชุดข้อมูลในตารางด้านบนก่อน", parent=self)
            return False
        return True

    # ---------- batches ----------

    def refresh_batches(self, select=None):
        target = select if select is not None else self.batch_id  # read before clearing the table
        batches = self.run(boq_store.list_batches)
        if batches is None:
            return
        self.batch_tree.delete(*self.batch_tree.get_children())
        for b in batches:
            self.batch_tree.insert("", "end", iid=str(b["batch_id"]), values=(
                b["batch_id"], b["project_name"] or "", METHOD_TH.get(b["input_method"], ""),
                b["file_name"] or "", b["created_by"], f"{b['created_at']:%Y-%m-%d %H:%M}",
                b["line_count"], b["error_rows"], STATUS_TH.get(b["status"], b["status"]),
                money(b["total_amount"])))
        if target is not None and self.batch_tree.exists(str(target)):
            self.batch_tree.selection_set(str(target))
            self.batch_tree.see(str(target))
            self.batch_id = target
            self.refresh_lines()
        else:
            self.batch_id = None
            self.refresh_lines()

    def _on_batch_selected(self):
        selected = self.batch_tree.selection()
        self.batch_id = int(selected[0]) if selected else None
        self.clear_form()
        self.refresh_lines()

    def new_batch(self):
        name = simpledialog.askstring("สร้างชุดใหม่", "ชื่อโครงการ:", parent=self)
        if name is None:
            return
        self.run(lambda: boq_store.create_batch(name, self.user_var.get()),
                 lambda batch_id: self.refresh_batches(select=batch_id))

    def import_csv(self):
        path = filedialog.askopenfilename(parent=self, title="เลือกไฟล์ CSV",
                                          filetypes=(("CSV", "*.csv"), ("ทุกไฟล์", "*.*")))
        if not path:
            return
        result = self.run(lambda: boq_store.import_csv(path, self.user_var.get()))
        if result is None:
            return
        batch_id, saved, errors = result
        message = f"บันทึก {saved} รายการ"
        if errors:
            shown = "\n".join(f"แถว {row}: {text}" for row, text in errors[:15])
            more = f"\n... และอีก {len(errors) - 15} แถว" if len(errors) > 15 else ""
            message += f"\nไม่ได้บันทึก {len(errors)} แถว:\n{shown}{more}"
            messagebox.showwarning("นำเข้า CSV", message, parent=self)
        else:
            messagebox.showinfo("นำเข้า CSV", message, parent=self)
        self.refresh_batches(select=batch_id)

    def rename_batch(self):
        if not self._need_batch():
            return
        current = self.batch_tree.set(str(self.batch_id), "project")
        name = simpledialog.askstring("แก้ชื่อโครงการ", "ชื่อโครงการ:", initialvalue=current,
                                      parent=self)
        if name is not None:
            self.run(lambda: boq_store.rename_batch(self.batch_id, name),
                     lambda _r: self.refresh_batches())

    def toggle_confirm(self):
        if not self._need_batch():
            return
        batch = self.run(lambda: boq_store.get_batch(self.batch_id))
        if batch is None:
            return
        if batch["status"] == "confirmed":
            new_status, question = "draft", "ยกเลิกการยืนยัน เพื่อแก้ไขรายการได้อีกครั้ง?"
        else:
            new_status, question = "confirmed", "ยืนยันชุดข้อมูลนี้? หลังยืนยันจะแก้ไขรายการไม่ได้"
        if messagebox.askyesno("สถานะ", question, parent=self):
            self.run(lambda: boq_store.set_status(self.batch_id, new_status),
                     lambda _r: self.refresh_batches())

    def delete_batch(self):
        if not self._need_batch():
            return
        lines = self.batch_tree.set(str(self.batch_id), "lines")
        if messagebox.askyesno("ลบชุดข้อมูล",
                               f"ลบชุดเลขที่ {self.batch_id} และรายการทั้งหมด {lines} รายการ?",
                               icon="warning", parent=self):
            self.run(lambda: boq_store.delete_batch(self.batch_id),
                     lambda _r: self.refresh_batches())

    def save_template(self):
        path = filedialog.asksaveasfilename(parent=self, title="บันทึกแม่แบบ CSV",
                                            defaultextension=".csv",
                                            initialfile="boq_input_template.csv",
                                            filetypes=(("CSV", "*.csv"),))
        if path:
            self.run(lambda: boq_store.write_csv_template(path),
                     lambda _r: messagebox.showinfo(
                         "แม่แบบ CSV", "บันทึกแล้ว\nคอลัมน์ที่ต้องมี: item_name, unit, quantity\n"
                         "ไม่บังคับ: unit_price, commodity_code (รหัส สนค. 16 หลัก), note",
                         parent=self))

    # ---------- lines ----------

    def refresh_lines(self):
        self.line_tree.delete(*self.line_tree.get_children())
        if self.batch_id is None:
            self.batch_title.configure(text="เลือกชุดข้อมูลด้านบน")
            self.total_label.configure(text="")
            return
        lines = self.run(lambda: boq_store.list_lines(self.batch_id))
        batch = self.run(lambda: boq_store.get_batch(self.batch_id))
        if lines is None or batch is None:
            return
        status = STATUS_TH.get(batch["status"], batch["status"])
        self.batch_title.configure(
            text=f"รายการของชุดเลขที่ {self.batch_id}: {batch['project_name'] or '-'}  [{status}]")
        total = ref_total = 0
        for line in lines:
            product = ""
            if line["product_id"]:
                product = f"{line['product_name']} ({line['store_name']}, {line['product_unit']})"
            self.line_tree.insert("", "end", iid=str(line["line_id"]), values=(
                line["line_no"], line["item_name"], line["unit"], number(line["quantity"]),
                money(line["unit_price"]), money(line["line_total"]), product,
                money(line["product_price"]), money(line["product_total"]), line["note"] or ""))
            total += line["line_total"] or 0
            ref_total += line["product_total"] or 0
        self.total_label.configure(
            text=f"รวมตาม BOQ: {money(total)} บาท    "
                 f"รวมตามราคาอ้างอิง (เฉพาะรายการที่หน่วยตรงกัน): {money(ref_total)} บาท")

    def _on_line_selected(self):
        selected = self.line_tree.selection()
        if not selected:
            return
        line_id = int(selected[0])
        lines = self.run(lambda: boq_store.list_lines(self.batch_id)) or []
        line = next((row for row in lines if row["line_id"] == line_id), None)
        if line is None:
            return
        self.line_id = line_id
        self.form_vars["item_name"].set(line["item_name"])
        self.form_vars["unit"].set(line["unit"])
        self.form_vars["quantity"].set(number(line["quantity"]))
        self.form_vars["unit_price"].set("" if line["unit_price"] is None else str(line["unit_price"]))
        self.form_vars["note"].set(line["note"] or "")
        label = f"{line['product_name']} ({line['store_name']})" if line["product_id"] else None
        self._set_product(line["product_id"], label)

    def _form_values(self):
        values = {key: var.get() for key, var in self.form_vars.items()}
        values["product_id"] = self.product_id
        return values

    def add_line(self):
        if not self._need_batch():
            return
        self.run(lambda: boq_store.add_line(self.batch_id, **self._form_values()),
                 lambda _r: (self.clear_form(), self.refresh_batches()))

    def save_line(self):
        if self.line_id is None:
            messagebox.showinfo("แก้ไขรายการ", "เลือกรายการในตารางก่อน หรือกด 'เพิ่มรายการ'",
                                parent=self)
            return
        self.run(lambda: boq_store.update_line(self.line_id, **self._form_values()),
                 lambda _r: (self.clear_form(), self.refresh_batches()))

    def delete_line(self):
        if self.line_id is None:
            messagebox.showinfo("ลบรายการ", "เลือกรายการในตารางก่อน", parent=self)
            return
        if messagebox.askyesno("ลบรายการ", "ลบรายการที่เลือก?", parent=self):
            self.run(lambda: boq_store.delete_line(self.line_id),
                     lambda _r: (self.clear_form(), self.refresh_batches()))

    def clear_form(self):
        self.line_id = None
        for var in self.form_vars.values():
            var.set("")
        self._set_product(None, None)
        if self.line_tree.selection():
            self.line_tree.selection_remove(self.line_tree.selection())

    def _set_product(self, product_id, label):
        self.product_id = product_id
        self.product_label.configure(text=label or "(ไม่ผูก)")

    def pick_product(self):
        ProductPicker(self, self.form_vars["item_name"].get(), self._picked)

    def _picked(self, product):
        self._set_product(product["id"], f"{product['product_name']} ({product['store_name']})")
        if not self.form_vars["item_name"].get().strip():
            self.form_vars["item_name"].set(product["product_name"][:255])
        if not self.form_vars["unit"].get().strip():
            self.form_vars["unit"].set(product["unit"])


class ProductPicker(tk.Toplevel):
    """Search master_product (read-only) and pick one row."""

    def __init__(self, app, text, on_pick):
        super().__init__(app)
        self.app, self.on_pick, self.rows = app, on_pick, {}
        self.title("ค้นหาราคาสินค้า")
        self.geometry("980x480")
        self.transient(app)

        bar = ttk.Frame(self, padding=8)
        bar.pack(fill="x")
        self.text = tk.StringVar(value=text)
        entry = ttk.Entry(bar, textvariable=self.text, width=50)
        entry.pack(side="left")
        entry.bind("<Return>", lambda _e: self.search())
        ttk.Button(bar, text="ค้นหา", command=self.search).pack(side="left", padx=6)
        ttk.Button(bar, text="เลือก", command=self.choose).pack(side="left")

        columns = (("source", "แหล่ง", 70), ("store", "ร้าน/แหล่ง", 140),
                   ("name", "สินค้า", 480), ("unit", "หน่วย", 70), ("price", "ราคา", 100),
                   ("period", "งวด", 80))
        self.tree = app._tree(self, columns, height=14)
        self.tree.bind("<Double-1>", lambda _e: self.choose())
        entry.focus_set()
        self.grab_set()
        if text.strip():
            self.search()

    def search(self):
        text = self.text.get().strip()
        if not text:
            return
        rows = self.app.run(lambda: boq_store.search_products(text))
        if rows is None:
            return
        self.tree.delete(*self.tree.get_children())
        self.rows = {str(row["id"]): row for row in rows}
        for row in rows:
            self.tree.insert("", "end", iid=str(row["id"]), values=(
                row["source"], row["store_name"], row["product_name"], row["unit"],
                money(row["price"]), row["price_period"]))
        if not rows:
            messagebox.showinfo("ค้นหา", "ไม่พบสินค้าที่มีราคา", parent=self)

    def choose(self):
        selected = self.tree.selection()
        if not selected:
            return
        self.on_pick(self.rows[selected[0]])
        self.destroy()


def main():
    app = App()
    try:
        get_connection().close()
    except Exception as error:
        app.withdraw()
        messagebox.showerror(
            "เชื่อมต่อฐานข้อมูลไม่ได้",
            f"{error}\n\nตรวจ .env (DB_HOST, DB_USER, DB_PASSWORD, DB_NAME=boq_intelligence)\n"
            "และ import db/boq_intelligence_dump.sql เข้า MySQL แล้วหรือยัง (ดู README)")
        app.destroy()
        return 1
    app.refresh_batches()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

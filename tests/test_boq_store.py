"""Tests for boq_store.py (BOQ batches and lines). Each test removes what it creates."""

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

import boq_store
from db import query

TEST_USER = "unittest"


class BoqStoreTest(unittest.TestCase):
    def setUp(self):
        self.created = []
        self.tpso = query("SELECT id, commodity_code, product_name, unit, price FROM master_product"
                          " WHERE source = 'TPSO' AND price IS NOT NULL ORDER BY id LIMIT 1")[0]
        self.price_rows_before = self._price_table_counts()

    def tearDown(self):
        for batch_id in self.created:
            if query("SELECT 1 FROM user_input_batch WHERE batch_id = %s", (batch_id,)):
                boq_store.delete_batch(batch_id)
        self.assertEqual(self._price_table_counts(), self.price_rows_before,
                         "price tables must never change")

    @staticmethod
    def _price_table_counts():
        return [query(f"SELECT COUNT(*) AS n FROM {t}")[0]["n"]
                for t in ("master_product", "tpso_price", "material_prices_long")]

    def new_batch(self, **kwargs):
        batch_id = boq_store.create_batch(kwargs.pop("project_name", "TEST batch"), TEST_USER, **kwargs)
        self.created.append(batch_id)
        return batch_id

    # --- manual CRUD ---

    def test_manual_crud(self):
        batch_id = self.new_batch()
        line_id = boq_store.add_line(batch_id, self.tpso["product_name"], self.tpso["unit"], "2",
                                     "100.50", product_id=self.tpso["id"])
        boq_store.add_line(batch_id, "รายการที่สอง", "ชิ้น", 3)
        lines = boq_store.list_lines(batch_id)
        self.assertEqual([l["line_no"] for l in lines], [1, 2])
        self.assertEqual(lines[0]["line_total"], Decimal("201.0000"))
        self.assertEqual(lines[0]["product_price"], self.tpso["price"])
        self.assertEqual(lines[0]["product_total"], 2 * self.tpso["price"])
        self.assertIsNone(lines[1]["unit_price"])
        self.assertEqual(boq_store.get_batch(batch_id)["total_rows"], 2)

        boq_store.update_line(line_id, "แก้ชื่อ", "ชิ้น", "5", "10", product_id=None, note="n")
        line = boq_store.list_lines(batch_id)[0]
        self.assertEqual((line["item_name"], line["quantity"], line["product_id"], line["note"]),
                         ("แก้ชื่อ", Decimal("5.00"), None, "n"))

        boq_store.delete_line(line_id)
        self.assertEqual(len(boq_store.list_lines(batch_id)), 1)
        self.assertEqual(boq_store.get_batch(batch_id)["total_rows"], 1)

        boq_store.rename_batch(batch_id, "TEST renamed")
        listed = [b for b in boq_store.list_batches() if b["batch_id"] == batch_id][0]
        self.assertEqual((listed["project_name"], listed["line_count"]), ("TEST renamed", 1))

        boq_store.delete_batch(batch_id)
        self.assertEqual(query("SELECT COUNT(*) AS n FROM user_input_line WHERE batch_id = %s",
                               (batch_id,))[0]["n"], 0, "lines are deleted with their batch")

    def test_invalid_lines_rejected(self):
        batch_id = self.new_batch()
        for args in (("", "ชิ้น", 1), ("x", "", 1), ("x", "ชิ้น", 0), ("x", "ชิ้น", "abc"),
                     ("x", "ชิ้น", 1, "-5"), ("x", "ชิ้น", "nan")):
            with self.assertRaises(ValueError, msg=str(args)):
                boq_store.add_line(batch_id, *args)
        with self.assertRaises(ValueError):
            boq_store.add_line(batch_id, "x", "ชิ้น", 1, product_id=-1)
        self.assertEqual(boq_store.list_lines(batch_id), [])

    def test_confirmed_batch_is_locked(self):
        batch_id = self.new_batch()
        line_id = boq_store.add_line(batch_id, "x", "ชิ้น", 1)
        boq_store.set_status(batch_id, "confirmed")
        for action in (lambda: boq_store.add_line(batch_id, "y", "ชิ้น", 1),
                       lambda: boq_store.update_line(line_id, "y", "ชิ้น", 1),
                       lambda: boq_store.delete_line(line_id),
                       lambda: boq_store.rename_batch(batch_id, "z")):
            with self.assertRaises(ValueError):
                action()
        boq_store.set_status(batch_id, "draft")
        boq_store.add_line(batch_id, "y", "ชิ้น", 1)
        with self.assertRaises(ValueError):
            boq_store.set_status(batch_id, "done")

    def test_batch_requires_user_and_csv_file(self):
        with self.assertRaises(ValueError):
            boq_store.create_batch("p", "  ")
        with self.assertRaises(ValueError):
            boq_store.create_batch("p", TEST_USER, input_method="csv")

    # --- CSV ---

    def write_csv(self, text, encoding="utf-8-sig"):
        handle = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding=encoding,
                                             newline="")
        handle.write(text)
        handle.close()
        self.addCleanup(Path(handle.name).unlink)
        return handle.name

    def import_csv(self, text, **kwargs):
        batch_id, saved, errors = boq_store.import_csv(self.write_csv(text, **kwargs), TEST_USER)
        self.created.append(batch_id)
        return batch_id, saved, errors

    def test_csv_import_with_errors(self):
        code = self.tpso["commodity_code"]
        text = ("item_name,unit,quantity,unit_price,commodity_code,note\n"
                f"รายการ A,{self.tpso['unit']},2,,{code},\n"
                "รายการ B,ชิ้น,\"1,000\",12.5,,ok\n"
                "\n"
                ",ชิ้น,1,,,\n"
                "รายการ D,ชิ้น,-1,,,\n"
                "รายการ E,ชิ้น,1,,9999999999999999,\n")
        batch_id, saved, errors = self.import_csv(text)
        self.assertEqual(saved, 2)
        self.assertEqual([number for number, _ in errors], [5, 6, 7])
        batch = boq_store.get_batch(batch_id)
        self.assertEqual((batch["input_method"], batch["status"], batch["total_rows"],
                          batch["error_rows"]), ("csv", "has_error", 5, 3))
        self.assertTrue(batch["file_name"].endswith(".csv"))
        lines = boq_store.list_lines(batch_id)
        self.assertEqual(lines[0]["product_id"], self.tpso["id"])
        self.assertEqual(lines[1]["quantity"], Decimal("1000.00"))

    def test_csv_old_template_headers_and_thai_windows_encoding(self):
        header = Path("templates/boq_template.csv").read_text(encoding="utf-8-sig").splitlines()[0]
        self.assertIn("budget_unit_price", header)
        text = "item_name,quantity,unit,budget_unit_price,specification\nปูน,3,ถุง,120,มอก.\n"
        batch_id, saved, errors = self.import_csv(text, encoding="cp874")
        self.assertEqual((saved, errors), (1, []))
        self.assertEqual(boq_store.get_batch(batch_id)["status"], "validated")
        line = boq_store.list_lines(batch_id)[0]
        self.assertEqual((line["item_name"], line["unit_price"], line["note"]),
                         ("ปูน", Decimal("120.00"), "มอก."))

    def test_csv_missing_columns(self):
        with self.assertRaises(ValueError) as caught:
            boq_store.read_csv("name_only\nx\n")
        self.assertIn("unit", str(caught.exception))

    def test_template_written(self):
        path = Path(tempfile.mkdtemp()) / "t.csv"
        boq_store.write_csv_template(path)
        self.addCleanup(path.unlink)
        rows, errors = boq_store.read_csv(path)
        self.assertEqual((rows, errors), ([], []))

    def test_search_products_is_read_only_lookup(self):
        word = self.tpso["product_name"].split()[0]
        found = boq_store.search_products(word, limit=5)
        self.assertTrue(found)
        self.assertTrue(all(word in row["product_name"] for row in found))
        self.assertEqual(boq_store.product_by_code(self.tpso["commodity_code"])["id"], self.tpso["id"])


if __name__ == "__main__":
    unittest.main()

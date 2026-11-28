"""Checks that the project runs end to end. Run:  python -m unittest -v

Needs the team database (Codespaces sets it up; elsewhere import
db/boq_intelligence_dump.sql and fill in .env). Add tests for your own feature
in a new file tests/test_<feature>.py.
"""

import contextlib
import io
import unittest
from unittest import mock

import analytics
import import_data
import main
from db import get_connection, query


class DatabaseTest(unittest.TestCase):
    def test_connects(self):
        get_connection().close()

    def test_tables_have_team_data(self):
        counts = {t: query(f"SELECT COUNT(*) AS n FROM {t}")[0]["n"]
                  for t in ("master_product", "tpso_price", "material_prices_long")}
        self.assertGreater(counts["tpso_price"], 0, "no TPSO prices: import the team dump")
        self.assertGreater(counts["material_prices_long"], 0)
        self.assertEqual(counts["master_product"],
                         counts["tpso_price"] + counts["material_prices_long"],
                         "every master_product row needs exactly one detail row")

    def test_detail_rows_match_master(self):
        mismatched = query(
            "SELECT COUNT(*) AS n FROM master_product m JOIN tpso_price t ON t.id = m.id"
            " WHERE m.source <> 'TPSO' OR m.price <> t.priceCur OR m.commodity_code <> t.commodityCode")
        self.assertEqual(mismatched[0]["n"], 0)

    def test_no_estimated_prices(self):
        """Real data only: unverified estimates must not be in the database."""
        rows = query("SELECT COUNT(*) AS n FROM master_product WHERE price_basis = %s", ("estimate",))
        self.assertEqual(rows[0]["n"], 0)


class MenuTest(unittest.TestCase):
    def run_menu(self, keys):
        output = io.StringIO()
        with mock.patch("builtins.input", side_effect=keys), contextlib.redirect_stdout(output):
            code = main.main()
        return code, output.getvalue()

    def test_menu_entries_are_unique_and_callable(self):
        keys = [key for key, _, _ in main.MENU]
        self.assertEqual(len(keys), len(set(keys)), "two menu items use the same key")
        self.assertNotIn("0", keys, "0 is reserved for exit")
        for key, label, func in main.MENU:
            self.assertTrue(callable(func), f"menu {key} ({label}) is not a function")

    def test_every_menu_item_runs(self):
        """Choose every menu item once, then exit. Fails if any item raises an error."""
        keys = [key for key, _, _ in main.MENU]
        with mock.patch.object(main.log, "exception") as logged:
            code, _ = self.run_menu(keys + ["0"] + [""] * 50)
        self.assertEqual(code, 0)
        failures = [call.args for call in logged.call_args_list]
        self.assertEqual(failures, [], f"menu items raised errors: {failures} (see logs/app.log)")

    def test_status_menu_shows_rows(self):
        _, out = self.run_menu(["5", "0"])
        self.assertIn("master_product", out)

    def test_reports_registered_correctly(self):
        for report in analytics.REPORTS:
            self.assertIsInstance(report.get("title"), str)
            self.assertTrue(callable(report.get("run")), f"report {report.get('title')} has no run function")


class ImportDataTest(unittest.TestCase):
    def test_real_tpso_row_round_trip(self):
        """A real tpso_price row, written in the TPSO file layout, is read back unchanged."""
        row = query("SELECT * FROM tpso_price ORDER BY id LIMIT 1")[0]
        raw = dict(row, priceCur=str(row["priceCur"]), createdAt=row["createdAt"].isoformat())
        cleaned = import_data.clean_row(raw)
        master = query("SELECT * FROM master_product WHERE id = %s", (row["id"],))[0]
        self.assertEqual(cleaned["id"], master["id"])
        self.assertEqual(cleaned["store_name"], master["store_name"])
        self.assertEqual(cleaned["period"], master["price_period"])
        self.assertEqual(cleaned["price"], master["price"])
        self.assertEqual(cleaned["created_at"].date(), master["retrieved_date"])

    def test_rows_without_price_are_rejected(self):
        row = query("SELECT * FROM tpso_price ORDER BY id LIMIT 1")[0]
        raw = dict(row, priceCur=None, createdAt=row["createdAt"].isoformat())
        self.assertIsNone(import_data.clean_row(raw))


if __name__ == "__main__":
    unittest.main()

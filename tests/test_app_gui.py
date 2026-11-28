"""The GUI module loads and has its main pieces. Skipped where Python has no Tkinter."""

import importlib.util
import unittest


@unittest.skipIf(importlib.util.find_spec("tkinter") is None, "Tkinter not installed")
class AppGuiImportTest(unittest.TestCase):
    def test_module_loads(self):
        import app_gui
        for name in ("new_batch", "import_csv", "add_line", "save_line", "delete_line",
                     "delete_batch", "toggle_confirm", "pick_product"):
            self.assertTrue(callable(getattr(app_gui.App, name)), name)


if __name__ == "__main__":
    unittest.main()

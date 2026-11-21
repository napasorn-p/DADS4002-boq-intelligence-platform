"""Entry point: CLI menu controller.

Run with `python main.py`. Shows the main menu and dispatches each choice
to the feature modules (menus/, analytics/). Not implemented yet.
"""

from menus import search, basket, exporter  # noqa: F401
from analytics import REPORTS  # noqa: F401

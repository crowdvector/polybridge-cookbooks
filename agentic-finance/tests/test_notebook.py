from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
NOTEBOOK_PATH = BASE_DIR / "agentic-finance.ipynb"
SECRET_PATTERN = re.compile(
    r"Bearer\s+|\bsk-[A-Za-z0-9]|Authorization:\s*(?:Basic|ApiKey|Bearer)|"
    r"POLYBRIDGE_API_KEY\s*[=:]\s*[A-Za-z0-9]|ALPACA_SECRET|APCA_API_SECRET",
    re.IGNORECASE,
)
LOCAL_PATH_PATTERN = re.compile(r"/Users/|/home/|[A-Za-z]:\\\\")


class NotebookTests(unittest.TestCase):
    def load_notebook(self) -> dict:
        return json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))

    def test_notebook_exists(self) -> None:
        self.assertTrue(NOTEBOOK_PATH.exists())

    def test_code_cell_outputs_are_cleared(self) -> None:
        nb = self.load_notebook()
        bad_cells = []
        for index, cell in enumerate(nb.get("cells", [])):
            if cell.get("cell_type") != "code":
                continue
            if cell.get("execution_count") is not None or cell.get("outputs"):
                bad_cells.append(index)

        self.assertEqual(bad_cells, [])

    def test_notebook_has_no_obvious_secrets_or_local_paths(self) -> None:
        text = NOTEBOOK_PATH.read_text(encoding="utf-8")

        self.assertIsNone(SECRET_PATTERN.search(text))
        self.assertIsNone(LOCAL_PATH_PATTERN.search(text))


if __name__ == "__main__":
    unittest.main()

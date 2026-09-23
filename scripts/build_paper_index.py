"""Publish the single-page local workbench from its maintained template.

The browser loads run data in place; sealed experiment files are never modified.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    template = ROOT / "paper/dashboard.html"
    target = ROOT / "paper/index.html"
    target.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
    print(json.dumps({"paper_index": str(target), "layout": "light_single_page"}))


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Make sure `approach2-using-existing-graph` is importable when executed as a script.
THIS_FILE = Path(__file__).resolve()
APPROACH2_DIR = THIS_FILE.parents[1]
if str(APPROACH2_DIR) not in sys.path:
    sys.path.insert(0, str(APPROACH2_DIR))

from risk_scoring.reporting import render_markdown_report  # noqa: E402


def _read_json(path: Optional[str]) -> Dict[str, Any]:
    if path is None or path == "-":
        data = sys.stdin.read()
    else:
        data = Path(path).read_text(encoding="utf-8")
    obj = json.loads(data)
    if not isinstance(obj, dict):
        raise ValueError("Report JSON must be an object")
    return obj


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="VS Code entrypoint: risk report JSON -> markdown")
    parser.add_argument("--input", default="-", help="Path to report JSON, or '-' for stdin")
    parser.add_argument("--max-sample-rows", type=int, default=5)
    args = parser.parse_args(argv)

    report = _read_json(args.input)
    md = render_markdown_report(report, max_sample_rows=args.max_sample_rows)
    sys.stdout.write(md)
    if not md.endswith("\n"):
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from risk_scoring.canonical_change import canonicalize_from_normalized_diff, to_canonical_json
from risk_scoring.diff_capture import capture_normalized_diff


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="VS Code entrypoint: diff -> canonical change JSON")
    parser.add_argument("--repo-dir", required=True)
    parser.add_argument("--base-ref", default="HEAD")
    parser.add_argument("--path", action="append", default=[], help="Repeatable path filter")
    parser.add_argument("--environment", default=None)

    args = parser.parse_args(argv)

    nd = capture_normalized_diff(
        repo_dir=args.repo_dir,
        base_ref=args.base_ref,
        paths=args.path if args.path else None,
    )

    # Feed normalized diff through canonicalization.
    # We include environment as an optional hint; if omitted it stays unknown.
    nd_obj: Dict[str, Any] = nd.to_dict()
    if args.environment is not None and str(args.environment).strip() != "":
        nd_obj["environment"] = args.environment

    canonical = canonicalize_from_normalized_diff(nd_obj)
    sys.stdout.write(to_canonical_json(canonical, indent=2))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Snapshot the FastAPI OpenAPI schema to disk.

Writes ``frontend/schema/openapi.json`` so the frontend can regenerate its
TypeScript types (``openapi-typescript``) without needing a live backend.

Usage:
    python scripts/generate_openapi.py
    python scripts/generate_openapi.py --out path/to/openapi.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_OUT = ROOT / "frontend" / "schema" / "openapi.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"Output path (default: {DEFAULT_OUT.relative_to(ROOT)})",
    )
    args = parser.parse_args()

    from app.bootstrap import create_app

    app = create_app()
    schema = app.openapi()

    out: Path = args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    print(f"Wrote OpenAPI schema to {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

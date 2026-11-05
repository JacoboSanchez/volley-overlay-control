"""Write the overlay state contract to disk.

Produces, from :mod:`app.overlay.payload_schema`:

* ``overlay_static/schema/overlay-state.schema.json`` — a JSON Schema
  (draft 2020-12) of what ``/ws/{public_token}`` sends, for anyone writing
  an overlay template or a third-party consumer;
* ``overlay_static/schema/overlay-state.openapi.json`` — the same models as
  OpenAPI 3.1 components, the input ``openapi-typescript`` turns into
  ``overlay_static/js/types/overlay-state.d.ts``
  (``cd frontend && npm run gen:overlay-types``).

``tests/test_overlay_payload_contract.py`` fails when the committed files
drift from the models.

Usage:
    python scripts/generate_overlay_schema.py
    python scripts/generate_overlay_schema.py --check   # exit 1 on drift
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCHEMA_DIR = ROOT / "overlay_static" / "schema"
JSON_SCHEMA_PATH = SCHEMA_DIR / "overlay-state.schema.json"
OPENAPI_PATH = SCHEMA_DIR / "overlay-state.openapi.json"


def render() -> dict[Path, str]:
    """Return ``{path: file contents}`` for every generated artifact."""
    from pydantic.json_schema import models_json_schema

    from app.overlay.payload_schema import OverlayPayload, OverlayState

    json_schema = OverlayState.model_json_schema()
    json_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "overlay-state.schema.json",
        **json_schema,
    }

    _, defs = models_json_schema(
        [(OverlayState, "serialization"), (OverlayPayload, "serialization")],
        ref_template="#/components/schemas/{model}",
    )
    openapi: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {
            "title": "Volley Overlay Control — overlay state",
            "version": "1",
            "description": "What /ws/{public_token} sends to overlay clients.",
        },
        "paths": {},
        "components": {"schemas": defs.get("$defs", {})},
    }

    def dump(payload: dict[str, Any]) -> str:
        return json.dumps(payload, indent=2, sort_keys=True) + "\n"

    return {JSON_SCHEMA_PATH: dump(json_schema), OPENAPI_PATH: dump(openapi)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Fail instead of writing when files are stale",
    )
    args = parser.parse_args()

    stale = []
    for path, content in render().items():
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current == content:
            continue
        stale.append(path)
        if not args.check:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            print(f"Wrote {path.relative_to(ROOT)}")
    if args.check and stale:
        for path in stale:
            print(f"Stale: {path.relative_to(ROOT)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

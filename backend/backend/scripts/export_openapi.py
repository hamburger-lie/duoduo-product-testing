"""Export the OpenAPI schema from the FastAPI app to docs/openapi.v0.1.json.

Usage:
    uv run python scripts/export_openapi.py
"""

from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    from app.main import app

    schema = app.openapi()
    out = Path(__file__).resolve().parents[2] / "docs" / "openapi.v0.1.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(schema, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Exported OpenAPI schema to {out}")


if __name__ == "__main__":
    main()

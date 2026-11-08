from __future__ import annotations

import argparse
import json
from pathlib import Path

from proof.main import app


def main() -> None:
    parser = argparse.ArgumentParser(description="Export or check the committed Proof OpenAPI contract")
    parser.add_argument("--check", action="store_true", help="fail if the committed contract has drifted")
    args = parser.parse_args()
    output = Path(__file__).resolve().parents[1] / "docs" / "openapi.json"
    schema = app.openapi()
    if args.check:
        if not output.is_file() or json.loads(output.read_text(encoding="utf-8")) != schema:
            parser.exit(1, "OpenAPI contract is stale. Run uv run python scripts/export_openapi.py.\n")
        print("OpenAPI contract matches the application.")
        return
    output.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()

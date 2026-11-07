from __future__ import annotations

import json
from pathlib import Path

from proof.main import app

output = Path("docs/openapi.json")
output.write_text(json.dumps(app.openapi(), indent=2) + "\n", encoding="utf-8")
print(f"Wrote {output}")

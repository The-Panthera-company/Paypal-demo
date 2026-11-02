"""Write the OpenAPI spec to api/openapi.json for Postman and frontend type generation.

Run from api/ after changing any route or schema:  .venv/Scripts/python -m scripts.export_openapi
"""

import json
from pathlib import Path

from app.main import app

out = Path(__file__).resolve().parent.parent / "openapi.json"
out.write_text(json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"Wrote {out} ({len(app.openapi()['paths'])} paths)")

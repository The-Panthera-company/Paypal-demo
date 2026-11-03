"""Write the OpenAPI spec to api/openapi.json for Postman, APIMatic SDKs and frontend types.

Run from api/ after changing any route or schema:  .venv/Scripts/python -m scripts.export_openapi

The file lists the servers SDK generators should call. The running app leaves them out, so its
own /docs page keeps trying requests against whichever server is serving it.
"""

import json
from pathlib import Path

from app.main import app

SERVERS = [
    {"url": "https://giving-api.onrender.com", "description": "Render (sandbox PayPal)"},
    {"url": "http://localhost:8000", "description": "Local"},
]


def exported_spec() -> dict:
    return {**app.openapi(), "servers": SERVERS}


if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "openapi.json"
    spec = exported_spec()
    out.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {out} ({len(spec['paths'])} paths)")

"""Catalogue reads, token checks, stubs and the exported spec."""

import json
from pathlib import Path

from app.config import get_settings
from app.main import app
from app.schemas import DocumentOut

ADMIN = {"Authorization": "Bearer admin-test-token"}
INTERNAL = {"Authorization": "Bearer internal-test-token"}


def _donate(client, project_id=1, amount=2000):
    order_id = client.post(
        "/donations/orders", json={"target_type": "PROJECT", "project_id": project_id, "amount_cents": amount}
    ).json()["order_id"]
    client.post(f"/donations/orders/{order_id}/capture")


def test_categories_count_listed_projects_only(client):
    assert client.get("/categories").json() == [
        {"id": 1, "name": "Education", "project_count": 2},
        {"id": 2, "name": "Health", "project_count": 0},
    ]


def test_projects_list_filters_and_hides_location(client):
    titles = lambda r: [p["title"] for p in r.json()]
    assert titles(client.get("/projects")) == ["Lanet Library", "Faith School Desks"]  # urgency desc, no pending
    assert titles(client.get("/projects", params={"exclude_tags": "faith-based"})) == ["Lanet Library"]
    assert titles(client.get("/projects", params={"beneficiary_group": "children"})) == ["Lanet Library"]
    assert titles(client.get("/projects", params={"q": "desk"})) == ["Faith School Desks"]
    # A hidden location is neither shown nor filterable.
    assert titles(client.get("/projects", params={"region": "Kisumu"})) == []
    desks = next(p for p in client.get("/projects").json() if p["id"] == 2)
    assert desks["region"] is None


def test_project_totals_count_people_not_gifts(client):
    _donate(client)
    _donate(client)  # same sandbox payer twice
    p = client.get("/projects/1").json()
    assert (p["raised_cents"], p["backer_count"]) == (4000, 1)
    assert p["milestones"] == []
    assert client.get("/projects/3").status_code == 404  # pending_review is not public
    history = client.get("/projects/1/funding-history").json()
    assert history[-1]["raised_cents"] == 4000 and history[-1]["backer_count"] == 1


def test_donor_profile_update(client):
    _donate(client)
    r = client.patch("/donors/1", json={"show_on_leaderboard": True, "interests": {"categories": [1]}})
    assert r.status_code == 200
    assert r.json()["show_on_leaderboard"] is True
    assert client.get("/donors/1").json()["interests"] == {"categories": [1]}
    assert client.get("/donors/99").status_code == 404


def test_admin_routes_need_admin_token(client):
    assert client.get("/admin/projects").status_code == 401
    assert client.get("/admin/projects", headers=INTERNAL).status_code == 401
    r = client.get("/admin/projects", headers=ADMIN)
    assert [p["title"] for p in r.json()] == ["Clinic Roof"]


def test_internal_routes_need_internal_token(client):
    entry = {"actor": "giving-agent", "action": "skip", "rule_result": "excluded_tag", "reason": "faith-based"}
    assert client.post("/internal/audit", json=entry).status_code == 401
    assert client.post("/internal/audit", json=entry, headers=ADMIN).status_code == 401
    r = client.post("/internal/audit", json=entry, headers=INTERNAL)
    assert r.status_code == 201
    log = client.get("/admin/audit-log", headers=ADMIN).json()
    assert log[0]["reason"] == "faith-based"


def test_unset_token_fails_closed(client):
    from app.config import Settings, get_settings

    app.dependency_overrides[get_settings] = lambda: Settings(admin_token="")
    assert client.get("/admin/projects", headers={"Authorization": "Bearer "}).status_code in (401, 503)
    assert client.get("/admin/projects", headers=ADMIN).status_code == 503


def _stub_app(settings):
    """Every route is built now, so the stub helper is tried on an app of its own."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.stubs import Planned, planned, planned_handler

    stub = FastAPI()
    stub.add_exception_handler(Planned, planned_handler)
    stub.dependency_overrides[get_settings] = lambda: settings

    @stub.post("/documents", response_model=DocumentOut, status_code=201)
    def add_document():
        planned("document uploads")

    return TestClient(stub)


def test_stub_returns_spec_example():
    from app.config import Settings

    r = _stub_app(Settings(stub_examples=True)).post("/documents")
    assert r.status_code == 201  # the route's own status code
    assert r.headers["X-Stub"] == "document uploads"
    assert r.json() == DocumentOut.model_config["json_schema_extra"]["example"]


def test_stub_returns_501_when_examples_off():
    from app.config import Settings

    r = _stub_app(Settings(stub_examples=False)).post("/documents")
    assert r.status_code == 501
    assert r.json()["detail"] == {"error": "NOT_IMPLEMENTED", "message": "Planned: document uploads"}
    assert "X-Stub" not in r.headers


def test_exported_spec_is_current():
    """Fails when routes change without re-running scripts/export_openapi.py."""
    from scripts.export_openapi import exported_spec

    exported = json.loads((Path(__file__).parent.parent / "openapi.json").read_text(encoding="utf-8"))
    assert exported == json.loads(json.dumps(exported_spec()))
    assert exported["servers"][0]["url"] == "https://giving-api.onrender.com"  # SDKs call Render by default


def test_spec_wording_does_not_depend_on_python_version():
    """Python 3.13 renamed status 422 ("Unprocessable Entity" -> "Unprocessable Content"). A response
    without its own description would make openapi.json differ between machines."""
    assert "Unprocessable" not in json.dumps(app.openapi())


def test_spec_is_fully_documented():
    """Every schema, field and parameter has a description (APIMatic scores the spec on this)."""
    spec = app.openapi()
    schemas = spec["components"]["schemas"]
    assert [n for n, s in schemas.items() if not s.get("description")] == []
    assert [f"{n}.{p}" for n, s in schemas.items() for p, d in s.get("properties", {}).items()
            if not d.get("description") and "$ref" not in d] == []  # a $ref's target has the description
    assert [f"{m.upper()} {path} {q['name']}" for path, item in spec["paths"].items() for m, op in item.items()
            for q in op.get("parameters", []) if not q.get("description")] == []
    assert [f"{m.upper()} {path} {code}" for path, item in spec["paths"].items() for m, op in item.items()
            for code, r in op["responses"].items() if code != "204" and "content" not in r] == []
    assert spec["info"]["contact"] and spec["info"]["license"] and spec["tags"]
    assert spec["components"]["securitySchemes"]["HTTPBearer"]["description"]


def test_request_examples_are_valid():
    """Each request body's example in the spec is accepted by the model the route really uses."""
    from fastapi.routing import APIRoute

    schemas = app.openapi()["components"]["schemas"]
    checked = 0
    for route in app.routes:
        if isinstance(route, APIRoute) and route.body_field is not None:
            model = route.body_field.type_
            example = schemas.get(model.__name__, {}).get("example")
            if hasattr(model, "model_validate") and example is not None:
                model.model_validate(example)
                checked += 1
    assert checked >= 15


def test_no_duplicate_schema_titles():
    """APIMatic rule L663: only named schemas keep a title, and those are unique."""
    spec = app.openapi()
    titles = []

    def walk(node, in_example=False):
        if isinstance(node, dict):
            if not in_example and isinstance(node.get("title"), str):
                titles.append(node["title"])
            for key, value in node.items():
                walk(value, in_example or key in ("example", "examples"))
        elif isinstance(node, list):
            for value in node:
                walk(value, in_example)

    walk(spec["paths"])
    for schema in spec["components"]["schemas"].values():
        walk({k: v for k, v in schema.items() if k != "title"})
    assert titles == []
    named = [s["title"] for s in spec["components"]["schemas"].values() if "title" in s]
    assert len(named) == len(set(named))


def test_new_columns_reach_existing_databases():
    """Render's database predates some columns; create_schema adds them at startup."""
    from sqlalchemy import create_engine, inspect, text
    from sqlalchemy.pool import StaticPool

    from app.db import Base, create_schema

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE projects DROP COLUMN facilitator"))
    create_schema(engine)
    create_schema(engine)  # nothing left to add the second time
    assert "facilitator" in {c["name"] for c in inspect(engine).get_columns("projects")}


def test_projects_show_their_facilitator(client):
    assert all("facilitator" in p for p in client.get("/projects").json())
    assert "facilitator" in client.get("/projects/1").json()

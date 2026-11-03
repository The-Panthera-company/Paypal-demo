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


DOCUMENT = {"kind": "receipt", "file_url": "https://files.example.com/receipt.jpg"}


def test_stub_returns_spec_example(client):
    r = client.post("/projects/1/documents", json=DOCUMENT)
    assert r.status_code == 201  # the route's own status code
    assert r.headers["X-Stub"] == "document uploads"
    assert r.json() == DocumentOut.model_config["json_schema_extra"]["example"]


def test_stub_returns_501_when_examples_off(client):
    app.dependency_overrides[get_settings]().stub_examples = False
    r = client.post("/projects/1/documents", json=DOCUMENT)
    assert r.status_code == 501
    assert r.json()["detail"] == {"error": "NOT_IMPLEMENTED", "message": "Planned: document uploads"}
    assert "X-Stub" not in r.headers


def test_exported_spec_is_current():
    """Fails when routes change without re-running scripts/export_openapi.py."""
    exported = json.loads((Path(__file__).parent.parent / "openapi.json").read_text(encoding="utf-8"))
    assert exported == json.loads(json.dumps(app.openapi()))

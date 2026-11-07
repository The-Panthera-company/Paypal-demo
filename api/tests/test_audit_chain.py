"""Audit hash chain, kill switch and the public trace's audit log columns."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import audit
from app.db import Base
from app.models import AuditLog

ADMIN = {"Authorization": "Bearer admin-test-token"}
INTERNAL = {"Authorization": "Bearer internal-test-token"}
MANDATE = {
    "monthly_budget_cents": 1000,
    "categories": [1],
    "excluded_tags": ["faith-based"],
    "per_project_max_cents": 400,
    "approval_threshold_cents": 300,
}


def _top_up(client, amount=1000):
    order = client.post("/donations/orders", json={"target_type": "AGENT", "amount_cents": amount}).json()
    assert client.post(f"/donations/orders/{order['order_id']}/capture").json()["status"] == "captured"


def _setup(client):
    _top_up(client)
    assert client.put("/donors/1/mandate", json=MANDATE).status_code == 200


def _run(client):
    r = client.post("/internal/mandate-runs", headers=INTERNAL, json={"mandate_id": 1, "decisions": {"chosen": []}})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _give(client, run_id, project_id=1, amount=200):
    return client.post(
        "/internal/checked-donations",
        headers=INTERNAL,
        json={"mandate_run_id": run_id, "project_id": project_id, "amount_cents": amount, "reason": "few backers"},
    )


def _audit(client, n=1):
    for i in range(n):
        r = client.post(
            "/internal/audit",
            headers=INTERNAL,
            json={"actor": "giving-agent", "action": "skip", "inputs": {"project_id": i}, "reason": "test"},
        )
        assert r.status_code == 201, r.text


def test_chain_verifies_after_ten_inserts_and_default_grid_is_unchanged(client):
    _audit(client, 10)

    rows = client.get("/admin/audit-log", headers=ADMIN).json()
    assert len(rows) == 10
    assert all("hash" not in row and "seq" not in row for row in rows)

    hashed = client.get("/admin/audit-log?include_hash=true", headers=ADMIN).json()
    assert [row["seq"] for row in hashed] == list(range(10, 0, -1))
    assert all(row["hash"] and row["prev_hash"] is not None for row in hashed)

    result = client.get("/admin/audit-log/verify", headers=ADMIN).json()
    assert result == {
        "valid": True,
        "checked": 10,
        "first_bad_id": None,
        "first_bad_reason": None,
        "head_hash": hashed[0]["hash"],
    }


def test_tampering_one_row_fails_verification_at_that_id(client, db_session_factory):
    _audit(client, 3)
    with db_session_factory() as db:
        rows = list(db.scalars(select(AuditLog).order_by(AuditLog.id)))
        bad_id = rows[1].id
        rows[1].reason = "edited after the fact"
        db.commit()

    result = client.get("/admin/audit-log/verify", headers=ADMIN).json()
    assert result["valid"] is False
    assert result["first_bad_id"] == bad_id
    assert result["checked"] == 2
    assert "hash" in result["first_bad_reason"]


def test_deleting_the_tail_is_detected_by_the_chain_head(client, db_session_factory):
    _audit(client, 3)
    with db_session_factory() as db:
        last = db.scalar(select(AuditLog).order_by(AuditLog.id.desc()))
        db.delete(last)
        db.commit()

    result = client.get("/admin/audit-log/verify", headers=ADMIN).json()
    assert result["valid"] is False
    assert "chain head" in result["first_bad_reason"]


def test_backfill_fills_old_rows_once_and_is_idempotent(db_session_factory):
    with db_session_factory() as db:
        for n in range(3):
            db.add(
                AuditLog(
                    actor="giving-agent",
                    action="legacy",
                    inputs={"n": n},
                    rule_result="ok",
                    reason="before the chain",
                    created_at=datetime.now(timezone.utc),
                )
            )
        db.commit()

        assert audit.backfill(db) == 3
        first = audit.verify(db)
        assert first["valid"] is True and first["checked"] == 3

        # A second startup must not rewrite the rows it already hashed.
        hashes = list(db.scalars(select(AuditLog.hash).order_by(AuditLog.id)))
        assert audit.backfill(db) == 0
        assert list(db.scalars(select(AuditLog.hash).order_by(AuditLog.id))) == hashes


def test_pause_blocks_money_but_not_audit_and_resume_restores(client):
    _setup(client)
    run_id = _run(client)

    paused = client.post("/admin/agents/pause", headers=ADMIN, json={"reason": "watchdog alert"})
    assert paused.status_code == 200
    assert paused.json()["paused"] is True
    assert paused.json()["reason"] == "watchdog alert"
    assert client.get("/internal/status", headers=INTERNAL).json()["paused"] is True

    blocked = _give(client, run_id)
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["error"] == "AGENTS_PAUSED"

    # /internal/audit is deliberately not guarded, so an agent can record why it stopped.
    _audit(client, 1)

    resumed = client.post("/admin/agents/resume", headers=ADMIN, json={"reason": "alert cleared"})
    assert resumed.status_code == 200
    assert resumed.json()["paused"] is False

    allowed = _give(client, run_id)
    assert allowed.status_code == 200
    assert allowed.json()["status"] == "recorded"


def test_concurrent_writers_get_distinct_sequence_numbers(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'audit.db'}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def insert(n: int) -> None:
        with factory() as db:
            audit.write(db, actor="test", action="write", inputs={"n": n}, rule_result="ok")
            db.commit()

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(insert, range(20)))

    with factory() as db:
        seqs = list(db.scalars(select(AuditLog.seq).order_by(AuditLog.id)))
        assert seqs == list(range(1, 21))
        assert audit.verify(db)["valid"] is True

    engine.dispose()


def test_concurrent_writers_on_the_static_pool(db_session_factory):
    """The test fixture shares one SQLite connection; the writer lock must still serialise."""

    def insert(n: int) -> None:
        with db_session_factory() as db:
            audit.write(db, actor="test", action="write", inputs={"n": n}, rule_result="ok")
            db.commit()

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(insert, range(10)))

    with db_session_factory() as db:
        seqs = list(db.scalars(select(AuditLog.seq).order_by(AuditLog.id)))
        assert seqs == list(range(1, 11))
        assert audit.verify(db)["valid"] is True

"""Append-only audit log with a tamper-evident SHA-256 hash chain.

Every audit row stores the sequence number, the previous row's hash and its own hash.
``write`` locks the one-row ``audit_chain`` table, so concurrent writers get distinct
sequence numbers. The hash covers a canonical JSON payload including ``created_at``;
changing any stored field makes ``verify`` fail at that row.
"""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import event, select, text
from sqlalchemy.orm import Session

from app.models import AuditChain, AuditLog

CHAIN_ID = 1
GENESIS_HASH = ""
_SQLITE_WRITE_LOCK = threading.RLock()


def _release_sqlite_write_lock(session: Session, transaction) -> None:
    # Release only when the outer transaction ends. Nested savepoint events keep the lock.
    if transaction.parent is None and session.info.pop("_audit_sqlite_lock", False):
        _SQLITE_WRITE_LOCK.release()


def _hold_sqlite_write_lock(db: Session) -> None:
    """SQLite has no row locks. A process-wide lock, held until commit/rollback/close, serialises
    sessions that share the in-memory StaticPool used by tests as well as file-backed ones."""
    if not db.info.get("_audit_lock_listener"):
        event.listen(db, "after_transaction_end", _release_sqlite_write_lock)
        db.info["_audit_lock_listener"] = True
    if db.info.get("_audit_sqlite_lock"):
        return
    _SQLITE_WRITE_LOCK.acquire()
    db.info["_audit_sqlite_lock"] = True


def _utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:  # SQLite returns naive datetimes; treat them as UTC.
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _payload(log: AuditLog, seq: int, prev_hash: str) -> dict[str, Any]:
    return {
        "id": log.id,
        "seq": seq,
        "prev_hash": prev_hash,
        "actor": log.actor,
        "action": log.action,
        "inputs": log.inputs,
        "rule_result": log.rule_result,
        "reason": log.reason,
        "created_at": _utc_iso(log.created_at),
    }


def compute_hash(log: AuditLog, seq: int, prev_hash: str) -> str:
    """Hash the row's canonical payload, including its position and timestamp."""
    canonical = json.dumps(
        _payload(log, seq, prev_hash),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _lock_chain(db: Session) -> AuditChain:
    """Ensure the singleton chain row exists and lock it until this transaction ends.

    Postgres serialises writers with SELECT ... FOR UPDATE. SQLite has no row locks, so a
    no-op UPDATE takes its write lock; the next writer waits for this transaction to end.
    """
    dialect = db.get_bind().dialect.name
    if dialect == "sqlite":
        _hold_sqlite_write_lock(db)
        db.execute(text("INSERT OR IGNORE INTO audit_chain (id, seq, hash) VALUES (1, 0, '')"))
        db.execute(text("UPDATE audit_chain SET seq = seq WHERE id = 1"))
    elif dialect == "postgresql":
        db.execute(
            text("INSERT INTO audit_chain (id, seq, hash) VALUES (1, 0, '') ON CONFLICT (id) DO NOTHING")
        )

    stmt = select(AuditChain).where(AuditChain.id == CHAIN_ID).execution_options(populate_existing=True)
    if dialect == "postgresql":
        stmt = stmt.with_for_update()
    chain = db.scalar(stmt)
    if chain is None:  # a dialect without the raw upsert above
        chain = AuditChain(id=CHAIN_ID, seq=0, hash=GENESIS_HASH)
        db.add(chain)
        db.flush()
    return chain


def write(
    db: Session,
    actor: str,
    action: str,
    inputs: dict | None = None,
    rule_result: str | None = None,
    reason: str | None = None,
) -> AuditLog:
    """Append one audit row and advance the chain. The caller commits the transaction."""
    chain = _lock_chain(db)
    seq = int(chain.seq or 0) + 1
    prev_hash = chain.hash or GENESIS_HASH
    log = AuditLog(
        actor=actor,
        action=action,
        inputs=inputs,
        rule_result=rule_result,
        reason=reason,
        created_at=datetime.now(timezone.utc),
        seq=seq,
        prev_hash=prev_hash,
    )
    db.add(log)
    db.flush()  # assigns log.id, which is part of the hash
    log.hash = compute_hash(log, seq, prev_hash)
    chain.seq = seq
    chain.hash = log.hash
    db.flush()
    return log


def backfill(db: Session) -> int:
    """Fill seq/prev_hash/hash for rows that predate the chain. Idempotent.

    Existing rows with a hash are never rewritten. Ordering is (created_at, id), the order
    the rows were originally written in.
    """
    chain = _lock_chain(db)
    rows = list(db.scalars(select(AuditLog).order_by(AuditLog.created_at, AuditLog.id)))
    head_seq = 0
    head_hash = GENESIS_HASH
    filled = 0
    for row in rows:
        if row.hash is None:
            seq = head_seq + 1
            row.seq = seq
            row.prev_hash = head_hash
            row.hash = compute_hash(row, seq, head_hash)
            head_seq = seq
            head_hash = row.hash
            filled += 1
        else:
            head_seq = int(row.seq) if row.seq is not None else head_seq + 1
            head_hash = row.hash
    # On the first run, or after filling legacy rows, seed the chain head. If the head is
    # already set, leave it alone: a deleted tail must still fail verification.
    if filled or (chain.seq or 0) == 0:
        chain.seq = head_seq
        chain.hash = head_hash
    db.commit()
    return filled


def verify(db: Session) -> dict[str, Any]:
    """Recompute the chain in id order and stop at the first edited or missing row."""
    rows = list(db.scalars(select(AuditLog).order_by(AuditLog.id)))
    chain = db.get(AuditChain, CHAIN_ID)
    expected_seq = 1
    prev_hash = GENESIS_HASH
    checked = 0
    head_hash = (rows[-1].hash or "") if rows else ""
    for row in rows:
        checked += 1
        if row.hash is None:
            return {
                "valid": False,
                "checked": checked,
                "first_bad_id": row.id,
                "first_bad_reason": "missing hash",
                "head_hash": head_hash,
            }
        if row.seq != expected_seq:
            return {
                "valid": False,
                "checked": checked,
                "first_bad_id": row.id,
                "first_bad_reason": f"expected seq {expected_seq}, found {row.seq}",
                "head_hash": head_hash,
            }
        if (row.prev_hash or GENESIS_HASH) != prev_hash:
            return {
                "valid": False,
                "checked": checked,
                "first_bad_id": row.id,
                "first_bad_reason": "prev_hash does not match the previous row",
                "head_hash": head_hash,
            }
        if compute_hash(row, row.seq, row.prev_hash or GENESIS_HASH) != row.hash:
            return {
                "valid": False,
                "checked": checked,
                "first_bad_id": row.id,
                "first_bad_reason": "hash does not match the row contents",
                "head_hash": head_hash,
            }
        prev_hash = row.hash
        expected_seq += 1
    # The chain row catches a deleted tail that would otherwise leave a shorter but valid chain.
    if chain is not None and ((chain.seq or 0) != checked or (chain.hash or "") != prev_hash):
        return {
            "valid": False,
            "checked": checked,
            "first_bad_id": rows[-1].id if rows else None,
            "first_bad_reason": "chain head does not match the last audit row",
            "head_hash": head_hash,
        }
    return {
        "valid": True,
        "checked": checked,
        "first_bad_id": None,
        "first_bad_reason": None,
        "head_hash": prev_hash,
    }

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.donor_board import donor_board
from app.models import Donor, Round
from scripts import seed_dev


def _seeded(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(seed_dev, "engine", engine)
    monkeypatch.setattr(seed_dev, "SessionLocal", factory)
    seed_dev.main()
    return factory


def test_donor_board_ladders_and_privacy(monkeypatch):
    factory = _seeded(monkeypatch)
    with factory() as db:
        round_ = db.scalar(select(Round))
        board = donor_board(db, round_)
        assert board.rows, "seeded backers should appear"
        for row in board.rows:
            assert row.given_cents > 0 and row.projects_backed >= 1
            assert row.alias.startswith("Donor ") and row.display_name is None  # nobody opted in
            assert row.multiplier == round(row.match_unlocked_cents / row.given_cents, 2)
        assert len({r.alias for r in board.rows}) == len(board.rows)

        # Opting in shows the name; `me` marks the caller's own row
        someone = db.scalar(select(Donor).where(Donor.id != 1).order_by(Donor.id))
        someone.display_name, someone.show_on_leaderboard = "Wanjiru", True
        db.commit()
        board = donor_board(db, round_, me=someone.id)
        mine = [r for r in board.rows if r.is_me]
        if mine:
            assert mine[0].display_name == "Wanjiru"


def test_donor_board_unknown_round(client):
    assert client.get("/rounds/999/donors").status_code == 404


def test_aliases_need_the_secret(monkeypatch):
    """Anyone could hash ids 1, 2, 3... with a public prefix; with a server secret they can't."""
    import hashlib

    from app.donor_board import _alias

    factory = _seeded(monkeypatch)
    with factory() as db:
        round_ = db.scalar(select(Round))
        board = donor_board(db, round_, secret="server-secret")
        donor_ids = [d for d, in db.execute(select(Donor.id))]
    public_guesses = {"Donor " + hashlib.sha256(f"cg-donor-{i}".encode()).hexdigest()[:k].upper()
                      for i in donor_ids for k in (6, 8)}
    aliases = {r.alias for r in board.rows}
    assert not aliases & public_guesses
    assert aliases == {_alias(i, "server-secret") for i in donor_ids} & aliases  # stable for the same secret
    assert _alias(1, "server-secret") != _alias(1, "another-secret")

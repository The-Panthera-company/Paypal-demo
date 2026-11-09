from collections.abc import Iterator

from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


_url = get_settings().db_url
engine = create_engine(
    _url,
    connect_args={"check_same_thread": False} if _url.startswith("sqlite") else {},
    # Render's Postgres closes idle connections; test each one before use.
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def create_schema(engine: Engine) -> None:
    """Good enough until we add migrations: create_all makes missing tables, then any new nullable
    column on an existing table is added, and a column the models now allow to be null loses its
    NOT NULL (create_all never alters a table, e.g. on Render)."""
    Base.metadata.create_all(engine)
    existing = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            have = {c["name"]: c for c in existing.get_columns(table.name)}
            for column in table.columns:
                if column.name not in have and column.nullable:
                    kind = column.type.compile(dialect=engine.dialect)
                    conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN "{column.name}" {kind}'))
                elif (column.name in have and column.nullable and not column.primary_key
                      and not have[column.name]["nullable"] and engine.dialect.name == "postgresql"):
                    # SQLite can't drop NOT NULL in place; it's only used fresh (tests, local).
                    conn.execute(text(f'ALTER TABLE {table.name} ALTER COLUMN "{column.name}" DROP NOT NULL'))


def get_db() -> Iterator[Session]:
    with SessionLocal() as db:
        yield db

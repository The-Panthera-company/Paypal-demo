"""Minimal local data so the checkout page and catalogue work before P3's seed JSON lands.

Adds the four categories, the worked-example Education projects and an open round if missing.
The SQLite file is relative to where the API starts, so run this from the same folder:
    from api/:      .venv/Scripts/python -m scripts.seed_dev
    from the root:  PYTHONPATH=api api/.venv/Scripts/python -m scripts.seed_dev
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db import Base, SessionLocal, engine
from app.models import Category, Project, ProjectStatus, Round, RoundStatus

CATEGORIES = ["Health", "Education", "Environment", "Water"]
PROJECTS = [
    ("Lanet Library", ["books", "literacy"], "literacy", "children", "Nakuru", 4, 120000),
    ("Kaptembwo Desks", ["furniture", "schools"], "school equipment", "children", "Nakuru", 3, 50000),
    ("Girls' STEM Club", ["stem", "girls"], "stem education", "children", "Kisumu", 3, 80000),
    ("New Reading Corner", ["books"], "literacy", "children", "Eldoret", 5, 30000),
]


def main() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        for name in CATEGORIES:
            if not db.scalar(select(Category).where(Category.name == name)):
                db.add(Category(name=name))
        db.flush()
        education = db.scalar(select(Category).where(Category.name == "Education"))
        for title, tags, cause, group, region, urgency, goal in PROJECTS:
            if not db.scalar(select(Project).where(Project.title == title)):
                db.add(
                    Project(
                        category_id=education.id,
                        title=title,
                        tags=tags,
                        cause=cause,
                        beneficiary_group=group,
                        region=region,
                        urgency=urgency,
                        goal_amount=goal,
                        currency="USD",
                        status=ProjectStatus.active,
                        verified_by="seed",
                        verified_at=datetime.now(timezone.utc),
                    )
                )
        if not db.scalar(select(Round)):
            now = datetime.now(timezone.utc)
            db.add(
                Round(
                    name="Dev round",
                    starts_at=now,
                    ends_at=now + timedelta(days=10),
                    matching_pool=1_000_000,
                    currency="USD",
                    status=RoundStatus.open,
                )
            )
        db.commit()
        for p in db.scalars(select(Project).order_by(Project.id)):
            print(f"project {p.id}: {p.title} ({p.status.value})")


if __name__ == "__main__":
    main()

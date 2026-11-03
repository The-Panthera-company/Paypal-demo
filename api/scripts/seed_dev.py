"""Demo data so the website, leaderboard and agents have something real to show.

Safe to run again: everything is added only if missing, and the worked-example settings are
re-applied. Adds:
- the four categories, with two or more tagged projects in each (filters, exclusions and the chat)
- the System Design worked example in Education: the four projects with goals big enough that
  the 40% category cap binds, and their seeded backers (16 x 12.50, 9 x 12.50, 4 x 50 USD), so the
  leaderboard shows Lanet Library capped and its excess shared out
- a first milestone for Lanet Library (to try a payout)
- a demo donor for the Giving Agent page (there is no route that creates donors), id 1 on a fresh database
- an open round: 10,000 USD pool, 40% cap

Seeded backers are database rows, not PayPal payments; reconciliation only counts PayPal money.

The SQLite file is relative to where the API starts, so run this from the same folder:
    from api/:      .venv/Scripts/python -m scripts.seed_dev
    from the root:  PYTHONPATH=api api/.venv/Scripts/python -m scripts.seed_dev
Against Render: set DATABASE_URL to the External Database URL for that one command.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db import Base, SessionLocal, engine
from app.models import (
    Category,
    Donation,
    DonationStatus,
    Donor,
    Milestone,
    Project,
    ProjectStatus,
    Round,
    RoundStatus,
    TargetType,
)

# (category, title, tags, cause, beneficiary group, region, urgency, goal cents, summary)
PROJECTS = [
    # The worked example: goals leave room above each project's share, so only the 40% cap binds.
    ("Education", "Lanet Library", ["books", "literacy"], "literacy", "children", "Nakuru", 4, 600_000,
     "A lending library for three primary schools in Lanet: shelves, 400 books and a part-time librarian."),
    ("Education", "Kaptembwo Desks", ["furniture", "schools"], "school equipment", "children", "Nakuru", 3, 400_000,
     "Forty double desks for Kaptembwo Primary, where pupils share benches or sit on the floor."),
    ("Education", "Girls' STEM Club", ["stem", "girls"], "stem education", "youth", "Kisumu", 3, 300_000,
     "Weekly science and coding sessions for 30 secondary-school girls, with kits and a mentor."),
    ("Education", "New Reading Corner", ["books"], "literacy", "children", "Eldoret", 5, 150_000,
     "A reading corner with mats, shelves and 150 picture books for an Eldoret nursery school."),
    ("Health", "Mobile Eye Clinic", ["eye-care", "screening"], "primary care", "elderly", "Turkana", 4, 500_000,
     "Monthly eye screening and free reading glasses in four Turkana villages."),
    ("Health", "St. Mary's Mission Maternity Ward", ["faith-based", "maternal-health"], "maternal care", "adults",
     "Kisumu", 3, 450_000, "Two delivery beds and a solar fridge for a faith-run maternity ward."),
    ("Health", "Lupus Patient Support Fund", ["rare-disease", "medicine"], "rare diseases", "adults", "Nairobi", 2,
     800_000, "Medicine and transport to specialist clinics for 25 people living with lupus."),
    ("Environment", "Lake Shoreline Trees", ["trees", "climate"], "conservation", "community", "Kisumu", 3, 500_000,
     "Planting 2,000 indigenous trees along Lake Victoria's eroding shoreline, with local youth groups."),
    ("Environment", "Plastic-Free Market", ["recycling", "waste"], "waste", "community", "Mombasa", 2, 250_000,
     "Collection points and reusable bags for Kongowea market's traders."),
    ("Water", "Village Borehole Repair", ["water", "infrastructure"], "clean water", "community", "Turkana", 5, 350_000,
     "Repairing a broken borehole pump that served 600 people, and training two local mechanics."),
    ("Water", "School Rainwater Tanks", ["water", "schools"], "clean water", "children", "Eldoret", 3, 200_000,
     "Two 10,000-litre rain tanks and gutters so pupils have water at school all year."),
]

# The worked example's backers: (project, people, cents each), one seeded person per gift. Half the design's
# 25 / 25 / 100 so every gift is within the 50 USD per-person cap; the scores keep the design's 6000:1800:1200.
BACKERS = [("Lanet Library", 16, 1250), ("Kaptembwo Desks", 9, 1250), ("Girls' STEM Club", 4, 5000)]
SEED_BACKER = "Seed backer"


def main() -> None:
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        categories = {}
        for name in ("Health", "Education", "Environment", "Water"):
            categories[name] = db.scalar(select(Category).where(Category.name == name)) or Category(name=name)
            db.add(categories[name])
        db.flush()

        for category, title, tags, cause, group, region, urgency, goal, summary in PROJECTS:
            project = db.scalar(select(Project).where(Project.title == title))
            if project is None:
                project = Project(
                    title=title, currency="USD", status=ProjectStatus.active,
                    verified_by="seed", verified_at=now,
                )
                db.add(project)
            project.category_id = categories[category].id
            project.tags, project.cause, project.beneficiary_group = tags, cause, group
            project.region, project.urgency, project.goal_amount = region, urgency, goal
            project.summary = project.summary or summary
        db.flush()

        library = db.scalar(select(Project).where(Project.title == "Lanet Library"))
        if not db.scalar(select(Milestone).where(Milestone.project_id == library.id)):
            db.add(Milestone(project_id=library.id, seq=1, title="Buy 40 books", amount=3000, currency="USD"))

        round_ = db.scalar(select(Round).where(Round.status == RoundStatus.open))
        if round_ is None:
            round_ = Round(
                name="Dev round", starts_at=now - timedelta(hours=1), ends_at=now + timedelta(days=10),
                matching_pool=1_000_000, currency="USD", status=RoundStatus.open,
            )
            db.add(round_)
        round_.project_cap_pct = 40.0

        demo = db.scalar(select(Donor).order_by(Donor.id))
        if demo is None:
            demo = Donor(display_name="Demo donor", show_on_leaderboard=True)
            db.add(demo)

        if not db.scalar(select(Donor).where(Donor.display_name.like(f"{SEED_BACKER} %"))):
            n = 0
            for title, people, cents in BACKERS:
                project = db.scalar(select(Project).where(Project.title == title))
                for _ in range(people):
                    n += 1
                    backer = Donor(display_name=f"{SEED_BACKER} {n}")
                    db.add(backer)
                    db.flush()
                    db.add(Donation(
                        donor_id=backer.id, target_type=TargetType.PROJECT, project_id=project.id,
                        amount=cents, currency="USD", status=DonationStatus.captured, captured_at=now,
                    ))
        db.commit()

        for p in db.scalars(select(Project).order_by(Project.category_id, Project.id)):
            print(f"project {p.id}: {p.title} [{next(c for c, v in categories.items() if v.id == p.category_id)}]")
        print(f"round {round_.id}: {round_.name}, cap {round_.project_cap_pct}%, pool {round_.matching_pool} cents")
        print(f"demo donor: id {demo.id}")


if __name__ == "__main__":
    main()

"""Demo data so the website, leaderboard and agents have something real to show.

Safe to run again: everything is added only if missing, and the worked-example settings are
re-applied. Adds:
- the four categories, with two or more tagged projects in each (filters, exclusions and the chat)
- the System Design worked example in Education: the four projects with goals big enough that
  the 40% category cap binds, and their seeded backers (16 x 12.50, 9 x 12.50, 4 x 50 USD), so the
  leaderboard shows Lanet Library capped and its excess shared out
- 3 or 4 dated milestones per project (the timeline and the admin's held tranches): Lanet Library's
  first, a 30 USD tranche, stays open to try a real payout; Kaptembwo Desks and Girls' STEM Club
  each have a released tranche (a story on the website), Girls' STEM Club one with evidence being
  checked, Kaptembwo Desks one held for an admin. Released tranches are booked like a real release
  but paid in the database only: their payout batch stays PENDING under a SEED- batch id, so nothing
  goes to PayPal and reconciliation stays clean (there is no PayPal money behind seeded backers).
- a demo donor for the Giving Agent page (there is no route that creates donors), id 1 on a fresh database
- an open round: 10,000 USD pool, 40% cap

Seeded backers are database rows, not PayPal payments; reconciliation only counts PayPal money.

The SQLite file is relative to where the API starts, so run this from the same folder:
    from api/:      .venv/Scripts/python -m scripts.seed_dev
    from the root:  PYTHONPATH=api api/.venv/Scripts/python -m scripts.seed_dev
Against Render: set DATABASE_URL to the External Database URL for that one command.
"""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Base, SessionLocal, engine
from app.models import (
    AuditLog,
    Category,
    Donation,
    DonationStatus,
    Donor,
    DocumentKind,
    LedgerEntry,
    LedgerType,
    Milestone,
    MilestoneStatus,
    Payout,
    PayoutStatus,
    Project,
    ProjectDocument,
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

# project: [(title, cents, due in days from today, status)], in order; each project's tranches add up to its goal.
# Released tranches stay within what the seeded backers gave.
OPEN, EVIDENCE, HELD, RELEASED = (MilestoneStatus.open, MilestoneStatus.evidence_submitted,
                                  MilestoneStatus.held, MilestoneStatus.released)
MILESTONES = {
    "Lanet Library": [("Buy 40 books", 3000, 7, OPEN), ("Shelves for three schools", 197_000, 30, OPEN),
                      ("Librarian, first term", 200_000, 60, OPEN), ("300 more books", 200_000, 90, OPEN)],
    "Kaptembwo Desks": [("First 10 desks delivered", 10_000, -25, RELEASED), ("Next 15 desks", 150_000, -3, HELD),
                        ("Final 15 desks", 240_000, 40, OPEN)],
    "Girls' STEM Club": [("Science kits for 30 girls", 15_000, -30, RELEASED), ("Two coding laptops", 120_000, -2, EVIDENCE),
                         ("Mentor stipend, term one", 90_000, 35, OPEN), ("End-of-year science fair", 75_000, 80, OPEN)],
    "New Reading Corner": [("Mats and shelves", 50_000, 14, OPEN), ("150 picture books", 70_000, 40, OPEN),
                           ("Storytime volunteer training", 30_000, 70, OPEN)],
    "Mobile Eye Clinic": [("Screening kit and trial lenses", 150_000, 21, OPEN), ("First two village visits", 150_000, 50, OPEN),
                          ("Reading glasses for 400 people", 200_000, 85, OPEN)],
    "St. Mary's Mission Maternity Ward": [("Two delivery beds", 180_000, 25, OPEN), ("Solar fridge for vaccines", 270_000, 60, OPEN)],
    "Lupus Patient Support Fund": [("First quarter of medicine", 300_000, 20, OPEN), ("Clinic transport for 25 people", 200_000, 45, OPEN),
                                   ("Second quarter of medicine", 300_000, 110, OPEN)],
    "Lake Shoreline Trees": [("Seedlings and nursery beds", 150_000, 18, OPEN), ("Plant the first 1,000 trees", 200_000, 50, OPEN),
                             ("Plant 1,000 more and fence them", 150_000, 95, OPEN)],
    "Plastic-Free Market": [("Four collection points", 100_000, 15, OPEN), ("2,000 reusable bags", 100_000, 40, OPEN),
                            ("Trader workshops", 50_000, 70, OPEN)],
    "Village Borehole Repair": [("New pump and parts", 200_000, 10, OPEN), ("Install and test the water", 100_000, 30, OPEN),
                                ("Train two local mechanics", 50_000, 60, OPEN)],
    "School Rainwater Tanks": [("First 10,000-litre tank", 90_000, 20, OPEN), ("Second tank", 90_000, 45, OPEN),
                               ("Gutters and taps", 20_000, 60, OPEN)],
}
EVIDENCE_URL = "https://files.example.com/seed/milestone-{id}-{kind}.jpg"
SEED_PAYEE = "seed-payee@example.com"


def seed_milestones(db: Session, project: Project, today: date) -> None:
    """Adds the project's missing milestones; an existing one only gets a due date if it has none."""
    for seq, (title, cents, due_in, status) in enumerate(MILESTONES.get(project.title, []), start=1):
        due = today + timedelta(days=due_in)
        milestone = db.scalar(select(Milestone).where(Milestone.project_id == project.id, Milestone.seq == seq))
        if milestone is not None:
            milestone.due_date = milestone.due_date or due
            continue
        milestone = Milestone(project_id=project.id, seq=seq, title=title, amount=cents, currency="USD",
                              due_date=due, status=status)
        db.add(milestone)
        db.flush()
        if status == OPEN:
            continue

        kinds = [DocumentKind.receipt, DocumentKind.photo] if status == RELEASED else [DocumentKind.receipt]
        for kind in kinds:
            db.add(ProjectDocument(project_id=project.id, milestone_id=milestone.id, kind=kind,
                                   file_url=EVIDENCE_URL.format(id=milestone.id, kind=kind.value)))
        if status == HELD:
            db.add(AuditLog(
                actor="milestone-agent", action="payout_request",
                inputs={"milestone_id": milestone.id, "amount_cents": cents},
                rule_result="held_for_admin",
                reason=f"Held: above_threshold ({cents} > 50000). Summary: delivery note for 15 desks matches the receipt.",
            ))
        if status == RELEASED:
            released_at = datetime.combine(due, datetime.min.time(), timezone.utc)
            db.add(LedgerEntry(type=LedgerType.tranche, amount=cents, currency="USD", project_id=project.id,
                               created_at=released_at))
            db.add(Payout(
                sender_batch_id=f"seed-milestone-{milestone.id}-USD", currency="USD", status=PayoutStatus.processing,
                paypal_batch_id=f"SEED-{milestone.id}", created_at=released_at,
                items=[{"project_id": project.id, "milestone_id": milestone.id, "amount_cents": cents,
                        "receiver": SEED_PAYEE, "status": "PENDING", "sender_item_id": f"milestone-{milestone.id}"}],
            ))


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

        for project in db.scalars(select(Project).where(Project.title.in_(list(MILESTONES)))):
            seed_milestones(db, project, now.date())

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

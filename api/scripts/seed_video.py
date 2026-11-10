"""Demo data for recording the hackathon video: the platform as if it were in active use.

Runs seed_dev first, then adds projects tied to the disasters shown in the video's opening
(Nepal flash floods, Kenya's Nyando floods, the Venezuela earthquakes, Sudan, Cox's Bazar), a
November relief round, several hundred donors with small gifts spread over the last nine days,
sponsors in the matching pool, released milestones with receipts, and Giving Agent runs.

All organisations, people and amounts are made up for the demo; the incidents are the only real
part. Every payment row is a database row, not a PayPal payment. Do not run this against the
shared Render database: it is for a local copy used to take screenshots.

    from api/:  PYTHONPATH=. python -m scripts.seed_video
"""

import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.db import SessionLocal
from app.demo import DEMO_MANDATE_ID
from app.models import (
    Donation, DonationStatus, Donor, MandateRun, PoolContribution, Project, Round, RoundStatus, TargetType,
)
from scripts import seed_dev as base

O, E, H, R = base.OPEN, base.EVIDENCE, base.HELD, base.RELEASED

# (category, title, tags, cause, group, region, urgency, goal cents, summary, facilitator, milestones)
INCIDENT_PROJECTS = [
    ("Water", "Bhote Koshi Clean Water Filters", ["flood-relief", "water", "nepal"], "clean water", "community",
     "Sindhupalchok, Nepal", 5, 1_200_000,
     "Household water filters and repaired water points for families cut off by the Bhote Koshi flash flood.",
     "Sindhupalchok Women's Water Group",
     [("200 household filters", 150_000, -6, R), ("Repair 12 water points", 600_000, -1, E), ("Hygiene training", 450_000, 30, O)]),
    ("Environment", "Tatopani Temporary Footbridge", ["flood-relief", "infrastructure", "nepal"], "access", "community",
     "Sindhupalchok, Nepal", 5, 1_400_000,
     "A steel footbridge to reconnect villages after the flood swept the crossing away.",
     "Tatopani Bridge Builders Cooperative",
     [("Survey and anchors", 120_000, -4, R), ("Steel cables and decking", 880_000, 20, O), ("Handrails and opening", 400_000, 45, O)]),
    ("Health", "Sindhupalchok Mobile Flood Clinic", ["flood-relief", "clinic", "nepal"], "primary care", "community",
     "Sindhupalchok, Nepal", 5, 1_500_000,
     "A clinic team walking to villages the road no longer reaches: wound care, medicines and check-ups.",
     "Upper Bhote Koshi Health Volunteers",
     [("First month of medicines", 180_000, -8, R), ("Second month and porters", 670_000, 15, O), ("Follow-up visits", 650_000, 50, O)]),
    ("Health", "Nyando Flood Medical Outreach", ["flood-relief", "clinic", "kenya"], "primary care", "families",
     "Kisumu, Kenya", 4, 600_000,
     "Health volunteers reaching families cut off when the Nyando burst its banks and closed the Kisumu-Kericho road.",
     "Nyando Community Health Volunteers",
     [("Malaria and cholera kits", 90_000, -5, R), ("Boat transport for volunteers", 310_000, 12, O), ("Follow-up clinics", 200_000, 40, O)]),
    ("Education", "Back to School after the Nyando Floods", ["flood-relief", "schools", "kenya"], "school equipment", "children",
     "Ahero, Kenya", 4, 400_000,
     "Uniforms, books and repaired desks so 300 children can return to class after the floods.",
     "Ahero Parents Association",
     [("Books and uniforms", 60_000, -3, R), ("Desk repairs", 340_000, 25, O)]),
    ("Health", "Lara Earthquake First Aid Posts", ["earthquake", "first-aid", "venezuela"], "emergency care", "community",
     "Lara, Venezuela", 5, 800_000,
     "Neighbourhood first-aid posts and stretchers after the earthquakes damaged homes and the local clinic.",
     "Lara Barrio First Aid Collective",
     [("Five first-aid posts", 100_000, -2, R), ("Stretchers and training", 700_000, 30, O)]),
    ("Health", "White Nile Emergency Shelter Kits", ["shelter", "displacement", "sudan"], "emergency shelter", "families",
     "Ad Dweim, Sudan", 5, 1_000_000,
     "Tarpaulins, blankets and health kits for families at risk of losing emergency shelter.",
     "White Nile Shelter Volunteers",
     [("120 shelter kits", 180_000, -7, R), ("Health kits", 520_000, 10, E), ("Winter blankets", 300_000, 40, O)]),
    ("Water", "Cox's Bazar Flood Water Points", ["flood-relief", "water", "bangladesh"], "clean water", "families",
     "Cox's Bazar, Bangladesh", 4, 900_000,
     "Raised hand pumps and chlorine for neighbourhoods where the floods left 250,000 people affected.",
     "Teknaf Youth Water Committee",
     [("Chlorine and testing", 80_000, -9, R), ("Eight raised hand pumps", 820_000, 21, O)]),
    ("Environment", "Nyando Riverbank Replanting", ["flood-relief", "trees", "kenya"], "flood protection", "community",
     "Kisumu, Kenya", 3, 500_000,
     "Bamboo and vetiver along the Nyando banks to slow the next flood.",
     "Nyando River Youth Greens",
     [("5,000 seedlings", 150_000, 6, O), ("Planting days", 350_000, 30, O)]),
]

FIRST = ["Amina", "Brian", "Wanjiru", "Kevin", "Achieng", "Musa", "Grace", "Otieno", "Faith", "Daniel", "Sita", "Ram",
         "Priya", "Arjun", "Lucía", "Mateo", "Fatima", "Omar", "Rahim", "Nadia", "Chloe", "Liam", "Aisha", "Yusuf",
         "Mercy", "Peter", "Njeri", "Hassan", "Elena", "Tom", "Mei", "Kofi", "Zara", "Ian", "Joy", "Sam"]
LAST = "ABCDEFGHJKLMNOPRSTUW"
SPONSORS = [("Lakeside Rotary (demo)", 600_000), ("Kisumu Tech Hub (demo)", 250_000), (None, 150_000)]
DONORS = 640


def main() -> None:
    for cat, title, tags, cause, group, region, urg, goal, summary, fac, ms in INCIDENT_PROJECTS:
        if title not in base.FACILITATORS:
            base.PROJECTS.append((cat, title, tags, cause, group, region, urg, goal, summary))
            base.FACILITATORS[title] = fac
            base.MILESTONES[title] = ms
    base.main()

    rng = random.Random(11)
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        round_ = db.scalar(select(Round).where(Round.status == RoundStatus.open))
        round_.name = "November Relief Round"
        round_.starts_at = now - timedelta(days=9)
        round_.ends_at = now + timedelta(days=6)
        round_.matching_pool = 4_000_000

        if db.scalar(select(func.count()).select_from(Donor).where(Donor.display_name.like("Video donor %"))):
            print("video data already there")
            db.commit()
            return

        incident = [db.scalar(select(Project).where(Project.title == p[1])) for p in INCIDENT_PROJECTS]
        others = db.scalars(select(Project).where(Project.title.not_in([p[1] for p in INCIDENT_PROJECTS]))).all()
        weights = [9, 7, 9, 6, 4, 6, 7, 5, 3]  # Nepal and Sudan draw the most people
        amounts = [500, 500, 500, 1000, 1000, 1000, 1000, 1500, 2000, 2500, 2500, 5000]

        for n in range(1, DONORS + 1):
            named = rng.random() < 0.18
            donor = Donor(display_name=f"{rng.choice(FIRST)} {rng.choice(LAST)}." if named else f"Video donor {n}",
                          show_on_leaderboard=named, created_at=now - timedelta(days=rng.uniform(0, 9)))
            db.add(donor)
            db.flush()
            picks = set()
            for _ in range(rng.choices([1, 2, 3, 4], [50, 28, 15, 7])[0]):
                pool = incident if rng.random() < 0.8 else others
                project = rng.choices(pool, weights if pool is incident else None)[0]
                if project.id in picks or project.matching_frozen:
                    continue
                picks.add(project.id)
                at = now - timedelta(days=rng.uniform(0, 9), minutes=rng.uniform(0, 600))
                db.add(Donation(donor_id=donor.id, round_id=round_.id, target_type=TargetType.PROJECT, project_id=project.id,
                                amount=rng.choice(amounts), currency="USD", status=DonationStatus.captured,
                                created_at=at, captured_at=at))

        for name, cents in SPONSORS:
            sponsor = Donor(display_name=name or "Anonymous sponsor")
            db.add(sponsor)
            db.flush()
            gift = Donation(donor_id=sponsor.id, round_id=round_.id, target_type=TargetType.POOL, amount=cents,
                            currency="USD", status=DonationStatus.captured, captured_at=now - timedelta(days=rng.uniform(1, 8)))
            db.add(gift)
            db.flush()
            db.add(PoolContribution(donation_id=gift.id, round_id=round_.id, sponsor_name=name, added_to_pool=True))
            round_.matching_pool += cents

        # Giving Agent runs for the demo mandate (the public Agent Trace page)
        water, clinic, bridge, sudan = incident[0], incident[2], incident[1], incident[6]
        for k, (chosen, skipped, report) in enumerate([
            ([(water.id, 1000), (sudan.id, 1000), (clinic.id, 500)], [(bridge.id, "above_per_project_cap"), (others[0].id, "outside_causes")],
             "Gave 25 USD across three flood and shelter projects with few backers; held back where your per-project limit would be passed."),
            ([(clinic.id, 1000), (incident[3].id, 500)], [(others[1].id, "excluded_tag")],
             "Two health projects reaching families cut off by floods; skipped one tagged with a cause you excluded."),
        ]):
            at = now - timedelta(days=3 - 2 * k, hours=2)
            trace = [
                {"seq": 1, "step": "search", "tool": "search_projects", "status": "ok", "title": f"Read {len(chosen) + len(skipped) + 9} projects in your causes"},
                {"seq": 2, "step": "score", "tool": "score_projects", "status": "ok", "title": "Scored them: few backers, urgency, receipts on time"},
                *[{"seq": 3 + i, "step": "request_donation", "tool": "request_checked_donation", "status": "ok", "rule": "ok",
                   "title": f"Rules engine allowed {c / 100:.0f} USD"} for i, (_, c) in enumerate(chosen)],
                *[{"seq": 10 + i, "step": "skip", "status": "blocked" if r == "above_per_project_cap" else "skipped", "rule": r,
                   "title": "Left out: " + r.replace("_", " ")} for i, (_, r) in enumerate(skipped)],
                {"seq": 20, "step": "report", "tool": "record_mandate_run", "status": "ok", "title": "Wrote your report"},
            ]
            db.add(MandateRun(mandate_id=DEMO_MANDATE_ID, agent="giving-agent", run_at=at, report_text=report,
                              decisions={"trace": trace, "chosen": [{"project_id": p, "amount_cents": c} for p, c in chosen],
                                         "skipped": [{"project_id": p, "reason": r} for p, r in skipped]}))
        db.commit()
        people = db.scalar(select(func.count(func.distinct(Donation.donor_id))).where(Donation.status == DonationStatus.captured))
        total = db.scalar(select(func.sum(Donation.amount)).where(Donation.status == DonationStatus.captured))
        print(f"video data: {people} donors, {total / 100:,.0f} USD captured, pool {round_.matching_pool / 100:,.0f} USD")


if __name__ == "__main__":
    main()

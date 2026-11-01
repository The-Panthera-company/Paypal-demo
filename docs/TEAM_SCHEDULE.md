# Team Schedule & GitHub Workflow

Community Giving Platform: PayPal AI Hackathon
**Day 1 = Sun 1 Nov 2026 · Day 12 = Thu 12 Nov 2026** · all times **GMT+3 (EAT)** · weekends included
Deadline **Thu 12 Nov, 11:00 PM**. We submit by **6:00 PM**. Feature freeze **Day 10 (Tue 10 Nov), 6 PM**.

| Role | GitHub | Owns | Stack |
|---|---|---|---|
| **Person 1**: Payments & core API | @KOWITI123 | PayPal orders/webhooks/payouts, ledger, matching, mandates, round close | Python (FastAPI), PostgreSQL, Render |
| **Person 2**: Product & frontend | @Btsolo | Donor app, admin console, leaderboard, chat panel, demo video, slides, Devpost | Next.js, AG Grid, Render |
| **Person 3**: AI agents & data | @Kalukwo | Giving / Milestone / Watchdog / Discovery agents, seed data, Elastic, fraud scenario | Python, PayPal Agent Toolkit, Elastic, Astropods |

---

## 1. Daily rhythm

| Time (EAT) | Activity |
|---|---|
| 9:00 – 9:15 AM | **Stand-up**: yesterday, today, blocked? Move cards on the board |
| 9:15 AM – 1:00 PM | Build block 1 |
| 2:00 – 5:00 PM | Build block 2 + tests |
| 5:00 – 6:00 PM | **Pull requests + reviews** |
| 6:00 PM | **Merge** approved PRs → auto-deploy to Render |
| 6:30 – 7:00 PM | Check the hosted URL; post handoff notes |

Demo runs: **Day 4 and Day 9, 4–6 PM**. Rule: **a handoff due on a day = merged and live by 6 PM.**

---

## 2. Whole-team schedule

| Day | Date | Person 1: Core API | Person 2: Frontend | Person 3: Agents & data | Handoff (by 6 PM) |
|---|---|---|---|---|---|
| 1 | Sun 1 Nov | FastAPI skeleton, DB schema, draft routes | Next.js skeleton, licence, screen/field list | Agent Toolkit hello-world; facet list + urgency scale | P2 → P1 screen list; P3 → P2 facets |
| 2 | Mon 2 Nov | **OpenAPI spec + Postman mock** | Types, API client, Render deploy; category pages + filters | Astropods trial; **seed projects JSON** | **P1 → P2, P3: spec + mock; P3 → P1, P2: seed JSON** |
| 3 | Tue 3 Nov | PayPal create-order + capture; webhooks + ledger | Project page, story feed, funding history | Seed documents + test donors; Elastic indices | — |
| 4 | Wed 4 Nov | Deploy API + Postgres; **live capture**; urgency field | PayPal button wired live | Load seeds into DB + reset script | **P1 → P2: live capture; P3: seeded DB.** 4 PM demo run #1 |
| 5 | Thu 5 Nov | Split preview; matching engine with tests | Checkout preview + exclusions | Giving Agent rules + tests | — |
| 6 | Fri 6 Nov | **Mandate, case, checked-donation, payout endpoints** | Interests step + mandate setup | Giving Agent end to end; **decision log** | **P1 → P2, P3: endpoints; P3 → P2: decision log** |
| 7 | Sat 7 Nov | Payouts with batch IDs | Admin console (AG Grid) | Milestone Agent; Watchdog rules | — |
| 8 | Sun 8 Nov | **Match projections** (5-min cron) | Agent log view | Watchdog on Elastic + fraud scenario | **P1 → P2: projections** |
| 9 | Mon 9 Nov | Round close | Leaderboard (AG Grid showcase) + donor report | **Discovery chat endpoint** | **P3 → P2: chat.** 4 PM demo run #2 |
| 10 | Tue 10 Nov | Reconciliation, edge cases | Chat panel, mobile, script v1 | Prompt-injection tests | **6 PM FEATURE FREEZE** |
| 11 | Wed 11 Nov | Fixes | **Video + slides + Devpost draft** | Fixes; tools list text | 4 PM rehearsal #1 |
| 12 | Thu 12 Nov | Fixes | Repo public, submit | Fixes | 12 PM rehearsal #2 · **6 PM submit** · 11 PM deadline |

Demo steps: Person 2 = 1, 7 · Person 1 = 2, 5 · Person 3 = 3, 4, 6.
**Critical path:** spec (Day 2) → live capture (Day 4) → projections (Day 8) → leaderboard (Day 9). If a critical handoff slips, say so at stand-up and cut a stretch item that day. Stretch items (Bryntum, Zapier) only if Day 9 ends on time.

---

## 3. GitHub workflow: how a task flows

```
Issue (on board) → branch → commits → pull request → review → merge to main → auto-deploy (Render)
```

- **Board:** GitHub Project "paypal demo": `Backlog → This day → In progress → In review → Done`. Issue titles carry the person and day: `[P2] Day 3 (Tue 3 Nov): ...`. Labels: `p1-api`, `p2-web`, `p3-agents`, `handoff`.
- **Folders:** `api/` (Person 1), `web/` (Person 2), `agents/` (Person 3), `docs/`.
- **Branches:** one per issue, e.g. `p2/8-category-pages`. `main` always deployable and protected (PR + 1 approval).
- **Commits:** small, reference the issue: `web: add facet filters (#8)`.
- **Pull requests:** open by 5 PM with `Closes #8`; reviewed the same day by the person who uses the work; author merges.
- **Secrets:** never in git. Render env vars; local `.env` (gitignored) + `.env.example` with names only.

### Before submission (Day 12)
- [ ] Repo **public**, licence visible in About
- [ ] README: what it is, hosted URL, demo logins, how to run locally
- [ ] No secrets in history

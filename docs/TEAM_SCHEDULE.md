# Team Schedule & GitHub Workflow

Community Giving Platform: PayPal AI Hackathon
Day 1 = Wed 28 Oct 2026 · Day 16 = Thu 12 Nov 2026 · all times **GMT+3 (EAT)**
Deadline **Thu 12 Nov, 11:00 PM**. We submit by **6:00 PM**. Feature freeze **Day 14 (Tue 10 Nov)**.

| Role | Owns | Stack |
|---|---|---|
| **P1**: Payments & core API | PayPal orders/webhooks/payouts, ledger, matching, mandates, round close | Python (FastAPI), PostgreSQL, Render |
| **P2**: Product & frontend | Donor app, admin console, leaderboard, chat panel, demo video, slides, Devpost | Next.js, AG Grid, Render |
| **P3**: AI agents & data | Giving / Milestone / Watchdog / Discovery agents, seed data, Elastic, fraud scenario | Python, PayPal Agent Toolkit, Elastic, Astropods |

---

## 1. Daily rhythm (every day, weekends included)

| Time (EAT) | Activity | Who |
|---|---|---|
| 9:00 – 9:15 AM | **Stand-up** (WhatsApp/Meet): yesterday, today, blocked? Move cards on the board | All |
| 9:15 AM – 1:00 PM | Build block 1: the day's main task | Each person |
| 1:00 – 2:00 PM | Break | |
| 2:00 – 5:00 PM | Build block 2: finish the task, write tests | Each person |
| 5:00 – 6:00 PM | **Pull requests + reviews**: open your PR, review the others' PRs | All |
| 6:00 PM | **Merge window**: approved PRs merged to `main`, auto-deploy to Render | Owner of each PR |
| 6:30 – 7:00 PM | Check the hosted URL still works; post the handoff note in the group | All |
| Evening (optional) | Catch-up / stretch work | Anyone |

Demo-run days (Day 6, Day 12): **4:00 – 6:00 PM** full demo together on the hosted URL instead of block 2's end.
Rule: **a handoff due on a day = merged and deployed by 6:00 PM that day.**

---

## 2. Whole-team schedule (day by day)

### Week 1: money flows, site is live
| Day | Date | P1: Core API | P2: Frontend | P3: Agents & data | Handoff (by 6 PM) |
|---|---|---|---|---|---|
| 1 | Wed 28 Oct | FastAPI skeleton, DB schema (14 tables), draft OpenAPI routes | Next.js skeleton, layout, MIT licence; send screen/field list | Agent Toolkit hello-world; facet list + urgency scale | P2 → P1 screen list; P3 → P2 facets |
| 2 | Thu 29 Oct | **OpenAPI spec + Postman mock** | Types from spec, API client, deploy web to Render | Astropods trial (1 day max) → decide | **P1 → P2, P3: spec + mock** |
| 3 | Fri 30 Oct | PayPal create-order + capture (sandbox) | Category pages, project list, facet filters | **Seed projects JSON** | **P3 → P1, P2: seed JSON** |
| 4 | Sat 31 Oct | Webhooks (capture completed, refund) + ledger | Project page, story feed, funding history | Seed documents + test donors | — |
| 5 | Sun 1 Nov | Deploy API + Postgres to Render; urgency field | PayPal button, success/cancel | Elastic indices + sync | — |
| 6 | Mon 2 Nov | Live capture end to end | Wire button to live API | Load seeds, reset script | **P1 → P2: live capture; P3: seeded DB.** 4 PM demo run #1 |

### Week 2: matching, agents, demo screens
| Day | Date | P1: Core API | P2: Frontend | P3: Agents & data | Handoff (by 6 PM) |
|---|---|---|---|---|---|
| 7 | Tue 3 Nov | Category split preview; matching engine (tests on worked example) | Checkout preview + exclusions | Giving Agent rules + tests | — |
| 8 | Wed 4 Nov | **Mandate + watchdog case endpoints** | Interests step + mandate setup | Giving Agent on mock | **P1 → P2: mandate + cases** |
| 9 | Thu 5 Nov | **Checked-donation + request-payout endpoints**, internal token | Admin console (AG Grid) | **Decision log**; Watchdog rules | **P1 → P3: checked endpoints; P3 → P2: decision log** |
| 10 | Fri 6 Nov | Payouts with deterministic batch IDs | Agent log view | Milestone Agent | — |
| 11 | Sat 7 Nov | **Match projections** (5-min cron) | Leaderboard (AG Grid showcase) | Watchdog on Elastic + fraud scenario | **P1 → P2: projections** |
| 12 | Sun 8 Nov | Round close | Donor report | **Discovery chat endpoint** | **P3 → P2: chat.** 4 PM demo run #2 (all 7 steps) |

### Week 3: polish, freeze, ship
| Day | Date | P1 | P2 | P3 | Team |
|---|---|---|---|---|---|
| 13 | Mon 9 Nov | Reconciliation, edge cases | Chat panel, mobile, script v1 | Prompt-injection tests | Each writes lines for own demo steps |
| 14 | Tue 10 Nov | **FREEZE**: fixes only | Slides, Devpost draft | Explanation quality | 6 PM: freeze check, every demo step works |
| 15 | Wed 11 Nov | Fixes | **Record video, upload to YouTube** | Fixes | 4 PM rehearsal #1 |
| 16 | Thu 12 Nov | Fixes | Repo public, submit | Tools list text | 12 PM rehearsal #2 · **6 PM submit** · 11 PM hard deadline |

Demo steps: P2 = 1, 7 · P1 = 2, 5 · P3 = 3, 4, 6.

**Critical path:** spec (Day 2) → live capture (Day 6) → projections (Day 11) → leaderboard → demo. If a critical handoff slips, say so at the next stand-up and cut a stretch item that day.

---

## 3. GitHub workflow: how a task flows

```
Issue (on board) → branch → commits → pull request → review → merge to main → auto-deploy (Render)
```

### Board
GitHub **Projects** board on this repo with columns:
`Backlog → This day → In progress → In review → Done`
- One **issue per task** in the schedule above, titled `[P2] Day 3: Category pages + facet filters`.
- Labels: `p1-api`, `p2-web`, `p3-agents`, `handoff`, `blocker`, `bug`, `stretch`.
- Milestones: `Week 1`, `Week 2`, `Week 3`.
- Handoff issues (label `handoff`) are assigned to the giver and mention the receiver.

### Folders (monorepo)
```
api/      P1: FastAPI
web/      P2: Next.js
agents/   P3: agents, rules, seed data
docs/     design docs, schedule
```
Each person mostly edits their own folder → few merge conflicts.

### Branches
- `main` is always deployable; Render deploys it automatically.
- One branch per issue: `p1/12-paypal-capture`, `p2/7-category-pages`, `p3/5-seed-json`.
- Protect `main`: pull request required, 1 approval, no force-push.

### Commits
Small and clear: `web: add facet filters to project list (#7)`. Reference the issue number.

### Pull requests
1. Open by **5:00 PM**, title = issue title, `Closes #7` in the description.
2. Description: what changed, how to test, screenshot for UI changes.
3. **One reviewer**, the person who consumes the work (P2 reviews P1's endpoints they will call, etc.).
4. Review **within the same day** (5–6 PM slot).
5. Merge by the author after approval → issue closes → card moves to Done.

### Secrets
Never commit keys. PayPal, LLM and Elastic keys live in Render environment variables; locally in `.env` (listed in `.gitignore`). Share an `.env.example` with names only.

### Before submission (Day 16)
- [ ] Repo **public**, licence shown in the About section
- [ ] README: what it is, hosted URL, demo logins, how to run locally
- [ ] No secrets in history

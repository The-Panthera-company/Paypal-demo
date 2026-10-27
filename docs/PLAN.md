# Community Giving Platform — Development Plan & Schedule

Sources: *System Design* (23 Oct 2026) and *Work Distribution* (26 Oct 2026).
Assumed calendar: Week 1 = Mon 26 Oct – Fri 30 Oct, Week 2 = 2–6 Nov, Week 3 = 9–13 Nov.
Feature freeze Wed 11 Nov. **Submission deadline is still unknown — confirm it; if it is before 13 Nov, compress Week 3.**

## 1. The goal in one paragraph

A web platform where small donors pool their power. Verified projects (Health, Education,
Environment, Water) receive PayPal donations — to a project, a category, or via a Giving Agent
acting within the donor's mandate. A sponsor matching pool is shared by **two-level quadratic
funding** (many backers beat one big backer) with a floor and caps. AI agents *read and explain*;
deterministic rules in the core API *decide* every money movement; PayPal *moves* it.
Win condition: a hosted URL running the 7-step, ~3-minute demo flawlessly.

## 2. Roles

| Person | Layer | Owns |
|---|---|---|
| 1 | Payments + core API (Spring Boot) | PayPal orders/webhooks/payouts, ledger, matching engine, mandate checks, round close |
| **2 (you)** | **Product + frontend (Next.js)** | Donor app, project portal, admin console, leaderboard, checkout preview, mandate setup, agent log view, donor report, **demo script + slides + backup video** |
| 3 | AI agents + data (TypeScript) | Giving / Milestone / Watchdog agents, document extraction, Elastic, seed data, fraud scenario |

## 3. Dependency schedule (who must deliver what, by when)

| Due | From → To | Deliverable | Blocks if late |
|---|---|---|---|
| **Tue 27 Oct EOD** | P1 → P2, P3 | OpenAPI spec + Postman mock server | All of P2's pages; P3's agent tool calls |
| **Tue 27 Oct** | P2 → P1 | Frontend's list of needed endpoints/fields (review the spec same day) | Spec gaps found late = rework |
| Wed 28 Oct | P3 → P2 | 8–10 seed projects as JSON (titles, tags, goals, photos) | Realistic pages / screenshots |
| Thu 29 Oct | P2 → all | Hosted web skeleton on Render | Friday demo run |
| **Fri 30 Oct** | P1 → P2 | Live sandbox create-order + capture endpoints | PayPal button (demo step 2) |
| Fri 30 Oct | P3 → P1, P2 | Seeded projects, documents, test donors in DB | Real data in UI |
| Fri 30 Oct | all | **Demo run #1** on hosted URL: donate 200 KES end to end | — |
| **Wed 4 Nov** | P1 → P3 | Checked-donation + request-payout endpoints | Giving & Milestone agents |
| **Wed 4 Nov** | P3 → P2 | Agent decision log endpoint (audit_log / mandate_runs) | Admin agent-log view (steps 3, 4, 6) |
| Wed 4 Nov | P1 → P2 | Mandate CRUD + watchdog case endpoints | Mandate setup, admin queue |
| **Fri 6 Nov** | P1 → P2 | Match projections endpoint | Live leaderboard (steps 2, 5) |
| Fri 6 Nov | all | **Demo run #2**: steps 1–7 rough | — |
| Mon 9 Nov | P2 → all | Demo script v1 + slide draft (each person writes their own steps' lines) | Rehearsal |
| **Wed 11 Nov** | all | **Feature freeze** | — |
| Thu 12 Nov | P2 | Backup video recorded | Stage-failure fallback |
| Fri 13 Nov | all | Two full rehearsals; submit | — |

**Critical path:** P1 spec (27 Oct) → P1 sandbox capture (30 Oct) → P1 projections (6 Nov) → P2 leaderboard → demo.
If P1 slips, everyone slips — check in with P1 daily in Week 1.

## 4. Person 2 — your build plan

Stack: Next.js (App Router) + TypeScript, AG Grid, PayPal JS SDK, deployed on Render.
Rule: build every screen against the **mock** first, switch to the real API with one env var
(`NEXT_PUBLIC_API_URL`).

### Week 1 — money flows, site is live
| Day | Task | Done when |
|---|---|---|
| Mon 26 | Repo, Next.js skeleton, layout/nav, Render deploy | Hosted URL loads |
| Tue 27 | Review P1's spec with your screen list; typed API client from OpenAPI | Client compiles against mock |
| Wed 28 | Category pages + project list (search/tag filter) | Mock projects render |
| Thu 29 | Project detail page (goal bar, backers count, milestones, documents) | Matches design |
| Fri 30 | PayPal button → create/capture via P1; success screen | Sandbox donation shows in ledger; demo run #1 |

### Week 2 — the demo screens
| Day | Task | Depends on |
|---|---|---|
| Mon 2 | Checkout preview: where category money may go + edit exclusions | Category split endpoint (mock ok) |
| Tue 3 | Mandate setup screen (budget, categories, excluded tags, per-project max, threshold) | Mandate endpoints |
| Wed 4 | Admin console: verification queue + watchdog cases (AG Grid), freeze/clear buttons | Case endpoints |
| Thu 5 | Agent log view (inputs → rule result → reason) | P3 decision log (Wed) |
| Fri 6 | Leaderboard (AG Grid, "projected", auto-refresh, capped badge, floor) | P1 projections (Fri); demo run #2 |

### Week 3 — polish and pitch
| Day | Task |
|---|---|
| Mon 9 | Donor report "where your money went"; "your 200 KES unlocked ~1,150 KES" message; script v1 |
| Tue 10 | Mobile check, empty/error/loading states, privacy (anonymous by default, opt-in leaderboard) |
| Wed 11 | **Freeze.** Slides final |
| Thu 12 | Backup video of full flow; rehearsal |
| Fri 13 | Rehearsals ×2; you present steps 1 and 7 |

Stretch (only after freeze is safe): Bryntum milestone timeline.

## 5. Decisions to settle now (first meeting)
1. Submission deadline + judging criteria.
2. Core API language (Spring Boot vs TypeScript) — affects P1 only, but decide today.
3. Names for P1/P3.
4. Demo round settings (cap %, floor %, per-person cap). The worked example uses cap 40%, floor 20%.
5. Discovery chat: MVP or stretch (recommend stretch).
6. One repo (monorepo `web/ api/ agents/`) or three — recommend monorepo for one CI and one README.

## 6. Risks for your layer
- Spec arrives late → build from the design doc's data model with local fixtures; adapt later.
- PayPal popup blocked / sandbox flaky on stage → backup video, pre-logged sandbox buyer.
- AG Grid licence: use Community edition features only unless sponsor grants Enterprise.

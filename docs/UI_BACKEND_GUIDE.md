# UI ↔ Backend Guide

What every screen and button in `web/` needs from the core API (Person 1) and the agents (Person 3).
The website already runs on sample data shaped exactly like this (`web/src/lib/types.ts`, `web/src/lib/mock-data.ts`),
so if your endpoint returns these shapes, the page works without frontend changes.

**Rules for every endpoint**
- Amounts are integers in minor units, with the currency: `{ "amount": 120000, "currency": "USD" }` = $1,200.00.
- Dates are ISO 8601 strings (`2026-11-08T12:00:00Z`).
- JSON uses camelCase field names (as below). If FastAPI models use snake_case, set `alias_generator=to_camel`.
- Errors: HTTP status + `{ "error": "code", "message": "plain words for the user" }`. The UI shows `message`.
- Agents never call PayPal for money; they call the checked endpoints (marked 🔒) with the internal token.

Legend: **P1** = Person 1 (API), **P3** = Person 3 (agents/data), 🔒 = internal token, 👤 = logged-in donor, 🛡 = admin.

---

## 1. Shared data shapes

```ts
Money        { amount: number, currency: string }
Category     { id, name, projectCount, raised: Money }
Project      { id, title, categoryId, facilitator, summary,
               facets: { cause, group, region }, tags: string[],
               goal: Money, raised: Money, backerCount, urgency: 1-5,
               status: "verified" | "active" | "frozen" | "completed",
               endsAt: ISO date }
ImpactUpdate { id, projectId, title, caption, kind: "photo" | "receipt", date, tranche?: Money, imageUrl? }
BackerStory  { id, quote, name, role, projectId }      // only with the backer's consent
Sponsor      { id, name, pool: Money }
```

Facet values (cause / group / region) and the urgency scale come from **P3's seed data**; the filters build their options from whatever values exist.

---

## 2. Screen by screen

### Home `/`
| UI element | Needs | Endpoint | Owner |
|---|---|---|---|
| Totals (raised, backers, projects) | sums over projects | `GET /projects` (UI sums) or `GET /stats` | P1 |
| Category buttons | categories | `GET /categories` | P1 |
| "Explore projects" grid (6 cards, most urgent first) | projects with urgency | `GET /projects` | P1, data P3 |
| "Latest impact" (3 tiles) + lightbox | latest updates | `GET /updates?limit=3` | P1, evidence from P3's Milestone Agent |
| "What backers are saying" | consented stories | `GET /stories` | P1 |
| Sponsor strip (matching pool) | sponsors of the current round | `GET /rounds/current/sponsors` | P1 |
| FAQ, How it works | static text | none | P2 |

### Explore `/projects`
| UI element | Needs | Endpoint | Owner |
|---|---|---|---|
| Search box | text search on title/summary | `GET /projects?q=` | P1 (Elastic: P3) |
| Filters: Category, Cause, Who it helps, Region | facet filters | `GET /projects?category=&cause=&group=&region=` | P1 / P3 |
| Result count, empty state | list length | same call | P2 |
| Project card: tag, days left, % raised, raised of goal, backers, Funded / Just launched | `Project` fields | same call | P1 |

### Project page `/projects/{id}`
| UI element | Needs | Endpoint | Owner |
|---|---|---|---|
| Title, facilitator, region, stat boxes, progress | one project | `GET /projects/{id}` | P1 |
| **Back this project** (PayPal button) | create order → donor approves → capture | `POST /donations/orders` `{ targetType: "PROJECT", projectId, amount }` → `{ orderId }`; `POST /donations/orders/{orderId}/capture` → donation | P1 |
| Impact updates timeline | updates for the project | `GET /projects/{id}/updates` | P1, written by P3's Milestone Agent |
| Similar projects | same category | `GET /projects?category=` | P1 |
| "Report it" link | open an admin case | `POST /projects/{id}/reports` `{ reason }` | P1 |
| Tabs: Documents | registration/plan files | `GET /projects/{id}/documents` | P1, extraction by P3 |

### Impact gallery `/gallery`
| UI element | Needs | Endpoint | Owner |
|---|---|---|---|
| Evidence tiles + lightbox | all released updates with `imageUrl` | `GET /updates` | P1 / P3 |

### Category checkout preview (Day 5, #20)
| UI element | Needs | Endpoint | Owner |
|---|---|---|---|
| "Where your money may go" list | split of a category gift | `GET /categories/{id}/split-preview?amount=&excluded=&rule=` → `[{ projectId, amount }]` | P1 |
| Edit exclusions | excluded tags | same call with `excluded=` | P1 |
| Pay | as project donation, `targetType: "CATEGORY"` | `POST /donations/orders` | P1 |

### Giving Agent setup `/mandate` (Day 6, #23)
| UI element | Needs | Endpoint | Owner |
|---|---|---|---|
| Interests step (causes, groups, regions) | 👤 save interests | `GET/PUT /donors/me/interests` | P1 |
| Mandate form: budget, categories, exclusions, per-project max, approval threshold | 👤 save mandate | `GET/PUT /mandates/me` | P1 |
| "Run now" (demo) | trigger one agent run | `POST /agents/giving/run` `{ mandateId }` | P3 |
| Pending approvals (gifts above threshold) | 👤 approve / decline | `GET /donors/me/pending`, `POST /donations/{id}/approve` | P1 |

### My Impact `/report` (Day 9, #35)
| UI element | Needs | Endpoint | Owner |
|---|---|---|---|
| "Where your money went" | 👤 donations, matching unlocked, updates from backed projects | `GET /donors/me/report` | P1 |
| Agent run explanations ("$3 to Desks: 4 backers, 60% funded") | 👤 mandate runs with reasons | included in report (`mandateRuns[]`) | P3 writes the text |
| "Your $2 unlocked ~$11 of matching" | projection per donation | included in report | P1 |

### Leaderboard `/leaderboard` (Day 9, #32, AG Grid)
| UI element | Needs | Endpoint | Owner |
|---|---|---|---|
| Grid: project, backers, score, floor, crowd share, capped, projected match | current projections | `GET /rounds/current/projections` → `[{ projectId, score, floorAmount, crowdAmount, capped, finalAmount, isFinal, computedAt }]` | P1 |
| "Projected" vs "Final" badge | `isFinal`, `computedAt` | same | P1 |
| Auto-refresh every 60 s | — | same call polled | P2 |

### Discovery chat panel (Day 10, #38)
| UI element | Needs | Endpoint | Owner |
|---|---|---|---|
| Text box "What do you care about?" | free text → filters → projects + reasons | `POST /agents/discovery/chat` `{ message }` → `{ filters, projects: Project[], explanation }` | **P3** |
| Each suggestion's "Back this" | normal donate flow | as project page | P1 |
| Rule: the chat never moves money or changes scores | | | P3 |

### Admin console `/admin` (Day 7–8, #26 #29, 🛡, AG Grid)
| UI element | Needs | Endpoint | Owner |
|---|---|---|---|
| Verification queue + **Verify** / **Reject** | pending projects, extracted fields, flags | `GET /admin/projects?status=pending`, `POST /admin/projects/{id}/verify` / `reject` | P1, fields from P3's Verification helper |
| Watchdog cases + **Clear** / **Confirm** | open cases with evidence | `GET /admin/cases`, `POST /admin/cases/{id}/clear` / `confirm` | P1, cases opened by P3's Watchdog |
| Held tranches + **Release** / **Hold** | milestone checks that failed or exceed threshold | `GET /admin/tranches?status=held`, `POST /admin/tranches/{id}/release` | P1, checks by P3's Milestone Agent |
| Agent log | every agent action | `GET /admin/audit-log?actor=` → `[{ actor, action, inputs, ruleResult, reason, createdAt }]` | **P3** writes, P1 serves |
| Reports from users | project reports | `GET /admin/reports` | P1 |

---

## 3. What each agent must write so the UI can show it (Person 3)

| Agent | Writes | Shown on |
|---|---|---|
| Giving | `mandate_runs` (candidates, scores, chosen, reasons, reportText); donation requests via 🔒 `POST /internal/donations/checked` | My Impact, Agent log |
| Milestone | `ImpactUpdate` rows (title, caption, kind, imageUrl, tranche) when released; held tranches with the LLM summary; payout requests via 🔒 `POST /internal/payouts/request` | Project timeline, Gallery, Admin held tranches |
| Watchdog | `watchdog_cases` (projectId, rule, evidence, status); freeze flag on the project | Admin cases, project status `frozen` |
| Discovery | answers to `POST /agents/discovery/chat` | Chat panel |
| Verification (helper) | `project_documents.extractedFields`, `flags[]` | Admin verification queue |
| All | one `audit_log` row per action: actor, action, inputs, ruleResult, reason | Admin agent log |

**Seed data checklist (P3, Day 2–4)** so every screen has something to show:
- 8–10 projects across 4 categories with facets, urgency, goal, raised, backers, `endsAt`
- 2+ projects with 0 backers (Just launched) and 1 at 100%+ (Funded)
- 6+ impact updates with images (some receipts)
- 3 consented backer stories (fictional names are fine for the demo, marked as sample)
- 3–4 sponsors with pool amounts
- 1 pending project, 1 watchdog case, 1 held tranche for the admin demo

---

## 4. Order to deliver (matches the schedule)

1. Day 2: `GET /categories`, `GET /projects`, `GET /projects/{id}` in the spec + mock (P1); seed JSON (P3)
2. Day 4: donation order + capture live (P1); seeded DB (P3)
3. Day 6: mandates, interests, cases, 🔒 checked donation and payout (P1); agent log rows (P3)
4. Day 8: projections (P1); updates written by the Milestone Agent (P3)
5. Day 9: discovery chat (P3); donor report (P1)

Questions or a field you want to rename: comment on the issue, and Person 2 changes `types.ts` to match.

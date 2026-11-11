# Core API (P1)

FastAPI service that owns all money logic. Only this service holds PayPal credentials.

## Run locally

```bash
cd api
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # macOS/Linux: .venv/bin/python
cp .env.example .env    # fill in PayPal sandbox keys
.venv/Scripts/python -m uvicorn app.main:app --reload
```

Without `DATABASE_URL` it uses a local SQLite file (`giving.db`). Keep it unset locally: set to the Render database, your local server writes to the live data. Tests always use an in-memory database whatever `.env` says. Docs at http://localhost:8000/docs, spec at `/openapi.json`.

Demo data: `.venv/Scripts/python -m scripts.seed_dev` (safe to run again). It adds 76 tagged projects across all 4 categories, from Kenya and around the world (Palestine, Syria, Yemen, Lebanon, Iraq, Afghanistan, DR Congo, Sudanese refugees in Chad, Ethiopia, Somalia, Ukraine, Haiti, Venezuela, Bangladesh, Myanmar, the Pacific islands, the Americas and Europe, among others; Education keeps only the worked example's 4), each with its facilitator (the group running it), the System Design worked example in Education with its seeded backers, a 40% cap and 10,000 USD pool (so the leaderboard shows Lanet Library capped at 4,000 and its excess shared: 3,024 / 2,256 / 720), 2 to 4 dated milestones per project (for the timeline and the admin's held tranches: two released, on Kaptembwo Desks and Girls' STEM Club so they have stories, one with evidence being checked, one held; Lanet Library's first, 30 USD, stays open to try a payout), and a demo donor (id 1 on a fresh database) for the Giving Agent page. Seeded backers are database rows, not PayPal payments, and seeded releases are paid in the database only (their payout batches stay PENDING under a `SEED-` batch id; refreshing one from the admin console gets a PayPal error). Against Render, set `DATABASE_URL` to the External Database URL for that one command.

## API spec (for P2 and P3)

The spec is [`api/openapi.json`](openapi.json), generated from the code. After changing a route or schema:

```bash
.venv/Scripts/python -m scripts.export_openapi
```

A test fails if the file is out of date. Descriptions and examples that the models don't carry themselves live in [`app/openapi_docs.py`](app/openapi_docs.py); a test fails if a new field, schema or parameter has none, or if a request example wouldn't pass validation. Conventions:

- Money: integers in minor units in fields ending `_cents`, plus `currency` (USD).
- Errors: `{"detail": {"error": "CODE", "message": "..."}}`.
- **`X-Stub` header** = in the spec, not built yet: the route returns its spec example (fake data) so P2 and P3 can build against it. It turns real without the URL or shape changing. `STUB_EXAMPLES=false` makes these answer **501 `NOT_IMPLEMENTED`** instead.
- `/admin/*`: `Authorization: Bearer <ADMIN_TOKEN>`. `/internal/*` (agents only): `Bearer <INTERNAL_TOKEN>`. Agents never get PayPal keys.
- No donor login yet: donor routes take `donor_id`; demo logins map to donor ids.

| Area | Real now | Stubbed (example + `X-Stub`) |
|---|---|---|
| Catalogue | `GET /categories`, `GET /projects` (filters: category, cause, beneficiary group, region, `exclude_tags`, `q`, sort), `GET /projects/{id}`, `GET /projects/{id}/funding-history`, `GET /projects/{id}/stories` | project application, document upload |
| Donations | create order, capture, `GET /donations/{id}`, `POST /donations/category-preview` | |
| Donors | `GET`/`PATCH /donors/{id}`, `GET /donors/{id}/report`, mandate (`GET`/`PUT`), monthly subscription (start, status, cancel), mandate runs, pending approvals and the yes/no | |
| Rounds | `GET /rounds/current`, `GET /rounds/{id}/leaderboard` | |
| Admin | review queue, verify, payout account, cases list, resolve case, held milestones, milestone review, payouts (list, send, refresh, retry), round close, reconciliation and sweep, audit log, webhook events | |
| Internal (agents) | active mandates, mandate runs, checked donations, payout requests, Watchdog cases, audit | |
| Webhooks | `POST /webhooks/paypal` (capture completed, pending, denied, refunded, reversed) | |

### Building against it (P2, P3)

The API is its own mock: point the frontend and agents at its base URL (local `http://localhost:8000` now, the Render URL once deployed). Built routes return real data; stubbed ones return the spec example with an `X-Stub` header naming the planned task. Check for that header rather than trusting stub data.

For a ready-made request list, import `api/openapi.json` into Postman (**Import**, or Ctrl+O) and set the collection's `baseUrl` variable to the API URL.

## Deploy to Render

[`render.yaml`](../render.yaml) at the repo root describes the API and its Postgres database (both free plan).

1. Push the branch to GitHub. Render deploys from a branch, so until it's merged, deploy from that branch.
2. render.com → sign in with GitHub → **New → Blueprint** → pick `The-Panthera-company/Paypal-demo` and the branch → it reads `render.yaml`.
3. It asks for the `sync: false` values: `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET` (the same sandbox keys as `.env`), and `PAYPAL_WEBHOOK_ID` (leave empty until webhooks are built). **Apply.**
4. Wait for the build, then open `https://<service>.onrender.com/health` → `{"ok": true}`, and `/docs`.
5. Seed it from your machine: Render → `giving-db` → **Connect → External Database URL**, then from `api/`:
   ```bash
   DATABASE_URL="<external database url>" .venv/Scripts/python -m scripts.seed_dev
   ```
6. `INTERNAL_TOKEN` and `ADMIN_TOKEN` are generated by Render: copy them from the service's **Environment** tab and share privately (P3: internal, P2's admin console: admin).
7. When P2's frontend is deployed, add its URL to `CORS_ORIGINS` (comma-separated) in the **Environment** tab.

Notes: tables are created on first start. The free web service sleeps after ~15 min idle, so the first request after that takes ~1 min; open `/health` before a demo. The free database expires after 30 days, enough for the hackathon. Each push to the deployed branch redeploys.

## SDKs with APIMatic

`openapi.json` is valid OpenAPI 3.1 (50 operations, each with a unique `operationId` and a description) and lists the Render and local servers, so it can be turned into SDKs as is.

1. apimatic.io → sign in → **Import API** → upload `api/openapi.json`.
2. **Generate SDK** → Python (for P3's agents) and/or TypeScript (for the website) → download.
3. Admin and internal routes take the bearer token in the SDK's configuration (`ADMIN_TOKEN` or `INTERNAL_TOKEN`).

Regenerate after changing the API (re-export the spec first).

## Tests

```bash
.venv/Scripts/python -m pytest -q
```

Tests fake PayPal at the HTTP level; no keys or network needed.

## PayPal sandbox setup (one time)

1. developer.paypal.com → Apps & Credentials → **Sandbox** → create a REST app. Copy client ID and secret into `.env`.
2. Testing tools → Sandbox accounts: use the default **business** account (receives donations) and create 2–3 **personal** accounts (donors).
3. Postman: import `postman/paypal-sandbox.postman_collection.json`, set `paypal_client_id` / `paypal_client_secret` as collection variables (secret type; don't share filled values). Run 1 → 2, open `approve_url` (logged in the Postman console), log in as a sandbox personal account, approve, then run 3.

## Testing against the real sandbox

1. **Keys work?** From `api/`:
   ```bash
   .venv/Scripts/python -m scripts.sandbox_check
   ```
   Prints `OK` for the token and a created (never captured) order, or the PayPal error.
2. **Full flow in a browser:** start the API, open http://localhost:8000/dev/checkout (sandbox only; 404 in live), click the button and pay:
   - **PayPal button:** log in with a sandbox *personal* account (Testing tools → Sandbox accounts → View/edit for its email and password).
   - **Card button (guest):** use a test card from Testing tools → Card testing; any future expiry, any CVV.

   The page logs each API call and response. Success ends with `✅ Donation captured.`
3. **Check it landed:** the donation should be `captured` with a capture ID, and the ledger should have a `donation` and a `fee` row. Both payments also show in the sandbox business account's activity at sandbox.paypal.com.
4. **Failure cases worth trying:** close the popup (cancel), click capture twice (idempotent), and a declined card. In sandbox, PayPal fakes errors when the request carries a `PayPal-Mock-Response` header, e.g. `{"mock_application_codes": "INSTRUMENT_DECLINED"}` on the capture call. Try it from Postman.

## Category split preview

`POST /donations/category-preview` with `{"category_id", "amount_cents", "rule", "excluded_tags"}` shows where a category gift would go before the donor pays. The cents always add up to `amount_cents`.

| `rule` | How it splits |
|---|---|
| `crowd` (default) | 20% equally across the eligible projects, 80% by each project's crowd score; no scores yet → all equally |
| `equal` | Equally |
| `closest_to_goal` | Fills the project nearest its goal first, then the next; anything left once all are full is shared equally |

- Eligible = the category's verified or active projects, minus any whose tags match `excluded_tags` (case-insensitive; returned in `excluded` with the tag that matched), minus projects whose matching the Watchdog froze. None left → 422 `NO_ELIGIBLE_PROJECTS`.
- Crowd score (design Step 2): `(Σ√d)² − Σd` over people, from project donations only, captured within the open round. One PayPal payer = one person, guests count half, refunds are gone, and only a person's first 50 USD per project counts. Many small backers beat one big one; one backer alone scores 0.
- The math lives in `app/matching.py` (pure, tested against the design's worked example) so the matching engine reuses it.
- **Paying:** `POST /donations/orders` with `target_type: CATEGORY`, `category_id` and the same `rule` and `excluded_tags` the donor saw in the preview. Checkout is refused with `NO_ELIGIBLE_PROJECTS` if nothing is left. At capture the gift is split once with that rule onto the projects eligible at that moment (`category_allocations`), and each share counts toward the project's raised total, backers and funding history. A refund removes the shares. For matching, a category gift still counts at category level only (design Step 1).

## Matching engine

[`app/engine.py`](app/engine.py) shares a round's matching pool, following the System Design's Steps 0–4. `compute()` is pure (same inputs, same result, tested against the design's worked example); `run_round(db, round)` gathers the inputs and replaces that round's `match_results` rows (`is_final=False` for projections, `True` at close).

1. **Clean inputs:** captured donations inside the round's window (refunded ones are no longer captured). One PayPal payer = one person; guest cards count half; donors listed in a **confirmed** Watchdog case's `evidence.donor_ids` count as one person; only a person's first `per_person_cap` (50 USD) per project counts. Gifts to projects that aren't listed or whose matching is frozen are left out.
2. **Category pools:** by each category's score over people's whole contribution to it (project + category gifts).
3. **Project scores:** project gifts only (agent gifts count as project gifts).
4. **Floor + crowd:** `floor_pct` (20%) equally, the rest by score; nobody scored yet → all equally.
5. **Caps:** `project_cap_pct` (30%) of the category pool and the project's remaining goal; the excess goes to the others in proportion to what they have, repeated. If every project is capped, the rest stays in the pool.

Cents always add up; ties break by id.

### Projections and the leaderboard

While a round is open its projected match is recomputed every `PROJECTION_INTERVAL_SECONDS` (300) and saved as `is_final=False` rows ([`app/projections.py`](app/projections.py)). Render's free plan has no cron and sleeps when idle, so this runs two ways: a background loop inside the API while it's awake, and `GET /rounds/{id}/leaderboard` recomputing when the saved projection is older than the interval (the first read after a sleep).

- `GET /rounds/{id}/leaderboard`: projects ranked by match, with score, floor, crowd, capped, backers and raised. `is_final` is true once round close has written final rows; those always win and are never recomputed. A closed round without final rows returns no rows.
- Projects whose matching is frozen are listed with a match of 0 and `matching_frozen: true`.
- `projected_match_cents` on `GET /projects` reads the same rows.
- `GET /rounds/{id}/donors?me=`: the donor ladders ([`app/donor_board.py`](app/donor_board.py)). Names only for donors who opted in; everyone else gets an alias such as `Donor 3FA9C10B`, an HMAC of their id under `ALIAS_SECRET` (default: `ADMIN_TOKEN`), so aliases can't be traced back to ids. Changing that secret changes every alias. `me` only marks a row (there's no login yet), so anyone can pass any id.
- If the pool is bigger than what projects still need, every project hits its goal cap and the rest stays in the pool.

### Round close

[`app/round_close.py`](app/round_close.py), System Design flow 4.

- **When:** automatically, by the same background loop, once the round's `ends_at` has passed; or now with `POST /admin/rounds/{id}/close` (add `?early=true` before the end time, e.g. in the demo). Donations after `ends_at` fall outside the round's window on their own.
- **Waits for the Watchdog:** while any case is open the round sits in `closing` and the route answers 409 `WAITING_FOR_CASES`. Resolving the last case closes it straight away.
- **Then, once:** final results (`is_final=True` rows, which the leaderboard shows from then on); each project's match is added to the `match_amount` of its first unreleased milestone (a "Matching funds (<round>)" milestone is created if it has none), so it's paid out with that tranche's evidence; a `match` ledger entry per project; status `closed`. A closed round is never recomputed (409 `ROUND_CLOSED`).
- Whatever the caps left unallocated stays unspent; the audit log's `round_closed` line says how much.

### Match preview, round controls, results and sponsors

- **Match preview:** `GET /rounds/{id}/match-preview?amount_cents=500` (optional `project_id`, `donor_id`). It runs the engine on the round's live inputs with and without one more gift, and returns per project `match_before_cents`, `match_after_cents` and `match_added_cents`, the biggest effect first. Pass `donor_id` so the donor's earlier gifts count: a second gift from the same person adds less, and nothing beyond the per-person cap. 409 `ROUND_NOT_OPEN`, 404 for an unlisted or frozen project. It's an estimate: other gifts change the final match.
- **Rounds (admin):** `POST /admin/rounds` schedules one (`name`, `starts_at`, `ends_at`, `matching_pool_cents`, `project_cap_pct`, `floor_pct`, `per_person_cap_cents`). It opens on its own at `starts_at`, through the background loop or the next `GET /rounds/current`. One round runs at a time (409 `ROUND_OVERLAP`). `PATCH /admin/rounds/{id}` changes a scheduled or open round: an open round keeps its start, a closed one is final, and the pool can't drop below what sponsors added. Close with `POST /admin/rounds/{id}/close` as before.
- **Results:** `GET /rounds` lists every round, newest first. `GET /rounds/{id}/results` shows each project's last projected match next to its final match (null until close), plus the pool (including sponsors), matched, unspent, raised and backers.
- **Sponsors:** `POST /donations/orders` with `{"target_type": "POOL", "amount_cents": ..., "sponsor_name": "..."}` (name optional, up to `MAX_POOL_CONTRIBUTION_CENTS`, default 10,000 USD), then the usual capture. Once captured it raises the open round's `matching_pool` (a `pool_contributions` row records which round). It isn't a gift to a project: no backer, no ladder entry. `GET /rounds/{id}/sponsors` lists them. A full refund while the round is open takes it out of the pool again.

## Giving Agent mandates

The agent never moves money itself: it asks `POST /internal/checked-donations`, and the API re-checks the mandate every time.

- **Mandate:** `PUT /donors/{id}/mandate` sets monthly budget, categories, excluded tags, per-project max, approval threshold and optional `weight_overrides` (keys `few_backers`, `progress`, `urgency`, `evidence`, `days_since_funded`; each within 20 of its default 35/25/20/10/10).
- **The mandate contract:** `GET /mandates/constraints` (public) gives the limits, so the website and the agents don't hard-code them:
  - the default weights and how far each may move (20);
  - a budget cap of 10,000 USD a month;
  - at most 20 excluded tags of up to 40 characters;
  - a per-project max and approval threshold of at least 1 USD, and never above the monthly budget.

  Saving also needs at least one existing category. Tags are saved trimmed, lowercased and deduped. A 422 puts the first problem in `error` and `message`, and lists every problem as `errors: [{field, code, message}]` (codes such as `CATEGORIES_REQUIRED`, `THRESHOLD_OVER_BUDGET`, `PER_PROJECT_OVER_BUDGET`, `BUDGET_TOO_HIGH`, `TOO_MANY_TAGS`, `TAG_TOO_LONG`, `INVALID_WEIGHTS`).
- **Preview before saving:** `POST /donors/{id}/mandate/preview` takes the same body and runs the same rules ([`validate_mandate`](app/mandates.py)) without saving: `{ok, errors, normalized}`. Check an LLM-drafted mandate here, show the donor the result, and call PUT only when they confirm. Every save writes a `mandate_updated` audit row with the mandate before and after.
- **Funding:** the donor tops up through PayPal with `POST /donations/orders` and `{"target_type": "AGENT", "amount_cents": ...}` (no project), then the normal capture. The top-up is credited to the payer's donor record, so they must pay with the same PayPal account as the mandate's donor. `funded_balance_cents` = top-ups − gifts given − gifts waiting for approval.
- **A run:** the agent reads `GET /internal/mandates/active`, records its candidates and scores with `POST /internal/mandate-runs`, then asks for each gift with `POST /internal/checked-donations` (`mandate_run_id`, `project_id`, `amount_cents`, `reason`).
- **The checks, in order** (`rule_result` names the one that blocked): `mandate_inactive`, `project_not_open`, `project_frozen` (Watchdog), `category_not_in_mandate`, `excluded_tag`, `over_per_project_max` (this calendar month), `over_monthly_budget` (this calendar month), `insufficient_balance`.
- **Outcome:** passes and at most the approval threshold → `recorded`: a captured AGENT donation for that donor, counting for matching like any project gift, with no PayPal call. Above the threshold → `awaiting_donor_approval`; the donor sees it in `GET /donors/{id}/pending-approvals` and answers `POST /donors/{id}/pending-approvals/{donation_id}` `{"approve": true|false}`. A yes re-checks the mandate first (409 with the rule if it no longer fits).
- Asking twice for the same run and project returns the first answer (`rule_result: duplicate`), so agent retries are safe. Every request is in the audit log with the agent's reason.

Ledger note for reconciliation: a top-up is a `donation` entry with no project; each agent gift is another `donation` entry with its project. The same money appears twice, so count top-ups (AGENT, no project) as budget, not as giving.

### Monthly budget through PayPal Subscriptions

Instead of one-off top-ups, a donor can fund the agent monthly ([`app/subscriptions.py`](app/subscriptions.py)).

- `POST /donors/{id}/mandate/subscription` `{"monthly_amount_cents": 2500}` (whole dollars) → `subscription_id` and `approve_url`. With the JS SDK (`vault=true&intent=subscription`), return `subscription_id` from `createSubscription`; or send the donor to `approve_url`. PayPal sends them back to `WEB_URL/mandate?subscription=approved` (or `=cancelled`).
- One PayPal plan per currency at 1.00 a month with quantity allowed: 25 USD a month is quantity 25. Created on first use and stored in `paypal_plans`.
- Each monthly charge arrives as `PAYMENT.SALE.COMPLETED` and is credited to the funded balance once (keyed by the sale id), with its ledger and fee entries. `BILLING.SUBSCRIPTION.*` webhooks keep `status` current (`APPROVAL_PENDING`, `ACTIVE`, `SUSPENDED`, `CANCELLED`, `EXPIRED`).
- `GET /donors/{id}/mandate/subscription`; `POST /donors/{id}/mandate/subscription/cancel` stops future charges (money already credited stays). One active subscription per donor.
- **PayPal dashboard:** add these to the webhook's events: *Payment sale completed*, *Billing subscription activated*, *re-activated*, *suspended*, *cancelled*, *expired* and *payment failed*. Render: set `WEB_URL` to the website's URL.

### MCP tools for the agents

[`mcp-server/`](../mcp-server/README.md) wraps the `/internal/*` routes (and the project and leaderboard reads) as MCP tools for P3's agents. Each tool is one call to this API with the internal token, so every rule is still checked here.

## Watchdog cases

- `POST /internal/watchdog/cases` (`project_id`, `rule`, `evidence`): opens a case and sets the project's `matching_frozen` (donations still work). The same rule on a project with an open case returns that case. Put the suspected donors in `evidence.donor_ids` as internal `Donor.id` integers, never PayPal payer ids. `rule=collusion_cluster` also accepts an optional `evidence.graph` with nodes (`id`, `type`, `label`) and edges (`source`, `target`, `weight`); unknown or non-integer donor ids answer 422.
- `GET /internal/donation-events?since=<iso>&limit=500`: the Watchdog's feed of captured and refunded donations, newest first. It returns internal donor ids (`donor_id`, `owner_donor_id`) and the donor's creation time; PayPal payer ids never appear.
- `POST /admin/cases/{id}/resolve` with `action`:
  - `clear`: false alarm; matching resumes once no other case is open for the project.
  - `confirm`: those `donor_ids` count as one person in matching from now on; matching resumes the same way.
  - `confirm` + `remove_project: true`: the project is delisted (`frozen`) and its matching stays frozen. Refunds aren't automatic: refund its donations in the PayPal sandbox and the refund webhooks update totals and matching.

## Milestone tranches

- `POST /internal/payout-requests` (`milestone_id`, the four `checks`, `summary`): released when every check passes, the project has no open Watchdog case, and the tranche plus its match is at most `MILESTONE_AUTO_RELEASE_CENTS` (50,000). Otherwise `held_for_admin` with the reasons; the agent's summary is in the audit log.
- Admin: `GET /admin/milestones/held`, then `POST /admin/milestones/{id}/review` `{"approve": true}` releases it, `false` sends it back to `open` for new evidence.
- Released = milestone `released`, a `tranche` ledger entry (amount + match), and a PayPal payout (next section).
- `POST /admin/projects/{id}/verify` `{"approve": true}` lists a project under review (`verified`); `false` sends it back to `draft`.

### Applications and evidence

- `POST /projects`: a project owner applies with its details, `facilitator`, a `milestones` plan (title, `amount_cents`, `due_date`; the amounts add up to `goal_cents`) and an optional `payout_email`. The project starts `pending_review` (not public). The answer includes an `owner_token`, shown once.
- `POST /projects/{id}/documents` with header `X-Project-Token: <owner_token>`: a registration, plan, receipt or photo, as an https link to the hosted file. A receipt or photo with a `milestone_id` is evidence: the tranche moves to `evidence_submitted` (409 if it's held or released).
- The Milestone Agent reads `GET /internal/milestones/evidence` (tranches with evidence and their documents), then calls `POST /internal/payout-requests` as above.
- Admin: `GET /admin/projects/{id}/documents` for verification; `POST /admin/projects/{id}/owner-token` issues a new token (lost token, or seeded projects, which have none).

### Managed procurement

The other way to release a tranche ([`app/procurement.py`](app/procurement.py)): instead of paying the project and checking its receipts afterwards, the platform buys the goods and PayPal Payouts pays the supplier directly.

1. **Owner asks:** `POST /projects/{id}/procurement-requests` with `X-Project-Token`, body `milestone_id`, `description`, `quantity`, `max_amount_cents`. The milestone must be `open` or `evidence_submitted`, the budget at most the tranche (amount + match), and the milestone must have no other active request. Status `requested`.
2. **Procurement Agent reads:** `GET /internal/procurement/requests` (requested and proposed, with project, milestone, goal, tags and region). `GET /internal/procurement/suppliers?project_id=` lists active suppliers whose region fits and whose categories or tags match the project's. It returns id, name, categories, tags, region, `unit_amount_cents` (the usual price for one unit) and `reliability` (0 to 100), never the PayPal email. Price and reliability are null when unknown.
3. **Agent proposes:** first `POST /internal/procurement/runs` with `decisions` (its `trace`) and `report_text` records the run. Its trace is public at `GET /agents/runs/{id}`, so keep supplier emails out of it. Then `POST /internal/procurement/{id}/propose` with `supplier_id`, `amount_cents`, `line_items`, `rationale` and that `run_id`. The supplier must be active and eligible (422 otherwise), the amount within the budget and the tranche, and the run a Procurement Agent run (422 `RUN_NOT_FOUND`). One proposal per request. Status `proposed`. Every purchase returns its `run_id`, so the website links it to the trace.
4. **Pay:** `POST /internal/procurement/{id}/pay`.
   - Up to `PROCUREMENT_AUTO_APPROVE_CENTS` (default 5,000 = 50 USD), it pays straight away.
   - Above that limit it answers 409 `APPROVAL_REQUIRED` until an admin approves with `POST /admin/procurement/{id}/approve` `{"approve": true}`. `false` cancels the request. `GET /admin/procurement` lists all requests.
   - It sends one batch, `procurement-<id>-<currency>`, to the supplier.
   - Once PayPal accepts the batch, the purchase is `paid`, the milestone `released`, an `expense` ledger entry is booked, and a receipt document is linked as `receipt_document_id`. The receipt is a public page, `GET /procurements/{id}/receipt` (HTML, not in the OpenAPI spec): supplier name, project, milestone, line items, total, date, PayPal batch id and status, never the supplier's email. `receipt_url` on every paid purchase points there, built from `PUBLIC_API_URL`. PayPal's own API link for the batch needs PayPal credentials, so it's only kept in the receipt's `extracted_fields.paypal_batch_url`.
   - Paying again returns the same result. A PayPal error leaves it `failed` with the error and can be retried, without a second batch.
5. **One release path:** a milestone with a requested, proposed, approved or paid purchase can't also be released as a tranche. `POST /internal/payout-requests` and `POST /admin/milestones/{id}/review` answer 409 `PROCUREMENT_MANAGED`.
6. **Payout webhooks** carry `procurement_id` on the payout item, so a webhook or admin refresh can finish a purchase too. The expense and receipt are still booked once.
7. **For the website:** `GET /projects/{id}/procurements` (public; only for listed or completed projects, never supplier emails) lists a project's purchases with `paypal_batch_id`, `receipt_url`, `needs_approval` and `run_id`. `POST /admin/procurement/{id}/retry` sends a `failed` purchase again with the same batch id, so PayPal can't pay twice. It's logged as the admin's `procurement_retry`.
8. **Reconciliation:** expenses count as money paid out (`procurement_expense_cents`). Seeded backers aren't PayPal money, so paying the seeded purchase on a database without real PayPal donations shows `negative_platform_balance`. Real sandbox donations cover it.

**Seed:** four suppliers in Nakuru and Kisumu, each with a unit price and reliability (Nakuru Books Sandbox at 75c is the best fit for the demo: 40 sets is exactly the 30 USD tranche), plus a 30 USD "40 copies of the Grade 3 reading set" request on Lanet Library's first milestone, with no matching on it, so the purchase is the whole tranche. For a real sandbox payout, run the seed with `SEED_SUPPLIER_EMAILS` set to your PayPal sandbox business accounts, comma-separated, in the seed's order (the fourth is Nakuru Books Sandbox). They replace the placeholder addresses. The API doesn't check that a proposal's line items add up to its amount; the Procurement Agent does.

### Refunds

`POST /admin/donations/{id}/refund` `{"amount_cents": 500, "reason": "..."}` (leave out `amount_cents` for everything left) refunds a PayPal-paid donation through PayPal. A `COMPLETED` refund is booked at once; a `PENDING` one when the `PAYMENT.CAPTURE.REFUNDED` webhook arrives. Each refund is booked once per PayPal refund id, so the webhook for an admin refund changes nothing. Agent gifts from a funded balance can't be refunded this way (409 `NOT_REFUNDABLE`).

## Payouts

Every released tranche (auto-released or approved by an admin) is sent through PayPal Payouts as its own batch ([`app/payouts.py`](app/payouts.py)).

- **Where it goes:** the project's payout account, `PUT /admin/projects/{id}/payout-account` `{"paypal_email": ...}`. In the sandbox use a sandbox personal account's email.
- **Deterministic ids:** `sender_batch_id` is `milestone-<id>-<currency>` (also sent as `PayPal-Request-Id`). PayPal refuses a reused one for 30 days, so sending twice can't pay twice.
- **Not sent yet:** no payout account, or PayPal refused (e.g. not enough balance in the sandbox business account) → the release still stands; the payout stays `pending` with the reason in each item's `error`. Fix it, then `POST /admin/payouts/{id}/send` (same id).
- **Tracking:** batches start `processing`. The payout webhooks (`PAYMENT.PAYOUTSBATCH.*`, `PAYMENT.PAYOUTS-ITEM.*`) update each item's status; `POST /admin/payouts/{id}/refresh` asks PayPal directly if a webhook was missed. A `SUCCESS` item writes one `payout` ledger entry (by PayPal's `payout_item_id`). `UNCLAIMED` = the email has no PayPal account yet; PayPal returns it after 30 days.
- **Retry:** items that `FAILED`, were `RETURNED` or `BLOCKED` → `POST /admin/payouts/{id}/retry` sends them in a new batch, `…-retry1`, `…-retry2`, using the project's current payout account (so fix the email first). The old items show `RETRIED`.
- **Try it in the sandbox:** `seed_dev` adds a 30 USD milestone to Lanet Library. Set its payout account to a sandbox personal email, then release it with `POST /internal/payout-requests` (all four checks true). The money comes out of the sandbox business account, which holds the test donations.

## Impact stories and the donor report

- `GET /projects/{id}/stories`: one story per **released** milestone, newest first: its title, a line on what was released (including matching), and `evidence_urls` from the milestone's receipt and photo documents. Dated by its payout (the release). None released → `[]`. The seed releases one tranche each on Kaptembwo Desks and Girls' STEM Club; release Lanet Library's first milestone to see a real one.
- `GET /donors/{id}/report` ("My Impact"): the donor's gifts, newest first (project, category and agent gifts; agent budget top-ups left out), each with `match_unlocked_cents`; `total_given_cents` (captured only; refunded gifts are listed but not counted); `updates` (stories from every project the donor backed, including through a category gift); and `agent_report` (the Giving Agent's latest run report).
- **Matching unlocked:** within each round, a project's match (final once closed, projected before) is shared among its backers in proportion to the square root of what each counted for (per-person cap applied, guests at half weight), the way each person moved its score. Category gifts don't move project scores, so they unlock 0.

## Reconciliation

- `GET /admin/reconciliation` (admin token) answers "do our records add up?" from our own database. `ok` is false when any issue is an error.
  - **Totals:** received via PayPal, refunded, PayPal fees, paid out, platform balance (received − refunds − fees − payouts: what should sit in the sandbox business account from this app), unspent agent budget, tranches released and not yet paid, match booked, category money not allocated.
  - **Errors:** captured payment without a ledger entry or without a capture id; ledger entry for a donation that isn't captured; refunds above the donation; category donation not split onto projects; negative agent balance; released tranche with no payout; successful payout not booked; a round matched beyond its pool; paid out more than received.
  - **Warnings:** orders not captured after 30 minutes (run the sweep); payments PayPal has held for over 3 days; payouts not sent, unclaimed, or failed (send or retry them).
- `POST /admin/reconciliation/sweep` asks PayPal about every order still open after 30 minutes: approved but never captured → captured now (the donor said yes in PayPal; this is the old popup-loop case); already captured → recorded; voided, or never approved after 3 hours → `failed`. One bad order doesn't stop the rest; it's listed in `errors`.
- Compare `platform_balance_cents` with the sandbox business account's balance (sandbox.paypal.com) before the demo. They differ by anything else that account received or sent, e.g. earlier manual tests.

## PayPal webhooks

PayPal tells us about payments that change after the donor leaves: a held payment that clears or is denied, refunds, and reversals (chargebacks). `POST /webhooks/paypal` handles them.

| Event | What happens |
|---|---|
| `PAYMENT.CAPTURE.COMPLETED` / `.PENDING` | Re-reads the order from PayPal and records it like the capture route: catches a held payment clearing, or a capture our route missed (browser closed). |
| `PAYMENT.CAPTURE.DENIED` | A pending donation becomes `failed`. |
| `PAYMENT.CAPTURE.REFUNDED` | A `refund` ledger entry; once refunds reach the full amount the donation becomes `refunded` and leaves project totals and matching. A partial refund stays counted. |
| `PAYMENT.CAPTURE.REVERSED` | Same as a refund, plus an audit-log entry (`actor: paypal`, `capture_reversed`) for the admin. |
| anything else | Recorded as `ignored`. |

- Every delivery is checked with PayPal's verify-signature API; unsigned or failing ones get 400. Without `PAYPAL_WEBHOOK_ID` the route refuses everything (503).
- Events are stored by id in `webhook_events`, so a redelivery returns `duplicate` and changes nothing. If a PayPal call fails mid-handling we answer 502 and store nothing, so PayPal retries.
- `GET /admin/webhook-events` (admin token) lists recent deliveries and the result of each. Use it to check the live setup.

### Setup (one time, sandbox)

1. developer.paypal.com → **Apps & Credentials** → Sandbox → open the app → **Webhooks → Add Webhook**.
2. URL: `https://<render service>.onrender.com/webhooks/paypal`. Events: Payment capture **completed**, **denied**, **pending**, **refunded**, **reversed**. Save.
3. Copy the **Webhook ID** shown next to it into Render → giving-api → Environment → `PAYPAL_WEBHOOK_ID`. Render redeploys.
4. Test with real sandbox payments, not the dashboard's Webhooks simulator: simulator events can't pass signature verification and are rejected with `INVALID_SIGNATURE`.
   - Pay on `https://<render service>.onrender.com/dev/checkout`, then check `/admin/webhook-events` for a `PAYMENT.CAPTURE.COMPLETED` row (`processed`).
   - Refund it: sandbox.paypal.com → log in as the sandbox **business** account → Activity → the payment → **Refund**. A `PAYMENT.CAPTURE.REFUNDED` row should appear and the project's `raised_cents` drop.

Webhooks can't reach `localhost`, so they only work on the deployed API.

## Donation flow (for P2)

Load the JS SDK with the **same currency** the API uses:

```html
<script src="https://www.paypal.com/sdk/js?client-id=<SANDBOX_CLIENT_ID>&currency=USD&intent=capture&components=buttons"></script>
```

```js
paypal.Buttons({
  createOrder: async () => {
    const r = await fetch(`${API}/donations/orders`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        target_type: "PROJECT",          // or "CATEGORY" with category_id, rule, excluded_tags
        project_id: 1,
        amount_cents: 2000,              // integer minor units
      }),
    });
    if (!r.ok) throw new Error((await r.json()).detail?.error);
    return (await r.json()).order_id;
  },
  onApprove: async (data, actions) => {
    const r = await fetch(`${API}/donations/orders/${data.orderID}/capture`, { method: "POST" });
    const body = await r.json();
    if (body.detail?.restart) return actions.restart(); // card declined: let donor pick another
    if (!r.ok) throw new Error(body.detail?.error);
    // body.status: "captured" | "pending" (pending = PayPal is holding it; show "processing")
  },
}).render("#paypal-button");
```

| Endpoint | Success | Errors (`detail.error`) |
|---|---|---|
| `POST /donations/orders` | `{order_id, donation_id}` | 422 validation or `AMOUNT_OUT_OF_RANGE`; 502 PayPal issue |
| `POST /donations/orders/{order_id}/capture` | donation (`status`, `amount_cents`, `currency`, ids) | 404 `ORDER_NOT_FOUND`; 422 `INSTRUMENT_DECLINED` + `restart: true`; 409 `AMOUNT_MISMATCH` / `CUSTOM_ID_MISMATCH`; 502 |

Capture is idempotent: calling it twice returns the same donation and writes the ledger once.

## Notes and decisions

- **Currency is USD.** PayPal does not process KES; show KES as a converted display amount only. Set by `CURRENCY`.
- The browser never sets what gets recorded: create stores a pending donation first, `custom_id = donation:<id>`, and capture checks PayPal's amount, currency and custom_id against it.
- `donations.paypal_capture_id` is stored because refunds and refund webhooks refer to the capture, not the order (added to the design's data model).
- Guest detection: `payment_source.card` in the capture response, or no `payer_id` → `donors.is_guest = true`. **Verify against a real sandbox card payment.**
- Capture status `PENDING` → donation `pending`, no ledger entry; the `PAYMENT.CAPTURE.COMPLETED` webhook settles it.
- PayPal's fee goes in as a separate `fee` ledger entry; the `donation` entry is the gross amount.
- Tables are created at startup, and new nullable columns are added to existing tables (`create_schema` in `app/db.py`; `create_all` alone never alters a table). Swap for migrations if the schema starts changing in other ways under live data.

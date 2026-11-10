# agents/ — Person 3

Giving, Discovery, Watchdog and Milestone agents for Community Giving. Rules decide; the LLM only
reads and explains. All writes and money actions go through the MCP tools in `../mcp-server/server.py`.

## Rules this service follows

- Scoring, filters, amounts and release checks are plain Python. The LLM writes text and extracts fields only.
- Project text, documents and receipts are **data**, wrapped in `<data>` blocks. Every LLM reply is validated against Pydantic; one retry, then a rule-based fallback.
- No PayPal keys, no database access, no direct payouts.
- Amounts are integer cents. Secrets come from env vars only.

## Setup

```bash
cd agents
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env      # then fill in the values
```

## Run the tests

Offline: fake LLM, fake MCP client, fake core. No network, no secrets needed.

```bash
cd agents
.venv/bin/python -m pytest tests/ -q
```

## Run the service

```bash
cd agents
.venv/bin/python -m uvicorn app.main:app --reload --port 8100
```

| Endpoint | Auth | Purpose |
|---|---|---|
| `GET /health` | none | liveness; shows `fake_core`, `dry_run`, model |
| `POST /agents/discovery/chat` | none (rate limited) | discovery chat; `/agents/chat` is an alias |
| `POST /agents/mandate/draft` | none (rate limited) | natural-language mandate draft; never writes |
| `POST /agents/giving/run` | `Authorization: Bearer $INTERNAL_TOKEN` | run one mandate; body `{"mandateId": 1, "force": false}` |

### Chat contract

The web app (`web/src/components/GivingAssistant.tsx`) sends `{"message": "..."}` and reads
`filters`, `projects[].id` and `explanation`. Response:

```json
{
  "filters": {"cause": "literacy", "region": "Nakuru", "excluding": "gambling"},
  "projects": [{"id": 3, "title": "...", "urgency": 4, "...": "..."}],
  "explanation": "Two projects fit.",
  "reply": "Two projects fit.",
  "projectIds": ["3", "7"]
}
```

`filters` values are always strings (the web renders `Object.values(filters)` as chips).
`reply` and `projectIds` mirror the spec-9.1 shape; the web ignores them. `projects` and `history`
are accepted in the request and ignored.

### Mandate draft contract

The web (`web/src/components/MandateDraft.tsx`) turns spoken or typed words into a draft of the
donor's rules. Request:

```json
{
  "text": "fifty a month, skip anything religious",
  "current": {
    "monthly_budget_cents": 4000,
    "per_project_max_cents": 1000,
    "approval_threshold_cents": 500,
    "categories": [2],
    "excluded_tags": []
  }
}
```

Response:

```json
{
  "proposed": {"monthly_budget_cents": 5000, "excluded_tags": ["faith-based"]},
  "warnings": ["couldn't verify tag faith-based"],
  "rejected": [],
  "used_llm": true
}
```

`proposed` carries only the fields the draft would change; anything absent stays as the donor had
it. `warnings` and `rejected` are always lists of plain strings. Nothing here creates a mandate:
the database row is written by the API after the donor confirms.

Status codes: **429** from the shared rate limit, **503** only when the text could not be read
*and* nothing was proposed, **422** for text over 1000 characters.

Rules the endpoint enforces:

- **Category ids come back in whatever domain they arrived.** The web sends API category ids when
  it talks to a real API and slug strings (`"education"`) on mock data. Existing values are
  returned untouched; `GET /categories` is used only to turn a newly named category into an id.
  A category that cannot be matched goes into `rejected`, never into a guess.
- **Tags are never dropped silently.** There is no public tag endpoint, so a named tag is checked
  against the tags visible on projects. An unseen tag is still kept, with
  `couldn't verify tag <name>` in `warnings`. A failed lookup flags every new tag rather than
  trusting them.
- **Weight overrides are clamped to what the API accepts** (at most 20 from each default, never
  below 0) and the clamp is reported in `warnings`.
- **Time budget:** 3 s for the catalogue lookup, 12 s for the LLM, inside the web's 20 s abort.
  Categories are cached in memory for 10 minutes. A lookup failure skips the lookup, it never
  fails the request.

## Scripts

Both are read-only dev probes: they only call `search_projects` / `get_project` and print no
secrets. Run them from `agents/`. Neither is part of the service.

**Smoke test** — real MCP server, three projects, plus 1-result and 0-result shape checks
(type and length only):

```bash
FAKE_CORE=false DRY_RUN=true .venv/bin/python scripts/hello_world.py
```

**Giving dry run** — canned mandate against live projects, real DeepSeek for the report
(thinking disabled), no writes:

```bash
FAKE_CORE=false DRY_RUN=true .venv/bin/python scripts/giving_dryrun.py
```

It prints each candidate's score and five factors, the planned allocation, skipped projects with
reasons, the report text and the LLM call count. `DRY_RUN=true` blocks `record_mandate_run` and
`request_checked_donation`; the script never calls them at all.

## Configuration

All from env (see `.env.example`):

| Variable | Default | Notes |
|---|---|---|
| `CORE_API_URL` | `https://giving-api.onrender.com` | core API base |
| `INTERNAL_TOKEN` | — | required for `/agents/giving/run` and the MCP subprocess |
| `FAKE_CORE` | `false` | `true` serves canned MCP results (use when the API token is unavailable) |
| `DRY_RUN` | `true` | blocks every mutating MCP tool; set `false` to arm the agents |
| `DEEPSEEK_API_KEY` | — | LLM; every caller has a fallback when it fails |
| `DEEPSEEK_MODEL` | `deepseek-v4-flash` | |
| `MCP_SERVER_PATH` | `../mcp-server/server.py` | |
| `WEB_ORIGIN` | `http://localhost:3000` | CORS allowlist, comma separated |
| `SCHEDULER_ENABLED` | `false` | off by default; see below |

## Scheduler

Off unless `SCHEDULER_ENABLED=true`. Jobs: giving run for every active mandate, watchdog scan,
milestone checks. Intervals: `GIVING_INTERVAL_HOURS`, `WATCHDOG_INTERVAL_SECONDS`,
`MILESTONE_INTERVAL_SECONDS`.

## Blocked on Person 1

`WatchdogAgent` and `MilestoneAgent` read through `EventsSource` and `MilestoneSource`. Both have
fake implementations in `app/agents/watchdog.py` and `app/agents/milestone.py`. Swap in the real
adapters when these exist:

- `GET /internal/donation-events?since=<iso>`
- `GET /internal/milestones?status=evidence_submitted`
- `POST /internal/documents/{id}/extraction`

DeepSeek is text-only, so receipts must arrive as text (or be OCR'd first).

## Layout

```
agents/
├── app/
│   ├── main.py          FastAPI surface
│   ├── config.py        env settings
│   ├── mcp_client.py    stdio MCP client (restart, DRY_RUN, FakeMcpClient)
│   ├── core.py          read-only public GETs
│   ├── llm.py           the only DeepSeek caller
│   ├── scheduler.py     APScheduler wiring (off by default)
│   └── agents/          giving, discovery, watchdog, milestone
├── tests/               pytest, offline
├── requirements.txt
├── .env.example
├── Dockerfile
└── README.md
```

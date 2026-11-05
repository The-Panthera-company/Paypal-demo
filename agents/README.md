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

## Configuration

All from env (see `.env.example`):

| Variable | Default | Notes |
|---|---|---|
| `CORE_API_URL` | `https://giving-api.onrender.com` | core API base |
| `INTERNAL_TOKEN` | — | required for `/agents/giving/run` and the MCP subprocess |
| `FAKE_CORE` | `false` | `true` serves canned MCP results (use when the API token is unavailable) |
| `DRY_RUN` | `false` | `true` blocks every mutating MCP tool |
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
│   ├── cache.py         small JSON cache
│   ├── scheduler.py     APScheduler wiring (off by default)
│   └── agents/          giving, discovery, watchdog, milestone
├── tests/               pytest, offline
├── requirements.txt
├── .env.example
├── Dockerfile
└── README.md
```

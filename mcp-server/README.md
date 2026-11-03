# MCP server for the agents (P1, for P3)

Gives the Giving, Milestone and Watchdog agents a small set of [MCP](https://modelcontextprotocol.io) tools over
the core API. Every tool is one call to the API with the internal token, and the API checks every rule (mandate
budget, exclusions, Watchdog freezes, payout thresholds) before money moves. This server holds no PayPal keys and
no database access, so an agent can't do more through it than the API allows.

| Tool | Calls | Changes anything? |
|---|---|---|
| `list_active_mandates` | `GET /internal/mandates/active` | no |
| `search_projects` | `GET /projects` (category, cause, group, region, `exclude_tags`, `q`, sort) | no |
| `get_project` | `GET /projects/{id}` | no |
| `get_leaderboard` | `GET /rounds/{current}/leaderboard` | no |
| `record_mandate_run` | `POST /internal/mandate-runs` | records the run |
| `request_checked_donation` | `POST /internal/checked-donations` | gives from the funded balance, if the API agrees |
| `open_watchdog_case` | `POST /internal/watchdog/cases` | freezes a project's matching |
| `request_milestone_payout` | `POST /internal/payout-requests` | releases a tranche, or holds it for an admin |
| `log_decision` | `POST /internal/audit` | writes to the agent log |

A rejection comes back as data (`status: rejected`, `rule_result: excluded_tag`); an API error (unknown run,
project not found) comes back as a tool error with the API's code.

## Run it

It runs over stdio: the agent service starts it as a subprocess, so the internal token stays with the agent.

```bash
cd mcp-server
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt      # macOS/Linux: .venv/bin/python
```

Settings, as environment variables of the process that starts it:

- `CORE_API_URL`: default `https://giving-api.onrender.com`
- `INTERNAL_TOKEN`: the API's `INTERNAL_TOKEN` (Render → giving-api → Environment)

Python agent (MCP client):

```python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

params = StdioServerParameters(command=".venv/Scripts/python", args=["server.py"],
                               env={"CORE_API_URL": "...", "INTERNAL_TOKEN": "..."})
async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
    await session.initialize()
    result = await session.call_tool("request_checked_donation",
                                     {"mandate_run_id": 5, "project_id": 4, "amount_cents": 250, "reason": "few backers"})
```

Claude Desktop or any MCP host: add a stdio server with the same command, args and env.

Not offered over HTTP on purpose: a public MCP endpoint would need its own login, or anyone could ask it to move money.

## Tests

```bash
.venv/Scripts/python -m pytest -q test_server.py
```

# Community Giving Platform (PayPal hackathon) — context for Claude

Three-person hackathon project. The user is **Person 2: product + frontend**.
Read `docs/PLAN.md` (schedule + handoffs) before starting work. Source documents:
`docs/System_Design.docx`, `docs/Work_Distribution.docx`.

## What it is
Small donors give via PayPal (sandbox) to a project, a category, or a Giving Agent bound by
their mandate. A sponsor pool is shared by two-level quadratic funding with a 20% floor and
caps. LLMs read and explain; deterministic rules in the core API decide every money movement;
PayPal moves the money. Everything is logged with a reason.

## Layout (planned monorepo)
- `web/` — Next.js + TypeScript, AG Grid (Person 2)
- `api/` — Spring Boot core API: PayPal, ledger, matching, mandates (Person 1)
- `agents/` — TypeScript agents + PayPal Agent Toolkit, Elastic (Person 3)

## Rules
- Amounts are integers in minor units; keep the currency on every row.
- No secrets in the repo: PayPal, LLM and Elastic keys live in Render env vars.
- Frontend builds against the Postman mock first; switch with `NEXT_PUBLIC_API_URL`.
- Matching changes must pass the worked example (Education, 10,000 KES pool, cap 40%:
  final 4,000 / 3,024 / 2,256 / 720).
- Feature freeze: Wednesday of week 3.

## Working with the user
Student; explain the reasoning, go in small steps, name the exact file for every edit.

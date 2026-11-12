# Community Giving: PayPal AI Hackathon

The group decides where the money goes; AI agents protect it; rules keep it fair; PayPal moves the money.

| Folder | What | Owner |
|---|---|---|
| `web/` | Next.js website: donor app, project pages, admin console | BUSOLO TITUS |
| `api/` | Python (FastAPI) core API: PayPal, ledger, matching | KOWITI ALLAN |
| `agents/` | AI agents (DeepSeek) and the MCP client | KALUKWO SHADRACK |
| `docs/` | Design docs, [team schedule](docs/TEAM_SCHEDULE.md), [UI ↔ backend guide](docs/UI_BACKEND_GUIDE.md) | All |

## Try it (live demo)

| | |
|---|---|
| **Website** | https://giving-web.onrender.com |
| **What the agents did** (live trace and activity) | https://giving-web.onrender.com/agents |
| **API docs** (try any route) | https://giving-api.onrender.com/docs |
| **A real purchase receipt** (paid by the Procurement Agent through PayPal Payouts) | https://giving-api.onrender.com/procurements/1/receipt |

The servers are on Render's free plan and sleep when idle: **the first page can take up to a minute to load**. After that it is fast.

All payments are **PayPal sandbox**: no real money moves. To pay, use a sandbox buyer account in the PayPal window:

- Email: `sb-segph53627780@personal.example.com`
- Password: `^_8w-(tR`

Things to try:

1. **Give $5 to a project** and watch its projected match: before you pay, the page shows what your gift adds to the matching pool. A small gift to a project with few backers adds the most.
2. **Ask the assistant** on the projects page, e.g. *"clean water projects for children, nothing faith-based"*.
3. **Set up a Giving Agent in plain words** on `/mandate`, e.g. *"About $20 a month, mostly water and health, at most $5 per project"*. The AI drafts the rules; nothing is saved until you approve.
4. **Open `/agents`** to see each agent run step by step: what it considered, what it chose, what it skipped and why.
5. **Open the leaderboard** to see how the matching pool is shared: people count, not just dollars.

## Tools we used

**AI model: DeepSeek V4 Flash** (`deepseek-v4-flash`, through DeepSeek's API). Every call is in [`agents/app/llm.py`](agents/app/llm.py). The model reads and writes text; **rules in code decide every gift, price and payout**, and the core API checks them again before any money moves. Every model reply is validated against a schema, with a rule-based fallback if the model fails.

| Agent | What the model does | What rules decide |
|---|---|---|
| **Discovery assistant** | Turns a donor's question into search filters, and explains the results | Which projects match |
| **Mandate drafting** | Turns a donor's own words into draft giving rules | Limits from `GET /mandates/constraints`; the donor approves before saving |
| **Giving Agent** | Writes the donor's report on each run | Scores, choices, amounts; the API re-checks the mandate on every gift |
| **Milestone Agent** | Reads receipt text: total, supplier, date | The four release checks and the auto-release limit |
| **Procurement Agent** | No model | Supplier eligibility, price (unit price × quantity) and reliability; admin approval above $50 |
| **Watchdog** | No model | Collusion rings found from the donation graph; a person confirms or clears |

Project text, documents and receipts are passed to the model as data, never as instructions.

**PayPal:** Checkout (JS SDK, Orders API) for donations, Subscriptions for monthly Giving Agent budgets, Payouts for milestone tranches and supplier purchases, Refunds, and webhooks to keep every record in step. All in sandbox.

**MCP:** the agents reach the core API only through our MCP server ([`mcp-server/`](mcp-server/README.md)), so an agent can never do more than the API allows.

**Built with:** Python (FastAPI, SQLAlchemy, Postgres) for the API and agents, and Next.js for the website.

### Sponsor tools

| Tool | What we use it for | Where |
|---|---|---|
| **AG Grid** | The leaderboard and the admin console: sortable, filterable grids for projects, cases, payouts and purchases | [`LeaderboardGrid.tsx`](web/src/components/LeaderboardGrid.tsx), [`AdminGrids.tsx`](web/src/components/admin/AdminGrids.tsx) |
| **Bryntum Gantt** | Each project's milestone timeline: what's planned, what's been proven, what's been paid | [`MilestoneGantt.tsx`](web/src/components/MilestoneGantt.tsx) |
| **APIMatic** | A developer portal and Python and TypeScript SDKs from our OpenAPI spec. We rewrote the spec generator to export OpenAPI 3.0 with full descriptions and examples, taking APIMatic's report from 1,490 issues to 0 errors and 1 warning | [`api/openapi.json`](api/openapi.json), [`api/app/openapi_docs.py`](api/app/openapi_docs.py) |
| **Render** | Hosts everything from one Blueprint: the core API, the AI agents service, the website and Postgres | [`render.yaml`](render.yaml) |

## Run the website on your computer

**Needs:** [Git](https://git-scm.com) and [Node.js 20 or 22 (LTS)](https://nodejs.org). Check with `node -v` and `git --version`.

### First time

```bash
git clone https://github.com/The-Panthera-company/Paypal-demo.git
cd Paypal-demo/web
npm install
```

Put the folder **outside OneDrive** (for example `C:\Users\<you>\Projects`). If the path has a space, wrap it in quotes in PowerShell: `cd "C:\Users\<you>\Projects\Paypal demo\Paypal-demo\web"`.

### Every time

**Windows:** double-click `web/start-web.bat`, or in PowerShell:

```powershell
cd <your path>\Paypal-demo\web
git pull
npx next dev -p 3000
```

**Mac / Linux:**

```bash
cd Paypal-demo/web
git pull
npm run dev
```

Open **http://localhost:3000**. Stop it with `Ctrl + C`.

> On some Windows machines `npm run dev` exits silently; `npx next dev -p 3000` (what `start-web.bat` uses) works.

### Or run it in Docker

Needs [Docker Desktop](https://www.docker.com/products/docker-desktop/) (running). No Node or Python needed on your PC.

**Website only, using the API on Render** (most of the time). Put your settings in `web/.env.local`
(`NEXT_PUBLIC_API_URL=https://<api>.onrender.com`, `ADMIN_TOKEN`, `ADMIN_UI_PASSWORD`, `NEXT_PUBLIC_DEMO_DONOR_ID=1`), then from the repo root:

```powershell
docker compose up web
```

**Website + API both in Docker** (works offline from Render; the API keeps its own local database). Put the API's settings
(PayPal sandbox keys, `ADMIN_TOKEN`) in `api/.env`, and in `web/.env.local` use:

```
NEXT_PUBLIC_API_URL=http://localhost:8000
API_INTERNAL_URL=http://api:8000
ADMIN_TOKEN=<same value as in api/.env>
```

```powershell
docker compose --profile local-api up
docker compose exec api python -m scripts.seed_dev     # first time: sample projects and a round
```

Open http://localhost:3000 (website) and http://localhost:8000/docs (API). Stop with `Ctrl + C`.
The first start takes a few minutes (downloads images, installs packages); later starts are quick.
After changing `.env.local`, stop and start again. If something looks stale: `docker compose down -v` resets the
containers and the website's package cache (it also deletes the local API database).

### Working on a branch

```bash
git fetch origin
git checkout <branch-name>      # e.g. p2/2-skeleton
cd web && npm install           # only if package.json changed
```

### Data: mock or real API

The site runs on built-in sample data (`web/src/lib/mock-data.ts`) until the API exists. To use the Postman mock or the real API, create `web/.env.local`:

```
NEXT_PUBLIC_API_URL=https://<postman-mock-or-api-url>
NEXT_PUBLIC_PAYPAL_CLIENT_ID=<sandbox client id>
```

For the admin console (`/admin`) also add:

```
ADMIN_TOKEN=<the API's ADMIN_TOKEN>        # stays on the server, never sent to the browser
ADMIN_UI_PASSWORD=<choose one>              # browser asks for it on /admin (any user name)
```

Without `ADMIN_TOKEN` the console shows sample data and its buttons change nothing.

Restart the dev server after changing it. Never commit `.env.local` or any secret.

### Checks before a pull request

```bash
cd web
npm run lint
npm run build
```

Both must pass. **Do not run `npm audit fix --force`**: it upgrades major versions and breaks the build.

### Common problems

| Problem | Fix |
|---|---|
| `npm run dev` stops with no message | Use `npx next dev -p 3000` or `start-web.bat` |
| Port 3000 in use | `npx next dev -p 3001` |
| Page has no styling | Stop the server, delete `web/.next`, start again |
| Errors after `git pull` | Run `npm install` again |
| `Module not found: Can't resolve 'ag-grid-community'` (or any package) | You switched to a branch with new packages: stop the server, `npm install`, start again. `start-web.bat` does this for you |
| `EBADENGINE` when updating npm | Ignore; you don't need a newer npm |

## Put the website online (Render)

`render.yaml` describes three things: `giving-api` (Person 1), its database `giving-db`, and the website `giving-web`. Free plan.

**First time** (whoever owns the Render account):

1. render.com → **New → Blueprint** → repo `The-Panthera-company/Paypal-demo`, branch `main` → it reads `render.yaml`.
   - If the API already exists from Person 1's earlier deploy, open that Blueprint and click **Manual sync** instead; Render adds `giving-web`.
2. It asks for the values marked `sync: false`:
   | Service | Key | Value |
   |---|---|---|
   | giving-web | `NEXT_PUBLIC_API_URL` | the API's address, e.g. `https://giving-api.onrender.com` (no `/` at the end) |
   | giving-web | `ADMIN_UI_PASSWORD` | choose a password for `/admin`; share it privately |
   | giving-web | `NEXT_PUBLIC_AGENTS_URL` | leave empty until Person 3's agents are deployed |
   `ADMIN_TOKEN` is copied from the API automatically.
3. **Apply**, wait for both builds (the website takes ~3–5 min).
4. Copy the website's address (`https://giving-web-xxxx.onrender.com`). In **giving-api → Environment**, set
   `CORS_ORIGINS` to `https://giving-web-xxxx.onrender.com,http://localhost:3000` and save (the API restarts).
   Without this, the PayPal button fails in the browser.
5. Check: open the website, then **Explore** (projects from the API), a project page (PayPal button appears),
   **Leaderboard**, and `/admin` (asks for the password).

**After that**, every merge to `main` redeploys both services. If you change `NEXT_PUBLIC_API_URL`, click
**Manual Deploy** on giving-web: Next.js reads it when building.

Free services sleep after ~15 min without visitors; the first page then takes about a minute.
**Before a demo, open the website and `/health` on the API a few minutes early.**

## How we work

Issue → branch (`p2/8-category-pages`) → pull request with `Closes #8` → one review → merge to `main` → auto-deploy to Render. Details and dates: [docs/TEAM_SCHEDULE.md](docs/TEAM_SCHEDULE.md).

## Licence

[MIT](LICENSE)

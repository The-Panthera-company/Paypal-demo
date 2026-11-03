# Community Giving: PayPal AI Hackathon

The group decides where the money goes; AI agents protect it; rules keep it fair; PayPal moves the money.

| Folder | What | Owner |
|---|---|---|
| `web/` | Next.js website: donor app, project pages, admin console | Person 2 |
| `api/` | Python (FastAPI) core API: PayPal, ledger, matching | Person 1 |
| `agents/` | AI agents, seed data, Elastic | Person 3 |
| `docs/` | Design docs, [team schedule](docs/TEAM_SCHEDULE.md), [UI ↔ backend guide](docs/UI_BACKEND_GUIDE.md) | All |

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

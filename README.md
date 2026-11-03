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

## How we work

Issue → branch (`p2/8-category-pages`) → pull request with `Closes #8` → one review → merge to `main` → auto-deploy to Render. Details and dates: [docs/TEAM_SCHEDULE.md](docs/TEAM_SCHEDULE.md).

## Licence

[MIT](LICENSE)

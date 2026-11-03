# web: donor app, project portal, admin console (Person 2)

```bash
cd web
cp .env.example .env.local   # leave values empty to use local mock data
npm install
npm run dev                  # http://localhost:3000
```

`src/lib/api.ts` is the only file that talks to the core API. With `NEXT_PUBLIC_API_URL`
empty it serves `src/lib/mock-data.ts`; set it to the Postman mock, then to the real API.
Amounts are integers in minor units (`12345` = 123.45).

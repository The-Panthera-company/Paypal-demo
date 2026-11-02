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

Without `DATABASE_URL` it uses a local SQLite file (`giving.db`). Docs at http://localhost:8000/docs, spec at `/openapi.json`.

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
        target_type: "PROJECT",          // or "CATEGORY" with category_id
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
- Capture status `PENDING` → donation `pending`, no ledger entry; the Day 4 webhook settles it.
- PayPal's fee goes in as a separate `fee` ledger entry; the `donation` entry is the gross amount.
- Tables are created at startup (`create_all`); swap for migrations if the schema starts changing under live data.

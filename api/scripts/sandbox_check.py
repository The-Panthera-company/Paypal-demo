"""Check the PayPal sandbox keys in api/.env without a browser.

Gets a token and creates (but never captures) a 1.00 order, then prints the
approve link. Run from api/:  .venv/Scripts/python -m scripts.sandbox_check
"""

import sys
import uuid

from app.config import get_settings
from app.paypal import PayPalClient, PayPalError


def main() -> int:
    s = get_settings()
    if not s.paypal_client_id or not s.paypal_client_secret:
        print("FAIL  PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET are empty in api/.env")
        return 1
    if "sandbox" not in s.paypal_base_url:
        print(f"FAIL  PAYPAL_BASE_URL is {s.paypal_base_url}; this check only runs against sandbox")
        return 1

    pp = PayPalClient(s)
    try:
        pp._access_token()
        print("OK    OAuth token from", s.paypal_base_url)
        order = pp.create_order(
            amount="1.00",
            currency=s.currency,
            custom_id="sandbox-check",
            description="Sandbox key check",
            request_id=f"check-{uuid.uuid4()}",
        )
    except PayPalError as e:
        print(f"FAIL  {e}  {e.body}")
        return 1

    approve = next((l["href"] for l in order.get("links", []) if l["rel"] in ("approve", "payer-action")), None)
    print(f"OK    Created order {order['id']} ({s.currency} 1.00, status {order['status']})")
    print(f"      approve link (optional, never captured): {approve}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

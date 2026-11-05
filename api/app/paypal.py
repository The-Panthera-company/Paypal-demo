"""Thin PayPal REST client. The core API is the only service that holds these credentials."""

import threading
import time

import httpx

from app.config import Settings, get_settings


class PayPalError(Exception):
    def __init__(self, status: int, body: dict):
        self.status = status
        self.body = body
        details = body.get("details") or [{}]
        # e.g. INSTRUMENT_DECLINED, ORDER_ALREADY_CAPTURED
        self.issue = details[0].get("issue") or body.get("name") or "UNKNOWN"
        super().__init__(f"PayPal {status}: {self.issue}")


class PayPalClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self._settings = settings
        self._http = httpx.Client(base_url=settings.paypal_base_url, timeout=20, transport=transport)
        self._token: str | None = None
        self._token_expires = 0.0
        self._lock = threading.Lock()

    def _access_token(self) -> str:
        with self._lock:
            # Refresh a minute early so a token never expires mid-request.
            if self._token and time.monotonic() < self._token_expires - 60:
                return self._token
            r = self._http.post(
                "/v1/oauth2/token",
                data={"grant_type": "client_credentials"},
                auth=(self._settings.paypal_client_id, self._settings.paypal_client_secret),
            )
            if r.status_code != 200:
                raise PayPalError(r.status_code, _json(r))
            body = r.json()
            self._token = body["access_token"]
            self._token_expires = time.monotonic() + body["expires_in"]
            return self._token

    def _request(self, method: str, path: str, *, json: dict | None = None, request_id: str | None = None) -> dict:
        headers = {"Authorization": f"Bearer {self._access_token()}", "Prefer": "return=representation"}
        # PayPal-Request-Id makes create/capture idempotent: a retry returns the first result.
        if request_id:
            headers["PayPal-Request-Id"] = request_id
        r = self._http.request(method, path, json=json, headers=headers)
        if r.status_code >= 400:
            raise PayPalError(r.status_code, _json(r))
        return r.json() if r.content else {}  # some calls (cancel) answer 204 with no body

    def create_order(self, *, amount: str, currency: str, custom_id: str, description: str, request_id: str) -> dict:
        # No payment_source here: with the JS SDK buttons, setting payment_source.paypal left the
        # popup looping on "Complete Purchase" without ever calling onApprove. A single DONATION
        # item stops PayPal asking for a shipping address instead.
        money = {"currency_code": currency, "value": amount}
        body = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "reference_id": custom_id,
                    "custom_id": custom_id,
                    "description": description[:127],
                    "amount": {**money, "breakdown": {"item_total": money}},
                    "items": [
                        {"name": description[:127], "quantity": "1", "unit_amount": money, "category": "DONATION"}
                    ],
                }
            ],
        }
        return self._request("POST", "/v2/checkout/orders", request_id=request_id, json=body)

    def capture_order(self, order_id: str, *, request_id: str) -> dict:
        return self._request("POST", f"/v2/checkout/orders/{order_id}/capture", request_id=request_id, json={})

    def get_order(self, order_id: str) -> dict:
        return self._request("GET", f"/v2/checkout/orders/{order_id}")

    def refund_capture(self, capture_id: str, *, amount: str | None, currency: str, note: str, request_id: str) -> dict:
        """Refund all of a capture (amount None) or part of it. The answer's status is COMPLETED or PENDING."""
        body: dict = {"note_to_payer": note[:255]}
        if amount is not None:
            body["amount"] = {"value": amount, "currency_code": currency}
        return self._request("POST", f"/v2/payments/captures/{capture_id}/refund", request_id=request_id, json=body)

    def create_payout(self, *, sender_batch_id: str, currency: str, items: list[dict]) -> dict:
        """Send one Payouts batch. items: sender_item_id, receiver (email), amount (PayPal string), note.

        sender_batch_id is deterministic: PayPal refuses a reused one for 30 days, so a retry can't pay twice.
        """
        body = {
            "sender_batch_header": {
                "sender_batch_id": sender_batch_id,
                "email_subject": "You have a payout from Community Giving",
                "email_message": "A milestone tranche for your project has been released.",
            },
            "items": [
                {
                    "recipient_type": "EMAIL",
                    "receiver": i["receiver"],
                    "amount": {"value": i["amount"], "currency": currency},
                    "note": i["note"][:4000],
                    "sender_item_id": i["sender_item_id"],
                }
                for i in items
            ],
        }
        return self._request("POST", "/v1/payments/payouts", json=body, request_id=sender_batch_id)

    def get_payout(self, payout_batch_id: str) -> dict:
        return self._request("GET", f"/v1/payments/payouts/{payout_batch_id}")

    def create_product(self, *, name: str, request_id: str) -> dict:
        return self._request("POST", "/v1/catalogs/products", request_id=request_id,
                             json={"name": name, "type": "SERVICE"})

    def create_monthly_plan(self, *, product_id: str, name: str, unit_price: str, currency: str, request_id: str) -> dict:
        """A monthly plan priced per unit, with quantity allowed: a subscription for N units bills N x unit_price."""
        body = {
            "product_id": product_id,
            "name": name,
            "status": "ACTIVE",
            "quantity_supported": True,
            "billing_cycles": [
                {
                    "frequency": {"interval_unit": "MONTH", "interval_count": 1},
                    "tenure_type": "REGULAR",
                    "sequence": 1,
                    "total_cycles": 0,  # until cancelled
                    "pricing_scheme": {"fixed_price": {"value": unit_price, "currency_code": currency}},
                }
            ],
            "payment_preferences": {"auto_bill_outstanding": True, "payment_failure_threshold": 1},
        }
        return self._request("POST", "/v1/billing/plans", request_id=request_id, json=body)

    def create_subscription(self, *, plan_id: str, quantity: int, custom_id: str, return_url: str,
                            cancel_url: str, request_id: str) -> dict:
        body = {
            "plan_id": plan_id,
            "quantity": str(quantity),
            "custom_id": custom_id,
            "application_context": {
                "brand_name": "Community Giving",
                "shipping_preference": "NO_SHIPPING",
                "user_action": "SUBSCRIBE_NOW",
                "return_url": return_url,
                "cancel_url": cancel_url,
            },
        }
        return self._request("POST", "/v1/billing/subscriptions", request_id=request_id, json=body)

    def get_subscription(self, subscription_id: str) -> dict:
        return self._request("GET", f"/v1/billing/subscriptions/{subscription_id}")

    def cancel_subscription(self, subscription_id: str, reason: str) -> None:
        self._request("POST", f"/v1/billing/subscriptions/{subscription_id}/cancel", json={"reason": reason[:128]})

    def verify_webhook_signature(self, *, headers: dict[str, str], event: dict, webhook_id: str) -> bool:
        """Ask PayPal whether this delivery really came from it, for our webhook.

        Events sent from the dashboard's Webhooks simulator always fail this check.
        """
        body = {
            "auth_algo": headers.get("paypal-auth-algo"),
            "cert_url": headers.get("paypal-cert-url"),
            "transmission_id": headers.get("paypal-transmission-id"),
            "transmission_sig": headers.get("paypal-transmission-sig"),
            "transmission_time": headers.get("paypal-transmission-time"),
            "webhook_id": webhook_id,
            "webhook_event": event,
        }
        result = self._request("POST", "/v1/notifications/verify-webhook-signature", json=body)
        return result.get("verification_status") == "SUCCESS"


def _json(r: httpx.Response) -> dict:
    try:
        return r.json()
    except ValueError:
        return {"name": "NON_JSON_RESPONSE", "message": r.text[:500]}


_client: PayPalClient | None = None


def get_paypal() -> PayPalClient:
    global _client
    if _client is None:
        _client = PayPalClient(get_settings())
    return _client

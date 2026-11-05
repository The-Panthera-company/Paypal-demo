import json
import os

# Before any app import: tests never touch the database named in .env (it may be the live one).
os.environ["DATABASE_URL"] = "sqlite://"

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings, get_settings
from app.db import Base, get_db
from app.main import app
from app.models import Category, Project, ProjectStatus
from app.paypal import PayPalClient, get_paypal


class FakePayPal:
    """Stands in for the PayPal sandbox at the HTTP level, so PayPalClient is exercised too."""

    def __init__(self):
        self.orders: dict[str, dict] = {}
        self.requests: list[httpx.Request] = []
        self.token_calls = 0
        self.capture_override: tuple[int, dict] | None = None
        self.capture_status = "COMPLETED"
        self.payment_source: dict = {"paypal": {"email_address": "donor@example.com"}}
        self.verification_status = "SUCCESS"
        self.get_order_down = False
        self.payouts: dict[str, dict] = {}  # payout_batch_id -> request body
        self.payout_error: tuple[int, dict] | None = None
        self.payout_item_status = "SUCCESS"
        self.plans: dict[str, dict] = {}  # plan id -> request body
        self.subscriptions: dict[str, dict] = {}  # subscription id -> request body
        self.cancelled: list[str] = []
        self.refunds: list[dict] = []  # request bodies, with the capture id
        self.refund_status = "COMPLETED"

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path == "/v1/oauth2/token":
            self.token_calls += 1
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 32400})
        if path == "/v2/checkout/orders" and request.method == "POST":
            body = json.loads(request.content)
            order_id = f"ORDER{len(self.orders) + 1}"
            self.orders[order_id] = {"id": order_id, "status": "CREATED", "purchase_units": body["purchase_units"]}
            return httpx.Response(201, json=self.orders[order_id])
        if path.endswith("/capture"):
            if self.capture_override:
                status, body = self.capture_override
                return httpx.Response(status, json=body)
            return httpx.Response(201, json=self.capture(path.split("/")[-2]))
        if path.startswith("/v2/payments/captures/") and path.endswith("/refund"):
            body = json.loads(request.content)
            self.refunds.append({"capture_id": path.split("/")[-2], **body})
            return httpx.Response(201, json={"id": f"REF-{len(self.refunds)}", "status": self.refund_status})
        if path == "/v1/payments/payouts" and request.method == "POST":
            if self.payout_error:
                status, body = self.payout_error
                return httpx.Response(status, json=body)
            body = json.loads(request.content)
            sender_batch_id = body["sender_batch_header"]["sender_batch_id"]
            if any(b["sender_batch_header"]["sender_batch_id"] == sender_batch_id for b in self.payouts.values()):
                return httpx.Response(400, json={"name": "USER_BUSINESS_ERROR", "details": [{"issue": "SENDER_BATCH_ID_ALREADY_USED"}]})
            batch_id = f"BATCH{len(self.payouts) + 1}"
            self.payouts[batch_id] = body
            return httpx.Response(201, json={"batch_header": {"payout_batch_id": batch_id, "batch_status": "PENDING",
                                                              "sender_batch_header": body["sender_batch_header"]}})
        if path.startswith("/v1/payments/payouts/") and request.method == "GET":
            return httpx.Response(200, json=self.payout_batch(path.split("/")[-1]))
        if path == "/v1/catalogs/products" and request.method == "POST":
            return httpx.Response(201, json={"id": "PROD-1", **json.loads(request.content)})
        if path == "/v1/billing/plans" and request.method == "POST":
            plan_id = f"P-{len(self.plans) + 1}"
            self.plans[plan_id] = json.loads(request.content)
            return httpx.Response(201, json={"id": plan_id, "status": "ACTIVE"})
        if path == "/v1/billing/subscriptions" and request.method == "POST":
            sub_id = f"I-SUB{len(self.subscriptions) + 1}"
            self.subscriptions[sub_id] = json.loads(request.content)
            approve = f"https://www.sandbox.paypal.com/webapps/billing/subscriptions?ba_token=BA-{sub_id}"
            return httpx.Response(201, json={"id": sub_id, "status": "APPROVAL_PENDING",
                                             "links": [{"rel": "approve", "href": approve}]})
        if path.startswith("/v1/billing/subscriptions/") and path.endswith("/cancel"):
            self.cancelled.append(path.split("/")[-2])
            return httpx.Response(204)
        if path == "/v1/notifications/verify-webhook-signature":
            return httpx.Response(200, json={"verification_status": self.verification_status})
        if path.startswith("/v2/checkout/orders/") and request.method == "GET":
            if self.get_order_down:
                return httpx.Response(503, json={"name": "SERVICE_UNAVAILABLE"})
            order = self.orders.get(path.split("/")[-1])
            if order is None:
                return httpx.Response(404, json={"name": "RESOURCE_NOT_FOUND", "details": [{"issue": "INVALID_RESOURCE_ID"}]})
            return httpx.Response(200, json=order)
        return httpx.Response(404, json={"name": "RESOURCE_NOT_FOUND"})

    def payout_batch(self, batch_id: str, item_status: str | None = None) -> dict:
        """A batch as GET /v1/payments/payouts/{id} returns it, items in payout_item_status."""
        body = self.payouts[batch_id]
        return {
            "batch_header": {"payout_batch_id": batch_id, "batch_status": "SUCCESS",
                             "sender_batch_header": body["sender_batch_header"]},
            "items": [
                {
                    "payout_item_id": f"ITEM-{batch_id}-{n}",
                    "transaction_status": item_status or self.payout_item_status,
                    "payout_batch_id": batch_id,
                    "payout_item": {k: item[k] for k in ("sender_item_id", "receiver", "amount")},
                }
                for n, item in enumerate(body["items"], start=1)
            ],
        }

    def capture(self, order_id: str) -> dict:
        """Capture at "PayPal". Tests call it directly for a capture our API never saw."""
        order = self.orders[order_id]
        unit = order["purchase_units"][0]
        amount = unit["amount"]
        unit["payments"] = {
            "captures": [
                {
                    "id": f"CAP-{order_id}",
                    "status": self.capture_status,
                    "amount": dict(amount),
                    "seller_receivable_breakdown": {
                        "gross_amount": amount,
                        "paypal_fee": {"currency_code": amount["currency_code"], "value": "0.59"},
                    },
                }
            ]
        }
        order.update(
            status="COMPLETED",
            payer={"payer_id": "PAYER123", "name": {"given_name": "Wanjiru"}},
            payment_source=self.payment_source,
        )
        return order


@pytest.fixture
def fake_paypal():
    return FakePayPal()


@pytest.fixture
def db_session_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        db.add_all(
            [
                Category(id=1, name="Education"),
                Category(id=2, name="Health"),
                Project(
                    id=1,
                    category_id=1,
                    title="Lanet Library",
                    tags=["books", "literacy"],
                    status=ProjectStatus.active,
                    goal_amount=120000,
                    currency="USD",
                    urgency=4,
                    cause="literacy",
                    beneficiary_group="children",
                    region="Nakuru",
                ),
                Project(
                    id=2,
                    category_id=1,
                    title="Faith School Desks",
                    tags=["faith-based", "furniture"],
                    status=ProjectStatus.active,
                    goal_amount=50000,
                    currency="USD",
                    urgency=2,
                    region="Kisumu",
                    hide_location=True,
                ),
                Project(id=3, category_id=2, title="Clinic Roof", status=ProjectStatus.pending_review, goal_amount=80000, currency="USD"),
            ]
        )
        db.commit()
    return factory


@pytest.fixture
def client(fake_paypal, db_session_factory):
    settings = Settings(
        paypal_client_id="id",
        paypal_client_secret="secret",
        currency="USD",
        internal_token="internal-test-token",
        admin_token="admin-test-token",
        paypal_webhook_id="WH-TEST",
        projection_interval_seconds=0,
    )
    paypal = PayPalClient(settings, transport=httpx.MockTransport(fake_paypal.handler))

    def _db():
        with db_session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_paypal] = lambda: paypal
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

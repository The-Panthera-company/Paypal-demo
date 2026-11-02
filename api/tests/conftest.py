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
        if path == "/v1/notifications/verify-webhook-signature":
            return httpx.Response(200, json={"verification_status": self.verification_status})
        if path.startswith("/v2/checkout/orders/") and request.method == "GET":
            if self.get_order_down:
                return httpx.Response(503, json={"name": "SERVICE_UNAVAILABLE"})
            return httpx.Response(200, json=self.orders[path.split("/")[-1]])
        return httpx.Response(404, json={"name": "RESOURCE_NOT_FOUND"})

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

"""Monthly Giving Agent budgets through PayPal Subscriptions.

One billing plan per currency at 1.00 a month with quantity allowed, so a donor's 25 USD a month
is that plan with quantity 25: one plan serves every amount. The donor approves in PayPal; each
month PayPal charges them and sends PAYMENT.SALE.COMPLETED, which credits the budget as an AGENT
top-up (the same kind of donation as a one-off top-up, keyed by the sale id so it is credited once).
Subscription webhooks keep the status current, so the agent can see when funding stops.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AgentSubscription, Donation, DonationStatus, PaypalPlan, TargetType
from app.money import from_paypal
from app.paypal import PayPalClient
from app.routers.donations import mark_captured

UNIT_PRICE = "1.00"


def plan_for(db: Session, paypal: PayPalClient, currency: str) -> str:
    """The monthly plan's id, creating the PayPal product and plan the first time. Caller commits."""
    plan = db.get(PaypalPlan, currency)
    if plan is None:
        product = paypal.create_product(name="Giving Agent monthly budget", request_id=f"agent-budget-product-{currency}")
        created = paypal.create_monthly_plan(
            product_id=product["id"],
            name=f"Giving Agent budget ({currency} {UNIT_PRICE} x amount)",
            unit_price=UNIT_PRICE,
            currency=currency,
            request_id=f"agent-budget-plan-{currency}",
        )
        plan = PaypalPlan(currency=currency, product_id=product["id"], plan_id=created["id"])
        db.add(plan)
        db.flush()
    return plan.plan_id


def approve_url(subscription: dict) -> str | None:
    return next((link["href"] for link in subscription.get("links", []) if link.get("rel") == "approve"), None)


def current(db: Session, donor_id: int) -> AgentSubscription | None:
    """The donor's latest subscription that is pending approval, active or suspended."""
    return db.scalar(
        select(AgentSubscription)
        .where(AgentSubscription.donor_id == donor_id,
               AgentSubscription.status.in_(("APPROVAL_PENDING", "ACTIVE", "SUSPENDED")))
        .order_by(AgentSubscription.created_at.desc())
    )


def credit_sale(db: Session, sale: dict) -> str:
    """A monthly charge (PAYMENT.SALE.COMPLETED): credit the subscriber's agent budget once."""
    subscription = db.get(AgentSubscription, sale.get("billing_agreement_id"))
    if subscription is None:
        return "unmatched"
    if db.scalar(select(Donation.id).where(Donation.paypal_capture_id == sale.get("id"))):
        return "processed"  # already credited
    money = sale.get("amount", {})
    currency = money.get("currency", subscription.currency)
    if currency != subscription.currency:
        return "mismatch"
    donation = Donation(
        donor_id=subscription.donor_id,
        target_type=TargetType.AGENT,
        amount=from_paypal(money.get("total", "0"), currency),
        currency=currency,
        paypal_capture_id=sale["id"],
        status=DonationStatus.created,
        created_at=datetime.now(timezone.utc),
    )
    db.add(donation)
    db.flush()
    fee = sale.get("transaction_fee") or {}
    capture = {"seller_receivable_breakdown": {"paypal_fee": {"value": fee["value"], "currency_code": fee.get("currency", currency)}}} if fee.get("value") else {}
    mark_captured(db, donation, capture)  # captured donation + ledger entries, like a one-off top-up
    if subscription.status != "ACTIVE":
        subscription.status = "ACTIVE"
    return "processed"


STATUS_EVENTS = {
    "BILLING.SUBSCRIPTION.ACTIVATED": "ACTIVE",
    "BILLING.SUBSCRIPTION.RE-ACTIVATED": "ACTIVE",
    "BILLING.SUBSCRIPTION.SUSPENDED": "SUSPENDED",
    "BILLING.SUBSCRIPTION.CANCELLED": "CANCELLED",
    "BILLING.SUBSCRIPTION.EXPIRED": "EXPIRED",
}


def apply_status(db: Session, event_type: str, resource: dict) -> str:
    subscription = db.get(AgentSubscription, resource.get("id"))
    if subscription is None:
        return "unmatched"
    if event_type == "BILLING.SUBSCRIPTION.PAYMENT.FAILED":
        subscription.status = "SUSPENDED" if resource.get("status") == "SUSPENDED" else subscription.status
    else:
        subscription.status = STATUS_EVENTS[event_type]
    return "processed"

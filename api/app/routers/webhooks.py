"""PayPal webhooks. PayPal calls this; it is authenticated by signature verification, not a token."""

from fastapi import APIRouter

from app.stubs import PLANNED, planned

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/paypal", status_code=200, responses=PLANNED)
def paypal_webhook():
    """Verifies the signature, ignores repeats by event id, then handles PAYMENT.CAPTURE.COMPLETED,
    .PENDING, .DENIED, .REFUNDED, .REVERSED and the Payouts batch/item events."""
    planned("webhooks")

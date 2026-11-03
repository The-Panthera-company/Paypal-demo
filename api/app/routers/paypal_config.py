"""Public PayPal settings for the browser, plus a sandbox-only test checkout page."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.config import Settings, get_settings

router = APIRouter(tags=["paypal"])

_CHECKOUT_PAGE = Path(__file__).resolve().parent.parent / "static" / "checkout.html"


def _is_sandbox(settings: Settings) -> bool:
    return "sandbox" in settings.paypal_base_url


@router.get("/config/paypal")
def paypal_config(settings: Settings = Depends(get_settings)) -> dict:
    # The client ID is public by design; the secret never leaves the server.
    return {
        "client_id": settings.paypal_client_id,
        "currency": settings.currency,
        "environment": "sandbox" if _is_sandbox(settings) else "live",
        "min_donation_cents": settings.min_donation_cents,
        "max_donation_cents": settings.max_donation_cents,
    }


@router.get("/dev/checkout", include_in_schema=False)
def dev_checkout(settings: Settings = Depends(get_settings)):
    if not _is_sandbox(settings):
        raise HTTPException(404)
    return FileResponse(_CHECKOUT_PAGE)

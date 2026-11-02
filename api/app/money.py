"""Conversion between our integer minor units and PayPal's decimal strings."""

from decimal import ROUND_HALF_UP, Decimal

# Currencies PayPal accepts for payments (developer.paypal.com/reference/currency-codes).
# KES is not among them, so Kenyan amounts are display-only.
PAYPAL_CURRENCIES = {
    "AUD", "BRL", "CAD", "CNY", "CZK", "DKK", "EUR", "HKD", "HUF", "ILS", "JPY",
    "MYR", "MXN", "TWD", "NZD", "NOK", "PHP", "PLN", "GBP", "SGD", "SEK", "CHF",
    "THB", "USD",
}
# PayPal rejects decimals for these.
ZERO_DECIMAL = {"HUF", "JPY", "TWD"}


def _exponent(currency: str) -> int:
    if currency not in PAYPAL_CURRENCIES:
        raise ValueError(f"PayPal does not support {currency}")
    return 0 if currency in ZERO_DECIMAL else 2


def to_paypal(cents: int, currency: str) -> str:
    """12345, 'USD' -> '123.45'"""
    exp = _exponent(currency)
    value = Decimal(cents).scaleb(-exp)
    return f"{value:.{exp}f}"


def from_paypal(value: str, currency: str) -> int:
    """'123.45', 'USD' -> 12345. Rejects values with more precision than the currency allows."""
    exp = _exponent(currency)
    scaled = Decimal(value).scaleb(exp)
    if scaled != scaled.to_integral_value(ROUND_HALF_UP):
        raise ValueError(f"{value} has too many decimals for {currency}")
    return int(scaled)

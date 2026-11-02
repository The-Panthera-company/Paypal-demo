import pytest

from app.money import from_paypal, to_paypal


def test_round_trip_usd():
    assert to_paypal(12345, "USD") == "123.45"
    assert to_paypal(5, "USD") == "0.05"
    assert from_paypal("123.45", "USD") == 12345
    assert from_paypal("10", "USD") == 1000


def test_zero_decimal_currency():
    assert to_paypal(500, "JPY") == "500"
    assert from_paypal("500", "JPY") == 500


def test_rejects_kes():
    with pytest.raises(ValueError):
        to_paypal(100, "KES")


def test_rejects_extra_precision():
    with pytest.raises(ValueError):
        from_paypal("1.005", "USD")

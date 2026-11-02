from app.config import Settings, get_settings
from app.main import app


def test_config_exposes_client_id_but_not_secret(client):
    r = client.get("/config/paypal")
    assert r.status_code == 200
    body = r.json()
    assert body["client_id"] == "id"
    assert body["currency"] == "USD"
    assert body["environment"] == "sandbox"
    assert "secret" not in r.text


def test_checkout_page_served_in_sandbox(client):
    r = client.get("/dev/checkout")
    assert r.status_code == 200
    assert "paypal.Buttons" in r.text


def test_checkout_page_hidden_in_live(client):
    app.dependency_overrides[get_settings] = lambda: Settings(paypal_base_url="https://api-m.paypal.com")
    assert client.get("/dev/checkout").status_code == 404

"""pytest: API contract + SEC-01 network-egress assertion (no socket opened while scoring)."""
import socket
import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI
from url_v5_service import router

app = FastAPI(); app.include_router(router)
client = TestClient(app)


@pytest.fixture
def no_network(monkeypatch):
    def boom(*a, **k): raise AssertionError("SEC-01 violated: network access attempted")
    monkeypatch.setattr(socket, "create_connection", boom)
    monkeypatch.setattr(socket.socket, "connect", boom)
    monkeypatch.setattr(socket, "getaddrinfo", boom)


@pytest.mark.parametrize("url,band", [
    ("http://sbi-kyc-update.online/login.php", "High"),
    ("paypal.com.secure-verify.xyz/signin", "High"),
    ("https://kiit.ac.in/", "Low"),
    ("https://docs.python.org/3/library/urllib.parse.html", "Low"),
])
def test_bands(no_network, url, band):
    r = client.post("/api/check-url", json={"url": url})
    assert r.status_code == 200
    j = r.json()
    assert j["band"] == band and 0 <= j["score"] <= 100 and j["evidence"]
    assert "http" not in j["url_defanged"].lower().replace("hxxp", "")   # defanged


@pytest.mark.parametrize("bad", ["javascript:alert(1)", "ftp://x.com/a", "", "a b c"])
def test_rejects_bad_input(no_network, bad):
    assert client.post("/api/check-url", json={"url": bad}).status_code == 422


def test_health():
    assert client.get("/api/health").json()["status"] == "ok"

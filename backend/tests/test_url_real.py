"""The real URL bundle through the API. Skipped when models/model_bundle is absent."""
import json
import socket
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main
from services import runtime

BUNDLE = Path(__file__).resolve().parents[2] / "models" / "model_bundle"
# v5 scores recorded at training time (MLPhil_URL_v5_kaggle_check.ipynb, parity cell).
EXPECTED_V5 = {
    "https://www.google.com/": 0.04378410467726692,
    "https://github.com/scikit-learn/scikit-learn": 0.0004928194416649637,
    "https://www.sbi.co.in/web/personal-banking": 0.5440022021998719,
    "http://sbi-kyc-update.online/login.php": 0.9999802986676156,
    "paypal.com.secure-verify.xyz/signin": 0.9999955121203509,
    "https://kiit.ac.in/": 0.03346929268891014,
    "https://my-office365-docs.pages.dev/auth": 0.9999920698481023,
    "https://www.amazon.in/gp/your-account/order-history": 0.9172495256403749,
    "https://appleid.apple.com.verify-id.co/": 0.9999984215940974,
    "https://swispostch.com/portal": 0.9129270654552593,
    "https://docs.python.org/3/library/urllib.parse.html": 3.543825718479272e-05,
    "http://192.0.2.10/admin/login.php": 0.9995332489025176,
    "https://www.irctc.co.in/nget/train-search": 0.04938253811040496,
    "https://telegarm-login.web.app/verify": 0.9999561113499335,
}

pytestmark = pytest.mark.skipif(not BUNDLE.exists(), reason="URL bundle not on disk")


def expected_scores():
    """Training-time scores for whichever bundle is installed (v6: recorded by the URL pipeline notebook on Kaggle)."""
    if json.loads((BUNDLE / "metadata.json").read_text())["version"] == "mlphil_url_v5":
        return EXPECTED_V5
    return json.loads((Path(__file__).parent / "url_v6_parity.json").read_text(encoding="utf-8"))["scores"]


@pytest.fixture
def real(monkeypatch):
    runtime.limiter.reset()
    monkeypatch.setenv("MLPHIL_URL_BUNDLE", str(BUNDLE))
    with TestClient(main.create_app()) as c:
        yield c


def test_scores_match_training_time(real):
    assert real.get("/api/health").json()["url_model"] is True
    for url, score in expected_scores().items():
        got = real.post("/api/check-url", json={"url": url}).json()["score"]
        assert got == pytest.approx(score * 100, abs=0.1), url


def test_bands_for_the_demo_examples(real):
    def band(url):
        return real.post("/api/check-url", json={"url": url}).json()["band"]

    assert band("paypal.com.secure-verify.xyz/signin") == "High"
    assert band("http://sbi-kyc-update.online/login.php") == "High"
    assert band("https://kiit.ac.in/") == "Low"
    assert band("https://docs.python.org/3/") == "Low"


def test_model_info_thresholds_come_from_the_bundle(real):
    meta = json.loads((BUNDLE / "metadata.json").read_text())
    url = real.get("/api/model-info").json()["url"]
    assert url["thr_high"] == round(meta["thr_alert"] * 100, 3)
    assert url["thr_medium"] == round(meta["thr_review"] * 100, 3)


def test_response_has_evidence_and_is_defanged(real):
    body = real.post("/api/check-url", json={"url": "  https://paypal.com.secure-verify.xyz/signin "}).json()
    assert body["url_defanged"] == "hxxps://paypal[.]com[.]secure-verify[.]xyz/signin"
    assert "Brand name appears in the address but the real domain is 'secure-verify.xyz'" in body["evidence"]
    assert real.post("/api/check-url", json={"url": "https://kiit.ac.in/"}).json()["evidence"]


def test_no_network_egress(real, monkeypatch):
    def blocked(*_, **__):
        raise AssertionError("network used")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    # A host the bundle has not cached, so a PSL or DNS lookup would be attempted here.
    r = real.post("/api/check-url", json={"url": "https://never-seen-host-12345.example/login"})
    assert r.status_code == 200

"""The real email model through the API. Skipped when models/email_security_model is absent.
Checks wiring and contract, not accuracy: accuracy is in the model's reports/."""
import json
import socket
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main
from services import runtime

MODEL_DIR = Path(__file__).resolve().parents[2] / "models" / "email_security_model"
VERDICTS = {"LEGITIMATE", "SPAM", "PHISHING", "UNCERTAIN"}

pytestmark = pytest.mark.skipif(not MODEL_DIR.exists(), reason="email model not on disk")


def blocked(*_, **__):
    raise AssertionError("network used")


@pytest.fixture(scope="module")
def real():
    """Loads with the network blocked, so a load that needs the internet fails here."""
    runtime.limiter.reset()
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("MLPHIL_EMAIL_MODEL_DIR", str(MODEL_DIR))
        mp.delenv("MLPHIL_EMAIL_REPORTS", raising=False)
        mp.setattr(socket.socket, "connect", blocked)
        mp.setattr(socket, "getaddrinfo", blocked)
        with TestClient(main.create_app()) as c:
            yield c


def test_model_loads_offline_and_reports_ready(real):
    health = real.get("/api/health").json()
    assert health["email_model"] is True
    assert health["versions"]["email"].startswith("email_security_model, trained 2026-")


@pytest.mark.parametrize(
    "subject,body",
    [
        ("Your account is suspended", "Verify your identity within 24 hours: http://northwind-bank-verify.example/login"),
        ("90% OFF everything", "Huge discounts today only. Buy now: http://mega-deals.example/sale"),
        ("Minutes from Tuesday", "The minutes are below. Priya will share the schedule by Friday."),
    ],
)
def test_response_shape_without_network(real, subject, body):
    r = real.post("/api/check-email", json={"subject": subject, "body": body})
    assert r.status_code == 200
    j = r.json()
    assert j["verdict"] in VERDICTS and j["prediction"] in VERDICTS
    assert set(j["probabilities"]) == {"LEGITIMATE", "SPAM", "PHISHING"}
    assert sum(j["probabilities"].values()) == pytest.approx(1, abs=0.001)
    assert j["truncated"] is False and j["model_version"].startswith("email_security_model")


def test_same_email_gives_same_result(real):
    payload = {"subject": "Hello", "body": "Please review the attached invoice before Friday."}
    assert real.post("/api/check-email", json=payload).json() == real.post("/api/check-email", json=payload).json()


def test_long_email_is_flagged_truncated(real):
    r = real.post("/api/check-email", json={"body": "please read this project update carefully. " * 300})
    assert r.status_code == 200 and r.json()["truncated"] is True


def test_empty_and_oversize_are_422(real):
    empty = real.post("/api/check-email", json={"subject": "", "body": "   "})
    assert empty.status_code == 422 and empty.json()["detail"] == {"message": "empty email"}
    assert real.post("/api/check-email", json={"body": "x" * 100_001}).status_code == 422


def test_model_info_reads_real_metrics_without_paths(real):
    email = real.get("/api/model-info").json()["email"]
    assert email["labels"] == ["LEGITIMATE", "SPAM", "PHISHING"]
    metrics = email["metrics"]
    if metrics is None:
        pytest.skip("models/email_reports not on disk")
    summary = json.loads((MODEL_DIR.parent / "email_reports" / "summary.json").read_text())
    assert metrics["external"]["phish_recall"] == summary["external"]["phish_recall"]
    assert metrics["internal"]["macro_f1"] == summary["internal"]["macro_f1"]
    assert "/kaggle/" not in json.dumps(email)


def test_analyze_email_end_to_end_without_network(real):
    """Both real models (URL bundle loaded by the fixture if present), network blocked."""
    body = "Your account is suspended. Verify now: http://sbi-kyc-update.online/login.php or visit https://kiit.ac.in/"
    r = real.post("/api/analyze-email", json={"subject": "Account suspended", "body": body})
    assert r.status_code == 200
    j = r.json()
    assert j["urls_found"] == 2 and j["overall"] in {"HIGH", "MEDIUM", "UNCERTAIN", "UNAVAILABLE", "LOW"}
    assert [u["url_defanged"] for u in j["urls"]] == ["hxxp://sbi-kyc-update[.]online/login[.]php", "hxxps://kiit[.]ac[.]in/"]


def test_html_in_email_is_not_echoed(real):
    r = real.post("/api/check-email", json={"body": "<script>alert('secret-marker')</script><a href='http://x.example'>hi there</a>"})
    assert r.status_code == 200 and "secret-marker" not in r.text and "x.example" not in r.text

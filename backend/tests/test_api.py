"""API contract with stand-in models, so these run without any model on disk."""
import json
import socket
import time
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import main
from services import runtime

URL_RESULT = {
    "model": "mlphil_url_v5",
    "band": "High",
    "score": 100.0,
    "evidence": ["Uses lure words (login / verify / account / update …)"],
    "url_defanged": "hxxps://paypal[.]example/signin",
    "note": "URL pattern strongly resembles phishing",
    "disclaimer": "URL-text analysis only. The link was not opened. A Low band is not a safety guarantee.",
}
EMAIL_RESULT = {
    "prediction": "PHISHING",
    "verdict": "PHISHING",
    "confidence": 0.9731,
    "probabilities": {"LEGITIMATE": 0.0102, "SPAM": 0.0167, "PHISHING": 0.9731},
    "truncated": False,
    "model_version": "v5.0",
    "score_semantics": "Advisory only.",
}


class FakeUrlService:
    URLIn = staticmethod(lambda url: url)
    MODEL = SimpleNamespace(thr_alert=0.9, thr_review=0.6)

    def check_url(self, url):
        if url == "bad.example":
            raise HTTPException(422, "Provide a valid public http(s) URL")
        if url == "boom.example":
            raise RuntimeError("secret C:/models/path")
        if url == "valueerror.example":
            raise ValueError("secret C:/models/path")
        if url == "slow.example":
            time.sleep(0.5)
        return URL_RESULT


class FakeEmail:
    def predict(self, subject, body):
        if not body.strip():
            raise ValueError("empty email")
        if body == "boom":
            raise RuntimeError("secret C:/models/path")
        return EMAIL_RESULT


def missing(*_):
    raise FileNotFoundError("C:/models/nope")


@pytest.fixture(autouse=True)
def fresh_limits():
    runtime.limiter.reset()


def client(monkeypatch, url=True, email=True):
    monkeypatch.setattr(runtime, "load_url_model", (lambda: (FakeUrlService(), "url-v")) if url else missing)
    monkeypatch.setattr(runtime, "load_email_model", (lambda: (FakeEmail(), "email-v")) if email else missing)
    return TestClient(main.create_app())


@pytest.mark.parametrize(
    "url,email,status,code",
    [(True, True, "ready", 200), (True, False, "degraded", 200), (False, True, "degraded", 200), (False, False, "down", 503)],
)
def test_health_reports_each_model(monkeypatch, url, email, status, code):
    with client(monkeypatch, url, email) as c:
        r = c.get("/api/health")
    assert r.status_code == code
    assert r.json()["status"] == status and r.json()["url_model"] is url and r.json()["email_model"] is email


def test_model_info_reports_only_loaded_models(monkeypatch):
    monkeypatch.delenv("MLPHIL_URL_BUNDLE", raising=False)  # stand-in models: no real report on disk
    with client(monkeypatch, email=False) as c:
        assert c.get("/api/model-info").json() == {
            "url": {"version": "url-v", "thr_high": 90.0, "thr_medium": 60.0, "metrics": None},
            "email": None,
        }
    with client(monkeypatch, url=False) as c:
        assert c.get("/api/model-info").json()["url"] is None
    with client(monkeypatch, url=False, email=False) as c:
        assert c.get("/api/model-info").status_code == 503


def test_model_info_reads_url_report_from_the_bundle(monkeypatch, tmp_path):
    (tmp_path / "final_report.json").write_text(json.dumps({
        "verdict": "ADVISORY_WITH_CAVEATS",
        "criteria": {"ext phishing recall >= 0.80": {"value": 0.84, "target": 0.8, "passed": True}},
        "results": [
            {"split": "ext_test", "cohort": "OpenPhish_feed", "metric": "recall", "n": 152, "rate_HIGH": 0.81, "ci_lo": 0.74, "ci_hi": 0.86},
            {"split": "ext_test", "cohort": "Tranco_roots", "metric": "false_alert", "n": 1268, "rate_HIGH": 0.008, "ci_lo": 0.004, "ci_hi": 0.014},
            {"split": "ext_dev", "cohort": "Tranco_roots", "metric": "false_alert", "n": 1, "rate_HIGH": 0.5},
        ],
    }))
    monkeypatch.setenv("MLPHIL_URL_BUNDLE", str(tmp_path))
    with client(monkeypatch, email=False) as c:
        metrics = c.get("/api/model-info").json()["url"]["metrics"]
    assert metrics["verdict"] == "ADVISORY_WITH_CAVEATS"
    assert metrics["criteria"] == [{"name": "ext phishing recall >= 0.80", "value": 0.84, "target": 0.8, "passed": True}]
    assert [r["cohort"] for r in metrics["results"]] == ["OpenPhish_feed", "Tranco_roots"]  # dev rows left out
    assert metrics["results"][0]["ci95"] == [0.74, 0.86]


def test_no_network_guard_still_blocks_real_connections(monkeypatch):
    """conftest exempts asyncio's socket pair on Windows. Nothing else may get through."""
    def boom(*_, **__):
        raise AssertionError("network used")

    monkeypatch.setattr(socket.socket, "connect", boom)
    pair = socket.socketpair()
    for s in pair:
        s.close()
    with socket.socket() as s, pytest.raises(AssertionError):
        s.connect(("192.0.2.1", 80))


def test_missing_url_model_leaves_email_working(monkeypatch):
    with client(monkeypatch, url=False) as c:
        assert c.post("/api/check-url", json={"url": "example.com"}).status_code == 503
        assert c.post("/api/check-email", json={"body": "hello"}).status_code == 200


def test_missing_email_model_leaves_url_working(monkeypatch):
    with client(monkeypatch, email=False) as c:
        r = c.post("/api/check-email", json={"body": "hello"})
        assert r.status_code == 503
        assert r.json()["detail"] == {"verdict": "UNAVAILABLE", "message": "Email model not loaded."}
        assert c.post("/api/check-url", json={"url": "example.com"}).status_code == 200


def test_real_loaders_fail_closed_when_folders_are_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("MLPHIL_URL_BUNDLE", str(tmp_path / "none"))
    monkeypatch.setenv("MLPHIL_EMAIL_MODEL_DIR", str(tmp_path / "none"))
    with TestClient(main.create_app()) as c:
        assert c.get("/api/health").status_code == 503
        assert c.post("/api/check-url", json={"url": "example.com"}).status_code == 503


def test_email_loader_uses_code_from_the_model_folder(monkeypatch, tmp_path):
    (tmp_path / "email_preprocess.py").write_text(
        "class EmailClassifier:\n"
        "    cfg = {'trained': 'T'}\n"
        "    def __init__(self, d): pass\n"
        "    def predict(self, s, b): return {'verdict': 'SPAM'}\n"
    )
    monkeypatch.setenv("MLPHIL_EMAIL_MODEL_DIR", str(tmp_path))
    model, version = runtime.load_email_model()
    assert version == f"{tmp_path.name}, trained T"
    assert model.predict("", "x")["verdict"] == "SPAM"


def test_email_loader_rejects_a_bad_self_test(monkeypatch, tmp_path):
    (tmp_path / "email_preprocess.py").write_text(
        "class EmailClassifier:\n"
        "    def __init__(self, d): pass\n"
        "    def predict(self, s, b): return {'verdict': 'FINE'}\n"
    )
    monkeypatch.setenv("MLPHIL_EMAIL_MODEL_DIR", str(tmp_path))
    with pytest.raises(RuntimeError):
        runtime.load_email_model()


def test_email_response_gets_a_version_when_predict_has_none(monkeypatch):
    class NoVersion(FakeEmail):
        def predict(self, subject, body):
            return {k: v for k, v in EMAIL_RESULT.items() if k != "model_version"}

    with client(monkeypatch) as c:
        c.app.state.email_model = NoVersion()
        r = c.post("/api/check-email", json={"body": "hello"})
    assert r.json()["model_version"] == "email-v"


def test_url_returns_service_result_unchanged(monkeypatch):
    with client(monkeypatch) as c:
        r = c.post("/api/check-url", json={"url": "https://paypal.example/signin"})
    assert r.status_code == 200 and r.json() == URL_RESULT


@pytest.mark.parametrize(
    "value", ["", "   ", "javascript:alert(1)", "ftp://example.com/x", "mailto:a@example.com", "garbage", "not a url", "bad.example", "x" * 2049]
)
def test_url_rejects_invalid_input(monkeypatch, value):
    with client(monkeypatch) as c:
        assert c.post("/api/check-url", json={"url": value}).status_code == 422


@pytest.mark.parametrize("value", ["example.com", "example.com:8080/x", "http://192.0.2.10/a", "http://[2001:db8::1]/a", "example.com/?next=http://a.b"])
def test_url_accepts_web_addresses(monkeypatch, value):
    with client(monkeypatch) as c:
        assert c.post("/api/check-url", json={"url": value}).status_code == 200


def test_email_returns_prediction_unchanged(monkeypatch):
    with client(monkeypatch) as c:
        r = c.post("/api/check-email", json={"subject": "Hi", "body": "hello"})
    assert r.status_code == 200 and r.json() == EMAIL_RESULT


def test_email_invalid_input_is_422(monkeypatch):
    with client(monkeypatch) as c:
        empty = c.post("/api/check-email", json={"body": "  "})
        assert empty.status_code == 422 and empty.json()["detail"] == {"message": "empty email"}
        assert c.post("/api/check-email", json={}).status_code == 422
        assert c.post("/api/check-email", json={"body": "x" * 100_001}).status_code == 422
        assert c.post("/api/check-email", json={"subject": "x" * 1_001, "body": "hello"}).status_code == 422


@pytest.mark.parametrize(
    "path,payload,detail",
    [
        ("/api/check-url", {"url": "boom.example"}, "UNAVAILABLE"),
        ("/api/check-url", {"url": "valueerror.example"}, "UNAVAILABLE"),
        ("/api/check-email", {"body": "boom"}, {"verdict": "UNAVAILABLE", "message": "Analysis failed; try again."}),
    ],
)
def test_crash_is_503_and_leaks_nothing(monkeypatch, path, payload, detail):
    with client(monkeypatch) as c:
        r = c.post(path, json=payload)
    assert r.status_code == 503 and r.json() == {"detail": detail}


def test_timeout_is_503(monkeypatch):
    monkeypatch.setattr(runtime, "TIMEOUT_S", 0.01)
    with client(monkeypatch) as c:
        assert c.post("/api/check-url", json={"url": "slow.example"}).status_code == 503


def test_validation_error_does_not_echo_input(monkeypatch):
    with client(monkeypatch) as c:
        r = c.post("/api/check-url", json={"url": "secret-" + "x" * 3000})
    assert r.status_code == 422 and "secret-" not in r.text and "pydantic" not in r.text


def test_rate_limit_is_429_after_30(monkeypatch):
    with client(monkeypatch) as c:
        codes = [c.post("/api/check-url", json={"url": "example.com"}).status_code for _ in range(31)]
    assert codes[:30] == [200] * 30 and codes[30] == 429


def test_body_cap_is_413_with_and_without_content_length(monkeypatch):
    big = {"body": "x" * (257 * 1024)}
    with client(monkeypatch) as c:
        assert c.post("/api/check-email", json=big).status_code == 413
        chunked = c.post("/api/check-email", content=iter([b"x" * (257 * 1024)]), headers={"Content-Type": "application/json"})
    assert chunked.status_code == 413


def test_security_headers_and_cors(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://allowed.example,*")
    with client(monkeypatch) as c:
        post = c.post("/api/check-url", json={"url": "example.com"}, headers={"Origin": "http://allowed.example"})
        other = c.get("/api/health", headers={"Origin": "http://other.example"})
    assert post.headers["X-Content-Type-Options"] == "nosniff"
    assert post.headers["Referrer-Policy"] == "no-referrer"
    assert post.headers["Cache-Control"] == "no-store"
    assert post.headers["access-control-allow-origin"] == "http://allowed.example"
    assert "access-control-allow-origin" not in other.headers


def test_logs_never_contain_input(monkeypatch, caplog):
    caplog.set_level("INFO")
    with client(monkeypatch) as c:
        c.post("/api/check-url", json={"url": "secret-host.example"})
        c.post("/api/check-email", json={"body": "secret-body"})
        c.post("/api/check-email", json={"body": "boom"})
    assert "status=200" in caplog.text
    assert "secret" not in caplog.text and "C:/models" not in caplog.text

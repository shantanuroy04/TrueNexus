"""analyze-email and check-eml with stand-in models: link extraction, the overall rule,
partial failures, .eml handling. Real models are covered in test_email_real.py."""
from email.message import EmailMessage

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import main
from routers.combined import overall
from services import runtime
from services.url_extract import extract_urls

BANDS = {"high.example": "High", "medium.example": "Medium", "low.example": "Low"}


class FakeUrlService:
    def URLIn(self, url):
        return url

    def check_url(self, url):
        host = url.split("//")[-1].split("/")[0].removeprefix("www.")
        if host == "boom.example":
            raise RuntimeError("secret")
        if host == "bad.example":
            raise HTTPException(422, "Provide a valid public http(s) URL")
        band = BANDS.get(host, "Low")
        return {"model": "u", "band": band, "score": 1.0, "evidence": ["e"], "url_defanged": url.replace(".", "[.]"),
                "note": "n", "disclaimer": "d"}


class FakeEmail:
    def __init__(self, verdict="LEGITIMATE"):
        self.verdict = verdict

    def predict(self, subject, body):
        if not (subject.strip() or body.strip()):
            raise ValueError("empty email")
        if self.verdict == "CRASH":
            raise RuntimeError("secret")
        return {"prediction": self.verdict, "verdict": self.verdict, "confidence": 0.9,
                "probabilities": {"LEGITIMATE": 0.9, "SPAM": 0.05, "PHISHING": 0.05}, "truncated": False}


@pytest.fixture(autouse=True)
def fresh_limits():
    runtime.limiter.reset()


def client(monkeypatch, email=FakeEmail(), url=FakeUrlService()):
    monkeypatch.setattr(runtime, "load_url_model", lambda: (url, "url-v") if url else (None, None))
    monkeypatch.setattr(runtime, "load_email_model", lambda: (email, "email-v") if email else (None, None))
    return TestClient(main.create_app())


def analyze(c, body, subject="Hi"):
    return c.post("/api/analyze-email", json={"subject": subject, "body": body})


# ---- link extraction ----------------------------------------------------------------

def test_extracts_plain_links_and_html_hrefs_in_order():
    text = 'See www.a.example. Then <a href="https://b.example/x?y=1&amp;z=2">click</a> and http://c.example/p'
    assert extract_urls(text) == ["www.a.example", "https://b.example/x?y=1&z=2", "http://c.example/p"]


def test_dedupes_case_insensitively_keeping_first():
    assert extract_urls("http://a.example/X http://A.example/x http://a.example/X") == ["http://a.example/X"]


def test_skips_non_web_hrefs():
    assert extract_urls('<a href="mailto:x@y.example">m</a> <a href="#top">t</a> <a href="javascript:void(0)">j</a>') == []


def test_caps_at_20_links_and_reports_the_total(monkeypatch):
    body = " ".join(f"http://site{i}.example/" for i in range(34))
    with client(monkeypatch) as c:
        r = analyze(c, body).json()
    assert r["urls_found"] == 34 and r["urls_checked"] == 20 and r["urls_capped"] is True
    assert r["urls"][0]["url_defanged"].startswith("http://site0[.]example")


# ---- overall rule: one test per row ---------------------------------------------------

@pytest.mark.parametrize(
    "email,bands,expected",
    [
        ("PHISHING", ["Low"], "HIGH"),
        ("LEGITIMATE", ["Low", "High"], "HIGH"),
        ("SPAM", ["Low"], "MEDIUM"),
        ("LEGITIMATE", ["Medium"], "MEDIUM"),
        ("UNCERTAIN", ["Low"], "UNCERTAIN"),
        ("UNAVAILABLE", ["Low"], "UNAVAILABLE"),
        ("LEGITIMATE", ["Low", "UNAVAILABLE"], "UNAVAILABLE"),
        ("LEGITIMATE", ["Low"], "LOW"),
        ("LEGITIMATE", [], "LOW"),
        ("UNAVAILABLE", ["High"], "HIGH"),
    ],
)
def test_overall_rule(email, bands, expected):
    assert overall(email, bands) == expected


def test_worst_signal_wins_through_the_api(monkeypatch):
    with client(monkeypatch, email=FakeEmail("LEGITIMATE")) as c:
        r = analyze(c, "Normal note. http://low.example/a and http://high.example/b").json()
    assert r["overall"] == "HIGH"
    assert r["overall_reason"] == "Email classified LEGITIMATE; 1 of 2 links rated High"
    assert r["email"]["model_version"] == "email-v"


def test_failed_link_check_makes_it_unavailable_not_low(monkeypatch):
    with client(monkeypatch) as c:
        r = analyze(c, "See http://low.example/a and http://boom.example/b").json()
    assert r["overall"] == "UNAVAILABLE"
    assert r["urls"][1] == {"url_defanged": "hxxp://boom[.]example/b", "band": "UNAVAILABLE"}


def test_link_the_url_model_rejects_is_not_called_clean(monkeypatch):
    with client(monkeypatch) as c:
        r = analyze(c, "See http://bad.example/a").json()
    assert r["overall"] == "UNAVAILABLE"


def test_email_model_crash_makes_it_unavailable_not_low(monkeypatch):
    with client(monkeypatch, email=FakeEmail("CRASH")) as c:
        r = analyze(c, "See http://low.example/a").json()
    assert r["email"] == {"verdict": "UNAVAILABLE"} and r["overall"] == "UNAVAILABLE"


def test_missing_url_model_marks_links_unavailable(monkeypatch):
    with client(monkeypatch, url=None) as c:
        r = analyze(c, "See https://low.example/a").json()
    assert r["urls"] == [{"url_defanged": "hxxps://low[.]example/a", "band": "UNAVAILABLE"}]
    assert r["overall"] == "UNAVAILABLE"


def test_missing_email_model_still_checks_links(monkeypatch):
    with client(monkeypatch, email=None) as c:
        r = analyze(c, "See http://high.example/a").json()
    assert r["email"] == {"verdict": "UNAVAILABLE"} and r["overall"] == "HIGH"


def test_both_models_missing_is_503(monkeypatch):
    with client(monkeypatch, email=None, url=None) as c:
        assert analyze(c, "hello").status_code == 503


def test_no_links(monkeypatch):
    with client(monkeypatch) as c:
        r = analyze(c, "Just a note with no links.").json()
    assert r["urls"] == [] and r["overall"] == "LOW" and r["overall_reason"].endswith("no links found")


def test_empty_is_422(monkeypatch):
    with client(monkeypatch) as c:
        r = c.post("/api/analyze-email", json={"subject": " ", "body": "  "})
    assert r.status_code == 422 and r.json()["detail"] == {"message": "empty email"}


def test_rate_limited(monkeypatch):
    with client(monkeypatch) as c:
        codes = [analyze(c, "hi").status_code for _ in range(31)]
    assert codes[30] == 429


# ---- .eml upload ---------------------------------------------------------------------

def eml(body="Please verify at http://high.example/login", html=None, attachment=None, subject="Account notice"):
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, "a@example.com", "b@example.com"
    msg.set_content(body)
    if html is not None:
        msg.add_alternative(html, subtype="html")
    if attachment is not None:
        msg.add_attachment(attachment.encode(), maintype="text", subtype="plain", filename="notes.txt")
    return bytes(msg)


def upload(c, data, content_type="message/rfc822"):
    return c.post("/api/check-eml", content=data, headers={"Content-Type": content_type})


def test_eml_is_parsed_and_analyzed(monkeypatch):
    with client(monkeypatch) as c:
        r = upload(c, eml())
    assert r.status_code == 200
    j = r.json()
    assert j["parsed_subject"] == "Account notice" and j["overall"] == "HIGH" and j["urls_checked"] == 1


def test_eml_html_links_are_found_by_href(monkeypatch):
    html_part = '<p>Click <a href="http://high.example/x">your bank</a></p><script>bad()</script>'
    with client(monkeypatch) as c:
        j = upload(c, eml(body="plain part, no links", html=html_part)).json()
    assert j["urls_checked"] == 0  # plain part preferred when both exist
    msg = EmailMessage()
    msg["Subject"] = "Only html"
    msg.set_content(html_part, subtype="html")
    with client(monkeypatch) as c:
        j = upload(c, bytes(msg)).json()
    assert j["urls_checked"] == 1 and j["overall"] == "HIGH"


def test_eml_attachment_is_ignored(monkeypatch):
    seen = {}

    class Recording(FakeEmail):
        def predict(self, subject, body):
            seen["body"] = body
            return super().predict(subject, body)

    data = eml(body="Hello team, notes inside.", attachment="secret-attachment http://high.example/evil")
    with client(monkeypatch, email=Recording()) as c:
        j = upload(c, data).json()
    assert "secret-attachment" not in seen["body"]
    assert j["urls_checked"] == 0 and j["overall"] == "LOW"


def test_eml_over_2mb_is_413(monkeypatch):
    with client(monkeypatch) as c:
        assert upload(c, b"x" * (3 * 1024 * 1024)).status_code == 413


def test_eml_under_2mb_is_allowed_past_the_256kb_cap(monkeypatch):
    with client(monkeypatch) as c:
        assert upload(c, eml(body="hello " * 60_000)).status_code in (200, 422)


def test_non_eml_content_type_is_415(monkeypatch):
    with client(monkeypatch) as c:
        assert upload(c, b"%PDF-1.4 ...", content_type="application/pdf").status_code == 415


def test_file_that_is_not_an_email_is_422(monkeypatch):
    with client(monkeypatch) as c:
        r = upload(c, b"%PDF-1.4\x00\x01 binary junk")
    assert r.status_code == 422 and r.json()["detail"] == {"message": "This file does not look like an email."}


def test_eml_errors_leak_nothing(monkeypatch):
    with client(monkeypatch) as c:
        for r in (upload(c, b"\x00\x01"), upload(c, b"x", "text/plain")):
            assert "Traceback" not in r.text and "site-packages" not in r.text and ":\\" not in r.text

"""Accounts: signup, login, logout, sessions. Uses a temporary database; models not loaded."""
import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

import main
from routers import auth
from services import runtime

ALICE = {"name": "Alice", "email": "Alice@Example.com", "password": "correct horse battery"}


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "accounts.db"


@pytest.fixture
def c(monkeypatch, db_path):
    runtime.limiter.reset()
    monkeypatch.setenv("MLPHIL_DB_PATH", str(db_path))
    monkeypatch.setattr(runtime, "load_url_model", lambda: (None, None))
    monkeypatch.setattr(runtime, "load_email_model", lambda: (None, None))
    with TestClient(main.create_app()) as client:
        yield client


def rows(db_path, sql):
    with sqlite3.connect(db_path) as conn:
        return conn.execute(sql).fetchall()


def test_signup_logs_in_and_logout_ends_the_session(c):
    r = c.post("/api/auth/signup", json=ALICE)
    assert r.status_code == 201 and r.json() == {"name": "Alice", "email": "alice@example.com"}
    assert c.get("/api/auth/me").json() == {"name": "Alice", "email": "alice@example.com"}
    assert c.post("/api/auth/logout").status_code == 204
    assert c.get("/api/auth/me").status_code == 401


def test_login_works_with_any_email_case(c):
    c.post("/api/auth/signup", json=ALICE)
    c.post("/api/auth/logout")
    r = c.post("/api/auth/login", json={"email": " ALICE@example.com ", "password": ALICE["password"]})
    assert r.status_code == 200 and c.get("/api/auth/me").status_code == 200


def test_wrong_password_and_unknown_email_get_the_same_answer(c):
    c.post("/api/auth/signup", json=ALICE)
    c.post("/api/auth/logout")
    wrong = c.post("/api/auth/login", json={"email": ALICE["email"], "password": "not the password"})
    unknown = c.post("/api/auth/login", json={"email": "nobody@example.com", "password": "not the password"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "Email or password is incorrect."}
    assert "set-cookie" not in wrong.headers


def test_duplicate_email_is_409(c):
    c.post("/api/auth/signup", json=ALICE)
    r = c.post("/api/auth/signup", json={**ALICE, "email": "ALICE@example.com"})
    assert r.status_code == 409


@pytest.mark.parametrize(
    "change,message",
    [
        ({"name": "  "}, "Enter your name."),
        ({"email": "not-an-email"}, "Enter a valid email address."),
        ({"password": "short"}, "Password must be at least 8 characters."),
    ],
)
def test_signup_validation(c, change, message):
    r = c.post("/api/auth/signup", json={**ALICE, **change})
    assert r.status_code == 422 and r.json() == {"detail": message}


def test_password_and_token_are_never_stored_in_plain_text(c, db_path):
    r = c.post("/api/auth/signup", json=ALICE)
    token = r.cookies["mlphil_session"]
    (stored,) = rows(db_path, "SELECT password_hash FROM users")[0]
    assert stored.startswith("$argon2id$") and ALICE["password"] not in stored
    (token_hash,) = rows(db_path, "SELECT token_hash FROM sessions")[0]
    assert token_hash != token and token not in token_hash


def test_session_cookie_flags(c):
    cookie = c.post("/api/auth/signup", json=ALICE).headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "path=/api" in cookie


def test_cookie_is_secure_when_configured(c, monkeypatch):
    monkeypatch.setenv("MLPHIL_COOKIE_SECURE", "1")
    assert "secure" in c.post("/api/auth/signup", json=ALICE).headers["set-cookie"].lower()


def test_expired_session_is_rejected(c, db_path):
    c.post("/api/auth/signup", json=ALICE)
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE sessions SET expires_at = ?", (int(time.time()) - 1,))
    assert c.get("/api/auth/me").status_code == 401


def test_forged_cookie_is_rejected(c):
    c.post("/api/auth/signup", json=ALICE)
    c.cookies.clear()
    c.cookies.set("mlphil_session", "made-up-token")
    assert c.get("/api/auth/me").status_code == 401


def test_login_is_rate_limited(c):
    codes = [c.post("/api/auth/login", json={"email": "x@example.com", "password": "wrong-pass"}).status_code for _ in range(11)]
    assert codes[:10] == [401] * 10 and codes[10] == 429


def test_database_failure_leaves_checks_alone(monkeypatch, tmp_path):
    runtime.limiter.reset()
    monkeypatch.setenv("MLPHIL_DB_PATH", str(tmp_path))  # a folder, so SQLite cannot open it
    monkeypatch.setattr(runtime, "load_url_model", lambda: (None, None))
    monkeypatch.setattr(runtime, "load_email_model", lambda: (None, None))
    with TestClient(main.create_app()) as c:
        assert c.get("/api/health").json()["accounts"] is False
        assert c.post("/api/auth/signup", json=ALICE).status_code == 503
        assert c.get("/api/auth/me").status_code == 401


def test_logs_never_contain_account_details(c, caplog):
    caplog.set_level("INFO")
    c.post("/api/auth/signup", json=ALICE)
    c.post("/api/auth/login", json={"email": ALICE["email"], "password": "wrong-pass"})
    assert "alice" not in caplog.text.lower() and ALICE["password"] not in caplog.text


def test_delete_account_needs_the_password_and_removes_everything(c, db_path):
    c.post("/api/auth/signup", json=ALICE)
    assert c.post("/api/auth/delete-account", json={"password": "wrong-password"}).status_code == 401
    assert c.get("/api/auth/me").status_code == 200
    assert c.post("/api/auth/delete-account", json={"password": ALICE["password"]}).status_code == 204
    assert c.get("/api/auth/me").status_code == 401
    assert rows(db_path, "SELECT COUNT(*) FROM users") == [(0,)]
    assert rows(db_path, "SELECT COUNT(*) FROM sessions") == [(0,)]
    login = c.post("/api/auth/login", json={"email": ALICE["email"], "password": ALICE["password"]})
    assert login.status_code == 401


def test_delete_account_without_session_is_401(c):
    assert c.post("/api/auth/delete-account", json={"password": "anything-1"}).status_code == 401


def test_dummy_hash_is_a_real_hash():
    assert auth._DUMMY_HASH.startswith("$argon2id$")

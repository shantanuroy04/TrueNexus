"""Accounts: signup, login, logout, me.

Passwords are stored only as Argon2id hashes. A session is a random token in an HttpOnly,
SameSite=Strict cookie; the database keeps only its SHA-256, so a leaked database file
cannot be used to log in. Login gives one message for an unknown email and a wrong password.
"""
import hashlib
import os
import re
import secrets
import sqlite3
import time

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from services import db
from services.runtime import limiter

router = APIRouter(prefix="/api/auth")
AUTH_LIMIT = "10/minute"
COOKIE = "mlphil_session"
SESSION_SECONDS = 7 * 24 * 3600
BAD_LOGIN = "Email or password is incorrect."
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_hasher = PasswordHasher()
# Verified against when the email is unknown, so that case takes as long as a wrong password.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


class SignupIn(BaseModel):
    name: str = Field(max_length=80)
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)


class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)


def _require_db(request: Request):
    if not request.app.state.db_ready:
        raise HTTPException(503, "Accounts are unavailable right now.")


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _start_session(response: Response, user_id: int):
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    with db.connect() as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
        conn.execute("INSERT INTO sessions VALUES (?, ?, ?)", (_token_hash(token), user_id, now + SESSION_SECONDS))
    response.set_cookie(
        COOKIE,
        token,
        max_age=SESSION_SECONDS,
        httponly=True,
        samesite="strict",
        secure=os.environ.get("MLPHIL_COOKIE_SECURE") == "1",  # set to 1 when served over HTTPS
        path="/api",
    )


def current_user(request: Request):
    """The logged-in user as {"name", "email"}, or None. Use it to protect a route later."""
    token = request.cookies.get(COOKIE)
    if not token or not request.app.state.db_ready:
        return None
    with db.connect() as conn:
        row = conn.execute(
            "SELECT u.name, u.email FROM sessions s JOIN users u ON u.id = s.user_id "
            "WHERE s.token_hash = ? AND s.expires_at > ?",
            (_token_hash(token), int(time.time())),
        ).fetchone()
    return dict(row) if row else None


@router.post("/signup", status_code=201)
@limiter.limit(AUTH_LIMIT)
def signup(request: Request, response: Response, body: SignupIn):
    _require_db(request)
    name, email = body.name.strip(), body.email.strip().lower()
    if not name:
        raise HTTPException(422, "Enter your name.")
    if not _EMAIL.match(email):
        raise HTTPException(422, "Enter a valid email address.")
    if len(body.password) < 8:
        raise HTTPException(422, "Password must be at least 8 characters.")
    try:
        with db.connect() as conn:
            user_id = conn.execute(
                "INSERT INTO users (email, name, password_hash, created_at) VALUES (?, ?, ?, ?)",
                (email, name, _hasher.hash(body.password), int(time.time())),
            ).lastrowid
    except sqlite3.IntegrityError:
        raise HTTPException(409, "An account with this email already exists.") from None
    _start_session(response, user_id)
    return {"name": name, "email": email}


@router.post("/login")
@limiter.limit(AUTH_LIMIT)
def login(request: Request, response: Response, body: LoginIn):
    _require_db(request)
    email = body.email.strip().lower()
    with db.connect() as conn:
        row = conn.execute("SELECT id, name, email, password_hash FROM users WHERE email = ?", (email,)).fetchone()
    try:
        _hasher.verify(row["password_hash"] if row else _DUMMY_HASH, body.password)
    except (VerificationError, InvalidHashError):
        raise HTTPException(401, BAD_LOGIN) from None
    if row is None:
        raise HTTPException(401, BAD_LOGIN)
    if _hasher.check_needs_rehash(row["password_hash"]):
        with db.connect() as conn:
            conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (_hasher.hash(body.password), row["id"]))
    _start_session(response, row["id"])
    return {"name": row["name"], "email": row["email"]}


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE)
    if token and request.app.state.db_ready:
        with db.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))
    response.delete_cookie(COOKIE, path="/api", httponly=True, samesite="strict")


class DeleteIn(BaseModel):
    password: str = Field(max_length=128)


@router.post("/delete-account", status_code=204)
@limiter.limit(AUTH_LIMIT)
def delete_account(request: Request, response: Response, body: DeleteIn):
    """Needs the password again, so a left-open browser cannot delete the account."""
    _require_db(request)
    token = request.cookies.get(COOKIE)
    with db.connect() as conn:
        row = conn.execute(
            "SELECT u.id, u.password_hash FROM sessions s JOIN users u ON u.id = s.user_id "
            "WHERE s.token_hash = ? AND s.expires_at > ?",
            (_token_hash(token or ""), int(time.time())),
        ).fetchone()
    if row is None:
        raise HTTPException(401, "Not logged in.")
    try:
        _hasher.verify(row["password_hash"], body.password)
    except (VerificationError, InvalidHashError):
        raise HTTPException(401, "Password is incorrect.") from None
    with db.connect() as conn:
        conn.execute("DELETE FROM users WHERE id = ?", (row["id"],))  # sessions go with it (ON DELETE CASCADE)
    response.delete_cookie(COOKIE, path="/api", httponly=True, samesite="strict")


@router.get("/me")
def me(request: Request):
    user = current_user(request)
    if user is None:
        raise HTTPException(401, "Not logged in.")
    return user

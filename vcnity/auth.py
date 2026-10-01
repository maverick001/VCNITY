"""Sign-in. Passwords are stored hashed; signing in hands back a signed token that
expires after TOKEN_HOURS. The API checks the token on every request and takes
the role from the account, never from the request body.

Accounts are made with app/scripts/users.py. There is no sign-up page.
"""
from __future__ import annotations

import secrets

from itsdangerous import BadSignature, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

from .config import settings
from .models import Job, User

ROLES = ("facilitator", "community", "analyst", "client")
STAFF = ("facilitator", "analyst")  # see every job; the community and the client see one
TOKEN_HOURS = 12
MIN_PASSWORD = 6  # a local demo; raise it before real community data


def _serializer() -> URLSafeTimedSerializer:
    key_file = settings.home / "auth.key"
    if not key_file.exists():
        key_file.parent.mkdir(parents=True, exist_ok=True)
        key_file.write_text(secrets.token_hex(32), encoding="utf-8")
    return URLSafeTimedSerializer(key_file.read_text(encoding="utf-8").strip(), salt="vcnity-sign-in")


def create_user(session, username: str, password: str, role: str, job_id: int | None = None) -> User:
    username = username.strip().lower()
    if not username:
        raise ValueError("a username is required")
    if role not in ROLES:
        raise ValueError(f"role must be one of {', '.join(ROLES)}")
    if len(password) < MIN_PASSWORD:
        raise ValueError(f"a password needs at least {MIN_PASSWORD} characters")
    if role in STAFF:
        job_id = None
    elif job_id is None or session.get(Job, job_id) is None:
        raise ValueError(f"a {role} account belongs to one job — give an existing job id")
    if session.query(User).filter_by(username=username).one_or_none():
        raise ValueError(f"'{username}' already exists")
    user = User(username=username, password_hash=generate_password_hash(password), role=role, job_id=job_id)
    session.add(user)
    session.flush()
    return user


def set_password(session, username: str, password: str) -> User:
    user = session.query(User).filter_by(username=username.strip().lower()).one_or_none()
    if user is None:
        raise KeyError(username)
    if len(password) < MIN_PASSWORD:
        raise ValueError(f"a password needs at least {MIN_PASSWORD} characters")
    user.password_hash = generate_password_hash(password)
    session.flush()
    return user


def check_login(session, username: str, password: str) -> User | None:
    user = session.query(User).filter_by(username=(username or "").strip().lower()).one_or_none()
    if user is None or not check_password_hash(user.password_hash, password or ""):
        return None
    return user


def make_token(user: User) -> str:
    return _serializer().dumps({"u": user.id})


def user_from_token(session, token: str) -> User | None:
    """The account behind a token, or None if it's forged, expired, or the account is gone."""
    if not token:
        return None
    try:
        data = _serializer().loads(token, max_age=TOKEN_HOURS * 3600)
    except BadSignature:  # also covers SignatureExpired
        return None
    return session.get(User, int(data.get("u", 0)))


def as_dict(user: User) -> dict:
    return {"id": user.id, "username": user.username, "role": user.role, "job_id": user.job_id}

"""Thin HTTP client for the Flask API. The UI never touches the database."""
from __future__ import annotations

import os
from http.cookiejar import DefaultCookiePolicy

import httpx

API = os.environ.get("VCNITY_API_URL", "http://127.0.0.1:8100")
_TIMEOUT = 30.0
# One client for the whole UI server: a page refresh makes a dozen calls, and this keeps the connection open
# between them instead of opening a new one each time. httpx clients are safe to share across threads. It is
# shared by everyone signed in, so it keeps no cookies: who you are travels only in each call's token.
_client = httpx.Client(timeout=_TIMEOUT)
_client.cookies.jar.set_policy(DefaultCookiePolicy(allowed_domains=[]))


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _check(r: httpx.Response):
    if r.status_code >= 400:
        try:
            msg = r.json().get("error", r.text)
        except Exception:  # noqa: BLE001
            msg = r.text
        raise ApiError(r.status_code, msg)
    if r.headers.get("content-type", "").startswith("application/json"):
        return r.json()
    return r.content


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"} if token else {}


def get(path: str, token: str = "", **params):
    return _check(_client.get(API + path, params=params or None, headers=_auth(token)))


def post(path: str, json=None, token: str = ""):
    return _check(_client.post(API + path, json=json if json is not None else {}, headers=_auth(token)))


def patch(path: str, json=None, token: str = ""):
    return _check(_client.patch(API + path, json=json or {}, headers=_auth(token)))


def put(path: str, json=None, token: str = ""):
    return _check(_client.put(API + path, json=json or {}, headers=_auth(token)))


def delete(path: str, token: str = ""):
    return _check(_client.delete(API + path, headers=_auth(token)))


def upload_file(path: str, *, filename: str, content: bytes, level: int, consent_label: str, consent_scope: str,
                token: str = ""):
    """Multipart upload — used for adding a new source file to a job."""
    return _check(_client.post(
        API + path, headers=_auth(token), timeout=120.0,  # audio files can take a moment
        files={"file": (filename, content)},
        data={"level": str(level), "consent_label": consent_label, "consent_scope": consent_scope},
    ))


def ask(job_id: int, question: str, history: list[dict], token: str = ""):
    """A question can take a minute on a laptop CPU, so this waits longer than other calls."""
    return _check(_client.post(f"{API}/jobs/{job_id}/ask", json={"question": question, "history": history},
                               headers=_auth(token), timeout=300.0))


# Links the browser opens itself can't send a header, so they carry the token as ?t=.
def export_url(report_id: int, token: str = "") -> str:
    return f"{API}/reports/{report_id}/export?t={token}"


def image_url(art_id: int, token: str = "") -> str:
    return f"{API}/artefacts/{art_id}/image?t={token}"


def media_url(file_id: int, token: str = "") -> str:
    return f"{API}/files/{file_id}/media?t={token}"

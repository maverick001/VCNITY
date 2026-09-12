"""Thin HTTP client for the Flask API. The UI never touches the database."""
from __future__ import annotations

import os

import httpx

API = os.environ.get("VCNITY_API_URL", "http://127.0.0.1:8100")
_TIMEOUT = 30.0


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


def get(path: str, **params):
    with httpx.Client(timeout=_TIMEOUT) as c:
        return _check(c.get(API + path, params=params or None))


def post(path: str, json=None):
    with httpx.Client(timeout=_TIMEOUT) as c:
        return _check(c.post(API + path, json=json if json is not None else {}))


def patch(path: str, json=None):
    with httpx.Client(timeout=_TIMEOUT) as c:
        return _check(c.patch(API + path, json=json or {}))


def put(path: str, json=None):
    with httpx.Client(timeout=_TIMEOUT) as c:
        return _check(c.put(API + path, json=json or {}))


def upload_file(path: str, *, filename: str, content: bytes, level: int, consent_label: str, consent_scope: str):
    """Multipart upload — used for adding a new source file to a job."""
    with httpx.Client(timeout=120.0) as c:  # audio files can take a moment
        return _check(c.post(
            API + path,
            files={"file": (filename, content)},
            data={"level": str(level), "consent_label": consent_label, "consent_scope": consent_scope},
        ))


def export_url(report_id: int) -> str:
    return f"{API}/reports/{report_id}/export"


def image_url(art_id: int) -> str:
    return f"{API}/artefacts/{art_id}/image"

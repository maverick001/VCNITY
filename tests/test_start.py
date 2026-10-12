"""The launcher skips the dependency sync only when nothing it depends on has changed."""
import importlib.util
from pathlib import Path

import pytest


@pytest.fixture()
def start(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("start_under_test", Path(__file__).resolve().parents[1] / "start.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "VENV", tmp_path / "venv")
    monkeypatch.setattr(mod, "SYNC_STAMP", tmp_path / "sync.stamp")
    py = mod._venv_python()
    py.parent.mkdir(parents=True)
    py.write_text("")
    return mod


def test_syncs_when_there_is_no_stamp(start):
    assert start._needs_sync(False) is True


def test_skips_when_the_stamp_matches(start):
    start.SYNC_STAMP.write_text(start._deps_fingerprint(), encoding="utf-8")
    assert start._needs_sync(False) is False


def test_syncs_when_the_lock_changed(start):
    start.SYNC_STAMP.write_text("an older fingerprint", encoding="utf-8")
    assert start._needs_sync(False) is True


def test_force_flag_and_missing_venv_always_sync(start):
    start.SYNC_STAMP.write_text(start._deps_fingerprint(), encoding="utf-8")
    assert start._needs_sync(True) is True
    start._venv_python().unlink()
    assert start._needs_sync(False) is True

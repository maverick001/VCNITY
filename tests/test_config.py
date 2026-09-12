from pathlib import Path


def test_settings_defaults(monkeypatch):
    monkeypatch.delenv("VCNITY_DATA_DIR", raising=False)
    monkeypatch.delenv("VCNITY_SMALL_N", raising=False)
    monkeypatch.delenv("VCNITY_SAFETY_CONTACT", raising=False)
    from vcnity.config import load_settings

    s = load_settings()
    assert s.data_dir.name == "raw"
    assert s.small_n == 3
    assert s.allow_hosted is False
    assert s.safety_contact.startswith("UNSET")


def test_settings_env_override(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("VCNITY_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("VCNITY_SMALL_N", "5")
    from vcnity.config import load_settings

    s = load_settings()
    assert s.data_dir == tmp_path
    assert s.small_n == 5

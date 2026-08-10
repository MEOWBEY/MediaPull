"""Env editor: line-preserving parse/apply, backups, preview validation."""

from __future__ import annotations

from pathlib import Path

import app.admin as admin
from app.admin import (
    apply_env_updates,
    env_safety_warnings,
    parse_env,
    read_env,
    render_env,
)

SAMPLE = """# Production defaults
DEBUG=false
LOG_LEVEL=INFO

CORS_ORIGINS=*
GROQ_API_KEY=
"""


def _point(monkeypatch, tmp_path: Path) -> Path:
    env_file = tmp_path / ".env"
    monkeypatch.setattr(admin, "_env_file_path", lambda: env_file)
    return env_file


def test_parse_render_roundtrip() -> None:
    assert render_env(parse_env(SAMPLE)) == SAMPLE


def test_apply_preserves_comments_and_order(monkeypatch, tmp_path: Path) -> None:
    env_file = _point(monkeypatch, tmp_path)
    env_file.write_text(SAMPLE, encoding="utf-8")

    apply_env_updates(
        {
            "DEBUG": "true",
            "GROQ_API_KEY": "gsk_abc",
            "NEW_OPTION": "42",
            "LOG_LEVEL": None,
        }
    )
    text = env_file.read_text(encoding="utf-8")
    assert "# Production defaults" in text
    assert "DEBUG=true" in text
    assert "GROQ_API_KEY=gsk_abc" in text
    assert "NEW_OPTION=42" in text
    assert "LOG_LEVEL=" not in text
    assert "CORS_ORIGINS=*" in text
    # New key appended at the end, after the blank line.
    assert text.rstrip().endswith("NEW_OPTION=42")


def test_apply_creates_backup(monkeypatch, tmp_path: Path) -> None:
    env_file = _point(monkeypatch, tmp_path)
    env_file.write_text("DEBUG=false\n", encoding="utf-8")

    apply_env_updates({"DEBUG": "true"})
    backups = list(tmp_path.glob(".env.bak-*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "DEBUG=false\n"


def test_read_env_skips_comments(monkeypatch, tmp_path: Path) -> None:
    env_file = _point(monkeypatch, tmp_path)
    env_file.write_text(SAMPLE, encoding="utf-8")
    keys = [e["key"] for e in read_env() if e["key"]]
    assert keys == ["DEBUG", "LOG_LEVEL", "CORS_ORIGINS", "GROQ_API_KEY"]


def test_safety_warnings_cross_fields(monkeypatch, tmp_path: Path) -> None:
    _point(monkeypatch, tmp_path)
    warnings = env_safety_warnings({"WORKERS": "4", "DEBUG": "true"})
    messages = {w["key"]: w["message"] for w in warnings}
    assert messages["WORKERS"].startswith("Must stay 1")
    assert "Debug mode" in messages["DEBUG"]

    # Cross-field: turning transcribe on without a Groq key info-warns.
    info = [w for w in env_safety_warnings({"TRANSCRIBE_ENABLED": "true"}) if w["key"] == "TRANSCRIBE_ENABLED"]
    assert info and info[0]["type"] == "info"

    # The wildcard CORS warning fires on the *candidate* value, not the file.
    cors = [w for w in env_safety_warnings({"CORS_ORIGINS": "https://app.example.com", "DEBUG": "false"}) if w["key"] == "CORS_ORIGINS"]
    assert cors == []
"""CORS wildcard + credentials collision guard."""

from app.config import Settings, get_settings
from app.main import create_app


def _cors_options(app):
    for mw in app.user_middleware:
        if mw.cls.__name__ == "CORSMiddleware":
            return mw.kwargs
    raise AssertionError("CORSMiddleware not registered")


def test_wildcard_disables_credentials():
    """Default CORS_ORIGINS is '*', which browsers reject with credentials, so
    allow_credentials must be forced off in that case."""
    assert Settings().cors_origins == ["*"]
    opts = _cors_options(create_app())
    assert "*" in opts["allow_origins"]
    assert opts["allow_credentials"] is False


def test_pinned_origin_enables_credentials(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com")
    get_settings.cache_clear()
    # Rebind the module-level `settings` create_app reads.
    import app.config as cfg
    import app.main as main_mod

    monkeypatch.setattr(cfg, "settings", cfg.Settings())
    monkeypatch.setattr(main_mod, "settings", cfg.settings)

    opts = _cors_options(create_app())
    assert opts["allow_origins"] == ["https://app.example.com"]
    assert opts["allow_credentials"] is True
    get_settings.cache_clear()

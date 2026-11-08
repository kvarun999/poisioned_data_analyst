import importlib.util
import os

from app.main import resolve_execution_mode


def test_local_provider_uses_local_celesto_without_api_key(monkeypatch):
    monkeypatch.setenv("CELESTO_PROVIDER", "local")
    monkeypatch.delenv("CELESTO_API_KEY", raising=False)

    original = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object() if name == "celesto" else original(name))

    mode = resolve_execution_mode()

    assert mode["mode"] == "local_celesto"
    assert mode["celesto_api_key_present"] is False
    assert mode["celesto_sdk_available"] is True

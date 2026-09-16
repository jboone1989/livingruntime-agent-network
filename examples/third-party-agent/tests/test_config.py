from __future__ import annotations

import importlib.util
from pathlib import Path


def _agent_module():
    path = Path(__file__).resolve().parents[1] / "agent.py"
    spec = importlib.util.spec_from_file_location("public_third_party_agent", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_network_url_targets_reference_seed_a2a(monkeypatch):
    monkeypatch.delenv("NETWORK_URL", raising=False)
    assert _agent_module().network_url() == "http://127.0.0.1:8001/a2a"


def test_configured_network_url_is_normalized(monkeypatch):
    monkeypatch.setenv("NETWORK_URL", "https://network.livingruntime.com/a2a/")
    assert _agent_module().network_url() == "https://network.livingruntime.com/a2a"

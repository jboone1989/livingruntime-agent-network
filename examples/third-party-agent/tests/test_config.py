from __future__ import annotations

import importlib


def test_default_network_url_targets_reference_seed_a2a(monkeypatch):
    monkeypatch.delenv("NETWORK_URL", raising=False)
    agent = importlib.import_module("agent")
    assert agent.network_url() == "http://127.0.0.1:8001/a2a"


def test_configured_network_url_is_normalized(monkeypatch):
    monkeypatch.setenv("NETWORK_URL", "https://network.livingruntime.com/a2a/")
    agent = importlib.import_module("agent")
    assert agent.network_url() == "https://network.livingruntime.com/a2a"

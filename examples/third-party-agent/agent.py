"""Standalone Agent Network example using only the public Python SDK."""
from __future__ import annotations

import os
from pathlib import Path

import uvicorn
from starlette.applications import Starlette

from agent_network.a2a_card import signed_agent_card
from agent_network.a2a_server import A2AServer, HandlerResult
from agent_network.crypto import Identity
from agent_network.network import AgentNetwork

DEFAULT_PORT = 8110

SKILL = {
    "id": "demo.echo",
    "version": "1.0.0",
    "input_schema": {"type": "object"},
    "output_schema": {"type": "object"},
    "side_effects": "NONE",
}


def port() -> int:
    return int(os.environ.get("THIRD_PARTY_PORT", str(DEFAULT_PORT)))


def bind_host() -> str:
    return os.environ.get("THIRD_PARTY_BIND_HOST", os.environ.get("THIRD_PARTY_HOST", "127.0.0.1"))


def agent_id() -> str:
    return os.environ.get("THIRD_PARTY_AGENT_ID", "thirdparty.demo.001")


def network_url() -> str:
    return os.environ.get("NETWORK_URL", "http://127.0.0.1:8001").rstrip("/")


def public_base_url() -> str:
    configured = (os.environ.get("THIRD_PARTY_PUBLIC_URL") or "").strip()
    return configured.rstrip("/") if configured else f"http://127.0.0.1:{port()}"


def advertised_urls() -> tuple[str, str]:
    base = public_base_url()
    return f"{base}/.well-known/agent-card.json", f"{base}/a2a"


def identity_path() -> Path:
    default = Path(__file__).resolve().parent / ".state" / "identity.json"
    return Path(os.environ.get("THIRD_PARTY_IDENTITY", str(default)))


async def echo(payload: dict) -> HandlerResult:
    return HandlerResult(metadata={"echo": (payload.get("metadata") or {}).get("text") or "ok"})


def create_app() -> Starlette:
    identity_file = identity_path()
    identity_file.parent.mkdir(parents=True, exist_ok=True)
    identity = Identity.load_or_create(identity_file, agent_id())
    card_url, endpoint = advertised_urls()
    card = signed_agent_card(
        identity=identity,
        name="Third-party demo",
        description="Independent Agent using the Agent Network SDK and official A2A transport.",
        url=endpoint,
        skills=[{"id": "demo.echo", "name": "echo", "description": "Echo a payload"}],
    )
    mesh = AgentNetwork(
        identity=identity,
        seeds=[network_url()],
        agent_card_url=card_url,
        endpoint=endpoint,
        capabilities=[SKILL],
    )
    server = A2AServer(identity=identity, card=card, handlers={"demo.echo": echo})
    return server.starlette_app(on_start=mesh.join)


def run() -> None:
    uvicorn.run(create_app(), host=bind_host(), port=port())


if __name__ == "__main__":
    run()

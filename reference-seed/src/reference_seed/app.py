from __future__ import annotations

import os
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import uvicorn

from agent_network.a2a_card import signed_agent_card
from agent_network.a2a_server import A2AServer, HandlerResult
from agent_network.capability import CapabilityDescriptor, version_matches
from agent_network.crypto import Identity, verify_object
from agent_network.models import utc_now


@dataclass
class Entry:
    agent_id: str
    public_key: str
    agent_card_url: str
    endpoint: str
    capabilities: list[dict[str, Any]]
    availability: str
    lease_expires_at: float
    last_seen: float


class ReferenceDirectory:
    def __init__(self) -> None:
        self.agents: dict[str, Entry] = {}

    def put(self, entry: Entry) -> None:
        self.agents[entry.agent_id] = entry

    def get(self, agent_id: str) -> Entry | None:
        return self.agents.get(agent_id)

    def discover(self, capability: str, version: str | None, limit: int) -> list[dict[str, Any]]:
        now = time.time()
        rows: list[dict[str, Any]] = []
        for entry in self.agents.values():
            if entry.lease_expires_at <= now or entry.availability != "AVAILABLE":
                continue
            descriptor = None
            for raw in entry.capabilities:
                cap = CapabilityDescriptor.from_value(raw)
                if cap.id == capability and version_matches(cap.version, version):
                    descriptor = cap
                    break
            if descriptor is None:
                continue
            rows.append({
                "agent_id": entry.agent_id,
                "public_key": entry.public_key,
                "agent_card_url": entry.agent_card_url,
                "endpoint": entry.endpoint,
                "network_id": "reference.local",
                "reachability": "REACHABLE",
                "availability": entry.availability,
                "last_seen": entry.last_seen,
                "lease_expires_at": entry.lease_expires_at,
                "capability": descriptor.to_dict(),
            })
        rows.sort(key=lambda row: (-float(row["last_seen"]), str(row["agent_id"])))
        return rows[:limit]


def _data(payload: dict[str, Any]) -> dict[str, Any]:
    for part in (payload.get("message") or {}).get("parts") or []:
        if part.get("kind") == "data" and isinstance(part.get("data"), dict):
            return dict(part["data"])
    return {}


class Handlers:
    def __init__(self, directory: ReferenceDirectory | None = None) -> None:
        self.directory = directory or ReferenceDirectory()

    async def join(self, payload: dict[str, Any]) -> HandlerResult:
        body = _data(payload)
        agent_id = str(body.get("agent_id") or "")
        public_key = str(body.get("public_key") or "")
        signature = str(body.get("signature") or "")
        if not agent_id or not public_key or not signature or not verify_object(public_key, body, signature):
            return HandlerResult(status="failed", error_code="IDENTITY_INVALID", message="signed announce required")
        lease = max(30, min(int(body.get("requested_lease_seconds") or 1800), 7200))
        now = time.time()
        entry = Entry(
            agent_id=agent_id,
            public_key=public_key,
            agent_card_url=str(body.get("agent_card_url") or ""),
            endpoint=str(body.get("endpoint") or ""),
            capabilities=[CapabilityDescriptor.from_value(item).to_dict() for item in (body.get("capabilities") or [])],
            availability=str((body.get("availability") or {}).get("status") or "AVAILABLE"),
            lease_expires_at=now + lease,
            last_seen=now,
        )
        known = self.directory.get(agent_id)
        if known is not None and known.public_key != public_key:
            return HandlerResult(status="failed", error_code="IDENTITY_INVALID", message="public key mismatch")
        self.directory.put(entry)
        return HandlerResult(metadata={"network_id": "reference.local", "agent_id": agent_id, "lease_seconds": lease, "lease_expires_at": entry.lease_expires_at})

    async def renew(self, payload: dict[str, Any]) -> HandlerResult:
        body = _data(payload)
        agent_id = str(body.get("agent_id") or "")
        entry = self.directory.get(agent_id)
        if entry is None or not verify_object(entry.public_key, body, str(body.get("signature") or "")):
            return HandlerResult(status="failed", error_code="IDENTITY_INVALID")
        entry.last_seen = time.time()
        entry.lease_expires_at = entry.last_seen + 1800
        return HandlerResult(metadata={"lease_expires_at": entry.lease_expires_at})

    async def leave(self, payload: dict[str, Any]) -> HandlerResult:
        body = _data(payload)
        agent_id = str(body.get("agent_id") or "")
        entry = self.directory.get(agent_id)
        if entry is None or not verify_object(entry.public_key, body, str(body.get("signature") or "")):
            return HandlerResult(status="failed", error_code="IDENTITY_INVALID")
        entry.availability = "OFFLINE"
        entry.lease_expires_at = time.time()
        return HandlerResult(metadata={"agent_id": agent_id})

    async def discover(self, payload: dict[str, Any]) -> HandlerResult:
        body = _data(payload)
        criteria = body.get("criteria") or {}
        capability = str(criteria.get("capability") or "")
        if not capability:
            return HandlerResult(status="failed", error_code="INVALID_REQUEST", message="capability required")
        rows = self.directory.discover(capability, criteria.get("version"), int(body.get("max_results") or 10))
        return HandlerResult(metadata={"query_id": body.get("query_id"), "agents": rows, "timestamp": utc_now()})

    async def report_unreachable(self, payload: dict[str, Any]) -> HandlerResult:
        return HandlerResult(metadata={"accepted": True})

    def skills(self) -> dict[str, Any]:
        return {
            "network.join": self.join,
            "network.announce": self.join,
            "network.renew": self.renew,
            "network.leave": self.leave,
            "network.discover": self.discover,
            "network.report_unreachable": self.report_unreachable,
        }


def create_app():
    root = Path(os.environ.get("REFERENCE_SEED_STATE", ".reference-seed"))
    root.mkdir(parents=True, exist_ok=True)
    identity = Identity.load_or_create(root / "identity.json", os.environ.get("REFERENCE_SEED_AGENT_ID", "seed.reference.local"))
    endpoint = os.environ.get("REFERENCE_SEED_PUBLIC_URL", "http://127.0.0.1:8001/a2a")
    card = signed_agent_card(
        identity=identity,
        name="LivingRuntime Reference Seed",
        description="Minimal discovery Seed for interoperability and local development.",
        url=endpoint,
        network_id="reference.local",
        skills=[
            {"id": "network.join", "name": "Join"},
            {"id": "network.renew", "name": "Renew"},
            {"id": "network.leave", "name": "Leave"},
            {"id": "network.discover", "name": "Discover"},
        ],
    )
    return A2AServer(identity=identity, card=card, handlers=Handlers().skills()).starlette_app()


def run() -> None:
    uvicorn.run(create_app(), host=os.environ.get("REFERENCE_SEED_HOST", "127.0.0.1"), port=int(os.environ.get("REFERENCE_SEED_PORT", "8001")))

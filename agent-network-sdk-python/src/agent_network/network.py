from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from agent_network.a2a_client import A2AClient
from agent_network.client import Peer
from agent_network.crypto import Identity, canonical_json, sha256_hex, unsigned_payload
from agent_network.errors import NetworkError, NoAvailableAgent
from agent_network.models import AgentSummary, utc_now


@dataclass(frozen=True)
class DiscoveryResult:
    query_id: str
    capability: str
    agents: list["DiscoveredAgent"]
    observed_at: str


class DiscoveredAgent:
    def __init__(self, data: dict[str, Any]) -> None:
        self.agent_id = str(data["agent_id"])
        self.agent_card_url = str(data.get("agent_card_url") or "")
        self.endpoint = data.get("endpoint")
        self.network_id = data.get("network_id")
        self.reachability = data.get("reachability")
        self.availability = data.get("availability")
        self.public_key = data.get("public_key")
        self.raw = dict(data)

    def as_summary(self) -> AgentSummary:
        return AgentSummary(
            agent_id=self.agent_id,
            name=self.agent_id,
            agent_card_url=self.agent_card_url,
            endpoint=self.endpoint,
            online=self.reachability == "REACHABLE",
            public_key=self.public_key,
            raw=self.raw,
        )


class AgentNetwork:
    """Minimal public Seed client. Discovery is indirect; Agent-to-Agent work is direct."""

    def __init__(
        self,
        *,
        identity: Identity,
        seeds: list[str],
        agent_card_url: str,
        endpoint: str,
        capabilities: list[Any],
        timeout: float = 30.0,
        lease_seconds: int = 1800,
    ) -> None:
        from agent_network.capability import CapabilityDescriptor

        self.identity = identity
        self.seeds = [seed.rstrip("/") for seed in seeds]
        self.agent_card_url = agent_card_url
        self.endpoint = endpoint
        self.capabilities = [CapabilityDescriptor.from_value(item).to_dict() for item in capabilities]
        self.timeout = timeout
        self.lease_seconds = lease_seconds
        self._clients: dict[str, A2AClient] = {}
        self._joined: set[str] = set()
        self._renew_task: asyncio.Task | None = None

    async def _seed_client(self, seed: str) -> A2AClient:
        client = self._clients.get(seed)
        if client is not None:
            return client
        client = A2AClient(seed)
        self._clients[seed] = client
        return client

    async def _message_any(self, message: dict[str, Any]) -> dict[str, Any]:
        last: Exception | None = None
        ordered = list(self._joined) + [s for s in self.seeds if s not in self._joined]
        for seed in ordered:
            try:
                return await (await self._seed_client(seed)).message_send(message)
            except Exception as exc:  # noqa: BLE001
                last = exc
        raise NetworkError("NO_SEED", str(last) if last else "no reachable Seed")

    def _announce_body(self, *, availability: str = "AVAILABLE", accept: bool = True) -> dict[str, Any]:
        policy = self.identity.recovery_policy()
        body: dict[str, Any] = {
            "type": "network.announce",
            "protocol_version": "0.1",
            "agent_id": self.identity.agent_id,
            "key_id": self.identity.key_id,
            "revision": self.identity.revision,
            "public_key": self.identity.public_key,
            "agent_card_url": self.agent_card_url,
            "endpoint": self.endpoint,
            "interfaces": [{"type": "DIRECT", "protocol": "a2a", "version": "1.0", "transport": "http", "endpoint": self.endpoint}],
            "capabilities": self.capabilities,
            "availability": {"accept_new_tasks": accept, "status": availability},
            "requested_lease_seconds": self.lease_seconds,
            "timestamp": utc_now(),
            "nonce": uuid4().hex,
            "recovery_policy": policy,
        }
        body["enrollment"] = self.identity.enrollment_message(
            recovery_policy_hash=sha256_hex(canonical_json(unsigned_payload(policy)))
        )
        body["signature"] = self.identity.sign_object(body)
        return body

    async def join(self) -> dict[str, Any]:
        last: Exception | None = None
        for seed in self.seeds:
            try:
                task = await (await self._seed_client(seed)).message_send({
                    "role": "user",
                    "parts": [{"kind": "data", "data": self._announce_body()}],
                    "metadata": {"capability": "network.join"},
                })
                if (task.get("status") or {}).get("state") != "completed":
                    raise NetworkError((task.get("metadata") or {}).get("error") or "REJECTED")
                self._joined.add(seed)
                self._start_renew()
                return task.get("metadata") or {}
            except Exception as exc:  # noqa: BLE001
                last = exc
        raise NetworkError("NO_SEED", str(last) if last else "join failed")

    async def renew(self) -> dict[str, Any]:
        if not self._joined:
            return await self.join()
        body = {"type": "network.renew", "agent_id": self.identity.agent_id, "timestamp": utc_now()}
        body["signature"] = self.identity.sign_object(body)
        task = await self._message_any({"role": "user", "parts": [{"kind": "data", "data": body}], "metadata": {"capability": "network.renew"}})
        if (task.get("status") or {}).get("state") != "completed":
            raise NetworkError("RENEW_FAILED", str(task.get("metadata") or {}))
        return task.get("metadata") or {}

    async def leave(self) -> dict[str, Any]:
        body = {"type": "network.leave", "agent_id": self.identity.agent_id, "timestamp": utc_now()}
        body["signature"] = self.identity.sign_object(body)
        task = await self._message_any({"role": "user", "parts": [{"kind": "data", "data": body}], "metadata": {"capability": "network.leave"}})
        self._joined.clear()
        if self._renew_task is not None:
            self._renew_task.cancel()
            self._renew_task = None
        return task.get("metadata") or {}

    async def discover_with_context(self, capability: str, *, max_results: int = 10, version: str | None = None) -> DiscoveryResult:
        query_id = f"q-{uuid4().hex[:10]}"
        criteria: dict[str, Any] = {"capability": capability, "availability": "AVAILABLE"}
        if version:
            criteria["version"] = version
        body = {
            "type": "network.discover",
            "query_id": query_id,
            "requester_agent_id": self.identity.agent_id,
            "criteria": criteria,
            "max_results": max_results,
            "timestamp": utc_now(),
        }
        body["signature"] = self.identity.sign_object(body)
        task = await self._message_any({"role": "user", "parts": [{"kind": "data", "data": body}], "metadata": {"capability": "network.discover"}})
        metadata = task.get("metadata") or {}
        return DiscoveryResult(
            query_id=str(metadata.get("query_id") or query_id),
            capability=capability,
            agents=[DiscoveredAgent(row) for row in (metadata.get("agents") or [])],
            observed_at=str(metadata.get("timestamp") or body["timestamp"]),
        )

    async def discover(self, capability: str, *, max_results: int = 10, version: str | None = None) -> list[DiscoveredAgent]:
        return (await self.discover_with_context(capability, max_results=max_results, version=version)).agents

    async def require(self, capability: str, version: str | None = None) -> DiscoveredAgent:
        rows = await self.discover(capability, version=version)
        if not rows:
            raise NoAvailableAgent(capability)
        return rows[0]

    require_agent = require

    async def connect(self, agent: DiscoveredAgent | AgentSummary) -> Peer:
        import httpx
        from agent_network.a2a_card import resolve_a2a_url

        summary = agent.as_summary() if isinstance(agent, DiscoveredAgent) else agent
        async with httpx.AsyncClient(timeout=self.timeout) as http:
            card = (await http.get(summary.agent_card_url)).json() if summary.agent_card_url else {}
        endpoint = resolve_a2a_url(card) or summary.endpoint
        if not endpoint:
            raise NetworkError("NO_ENDPOINT", f"{summary.agent_id} has no A2A URL")
        return Peer(self, summary, card, endpoint)

    async def report_unreachable(self, agent_id: str, reason: str = "connection_failed") -> None:
        body = {"type": "network.report_unreachable", "agent_id": agent_id, "reporter_agent_id": self.identity.agent_id, "reason": reason, "timestamp": utc_now()}
        body["signature"] = self.identity.sign_object(body)
        try:
            await self._message_any({"role": "user", "parts": [{"kind": "data", "data": body}], "metadata": {"capability": "network.report_unreachable"}})
        except Exception:
            return

    def _start_renew(self) -> None:
        if self._renew_task is not None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        interval = max(30, int(self.lease_seconds * 0.6))
        self._renew_task = loop.create_task(self._renew_loop(interval))

    async def _renew_loop(self, interval: int) -> None:
        while True:
            await asyncio.sleep(interval)
            try:
                await self.renew()
            except Exception:
                continue

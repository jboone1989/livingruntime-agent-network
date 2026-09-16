import asyncio

from agent_network.crypto import Identity
from agent_network.models import utc_now
from reference_seed.app import Handlers


def envelope(body, capability):
    return {"message": {"parts": [{"kind": "data", "data": body}]}, "metadata": {"capability": capability}, "task_id": "t1"}


def test_signed_join_and_discovery():
    async def run():
        identity = Identity.generate("agent.example.001")
        body = {
            "type": "network.announce",
            "agent_id": identity.agent_id,
            "public_key": identity.public_key,
            "agent_card_url": "https://agent.example/.well-known/agent-card.json",
            "endpoint": "https://agent.example/a2a",
            "capabilities": [{"id": "demo.echo", "version": "1.0.0"}],
            "availability": {"status": "AVAILABLE"},
            "requested_lease_seconds": 120,
            "timestamp": utc_now(),
        }
        body["signature"] = identity.sign_object(body)
        handlers = Handlers()
        joined = await handlers.join(envelope(body, "network.join"))
        assert joined.status == "completed"

        query = {"type": "network.discover", "query_id": "q1", "criteria": {"capability": "demo.echo"}, "max_results": 5, "timestamp": utc_now()}
        result = await handlers.discover(envelope(query, "network.discover"))
        assert result.metadata["agents"][0]["agent_id"] == identity.agent_id
    asyncio.run(run())


def test_rejects_unsigned_join():
    async def run():
        identity = Identity.generate("agent.bad.001")
        body = {"agent_id": identity.agent_id, "public_key": identity.public_key}
        result = await Handlers().join(envelope(body, "network.join"))
        assert result.status == "failed"
        assert result.error_code == "IDENTITY_INVALID"
    asyncio.run(run())

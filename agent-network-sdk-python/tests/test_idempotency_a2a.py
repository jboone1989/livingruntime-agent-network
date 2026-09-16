from __future__ import annotations

from agent_network.a2a_server import A2AServer, HandlerResult
from agent_network.crypto import Identity
from starlette.testclient import TestClient


def test_idempotent_skill_runs_once() -> None:
    ident = Identity.generate("coding.local.001")
    calls = {"n": 0}

    async def mutate(payload):
        calls["n"] += 1
        return HandlerResult(metadata={"receipt": "once"})

    server = A2AServer(
        identity=ident,
        card={"name": "t", "url": "http://x/a2a", "skills": []},
        handlers={"crypto.trade.execute": mutate},
    )
    http = TestClient(server.starlette_app())
    msg = {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "message/send",
        "params": {
            "message": {
                "messageId": "m1",
                "role": "user",
                "parts": [{"kind": "text", "text": "trade"}],
                "metadata": {
                    "capability": "crypto.trade.execute",
                    "idempotency_key": "arb-cai-codefix-20260818-001",
                    "requester_agent_id": "arb.cai.001",
                },
            }
        },
    }
    first = http.post("/a2a", json=msg).json()["result"]
    second = http.post("/a2a", json=msg).json()["result"]
    assert first["metadata"]["receipt"] == second["metadata"]["receipt"] == "once"
    assert calls["n"] == 1

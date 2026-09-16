from __future__ import annotations

from agent_network.a2a_server import A2AServer, HandlerResult
from agent_network.crypto import Identity
from starlette.testclient import TestClient


def test_duplicate_message_id_does_not_rerun_with_new_task_id() -> None:
    ident = Identity.generate("coding.local.001")
    calls = {"n": 0}

    async def mutate(payload):
        calls["n"] += 1
        return HandlerResult(metadata={"receipt": f"run-{calls['n']}"})

    server = A2AServer(
        identity=ident,
        card={"name": "t", "url": "http://x/a2a", "skills": []},
        handlers={"crypto.trade.execute": mutate},
    )
    http = TestClient(server.starlette_app())

    def msg(task_id: str) -> dict:
        return {
            "jsonrpc": "2.0",
            "id": "1",
            "method": "message/send",
            "params": {
                "message": {
                    "messageId": "same-wire-id",
                    "role": "user",
                    "parts": [{"kind": "text", "text": "trade"}],
                    "metadata": {
                        "capability": "crypto.trade.execute",
                        "task_id": task_id,
                        "requester_agent_id": "arb.cai.001",
                    },
                }
            },
        }

    first = http.post("/a2a", json=msg("task-a")).json()["result"]
    second = http.post("/a2a", json=msg("task-b")).json()["result"]
    assert calls["n"] == 1
    assert first["metadata"]["receipt"] == second["metadata"]["receipt"] == "run-1"

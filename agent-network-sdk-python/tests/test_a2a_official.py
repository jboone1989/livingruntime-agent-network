from __future__ import annotations

import asyncio

import httpx
from google.protobuf.json_format import MessageToDict, ParseDict
from starlette.testclient import TestClient

from a2a.client.card_resolver import parse_agent_card
from a2a.client.client import ClientConfig
from a2a.client.client_factory import ClientFactory
from a2a.types.a2a_pb2 import Message, Part, Role, SendMessageRequest, TaskState

from agent_network.a2a_card import signed_agent_card
from agent_network.a2a_server import A2AServer, HandlerResult
from agent_network.crypto import Identity


def test_official_a2a_sdk_send_message() -> None:
    ident = Identity.generate("echo.local.001")
    card = signed_agent_card(
        identity=ident,
        name="echo",
        description="echo",
        url="http://test/a2a",
        skills=[{"id": "demo.echo", "name": "echo", "description": "echo"}],
    )

    async def echo(payload):
        return HandlerResult(metadata={"pong": payload["metadata"].get("ping"), "capability": payload["capability"]})

    server = A2AServer(identity=ident, card=card, handlers={"demo.echo": echo})
    app = server.starlette_app()
    well_known = TestClient(app).get("/.well-known/agent-card.json").json()
    official = parse_agent_card(well_known)
    assert official.supported_interfaces[0].protocol_binding == "JSONRPC"
    assert official.supported_interfaces[0].protocol_version == "1.0"
    bindings = {iface.protocol_binding for iface in official.supported_interfaces}
    assert "HTTP+JSON" in bindings

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            factory = ClientFactory(ClientConfig(streaming=False, httpx_client=client))
            a2a_client = factory.create(official)
            request = SendMessageRequest()
            request.message.CopyFrom(
                Message(message_id="m-official", role=Role.ROLE_USER, parts=[Part(text="hi")])
            )
            ParseDict({"capability": "demo.echo", "ping": "ok"}, request.message.metadata)
            events = []
            async for event in a2a_client.send_message(request):
                events.append(event)
            assert events
            task = events[0].task
            assert task.status.state == TaskState.TASK_STATE_COMPLETED
            meta = MessageToDict(task.metadata)
            assert meta["pong"] == "ok"

    asyncio.run(run())


def test_v03_message_send_still_works() -> None:
    ident = Identity.generate("echo.local.001")
    server = A2AServer(
        identity=ident,
        card={"name": "echo", "url": "http://test/a2a", "skills": []},
        handlers={"demo.echo": lambda payload: HandlerResult(metadata={"pong": True})},
    )
    http = TestClient(server.starlette_app())
    res = http.post(
        "/a2a",
        json={
            "jsonrpc": "2.0",
            "id": "1",
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"kind": "text", "text": "hi"}],
                    "metadata": {"capability": "demo.echo"},
                }
            },
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["result"]["status"]["state"] == "completed"
    assert body["result"]["metadata"]["pong"] is True


def test_http_json_message_send() -> None:
    ident = Identity.generate("echo.local.001")
    card = signed_agent_card(
        identity=ident,
        name="echo",
        description="echo",
        url="http://test/a2a",
        skills=[{"id": "demo.echo", "name": "echo", "description": "echo"}],
    )

    async def echo(payload):
        return HandlerResult(metadata={"pong": payload["metadata"].get("ping"), "capability": payload["capability"]})

    server = A2AServer(identity=ident, card=card, handlers={"demo.echo": echo})
    http = TestClient(server.starlette_app())
    res = http.post(
        "/message:send",
        headers={"A2A-Version": "1.0", "Content-Type": "application/json"},
        json={
            "message": {
                "messageId": "m-rest",
                "role": "ROLE_USER",
                "parts": [{"text": "hi"}],
                "metadata": {"capability": "demo.echo", "ping": "rest"},
            }
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    task = body.get("task") or body
    status = (task.get("status") or {})
    state = status.get("state")
    assert state in {"TASK_STATE_COMPLETED", "COMPLETED", "completed", 3, "3"}, body
    meta = task.get("metadata") or {}
    assert meta.get("pong") == "rest" or meta.get("fields", {}).get("pong") == "rest" or "rest" in str(meta)


def test_http_json_message_send() -> None:
    ident = Identity.generate("echo.local.001")
    server = A2AServer(
        identity=ident,
        card=signed_agent_card(
            identity=ident,
            name="echo",
            description="echo",
            url="http://test/a2a",
            skills=[{"id": "demo.echo", "name": "echo", "description": "echo"}],
        ),
        handlers={"demo.echo": lambda payload: HandlerResult(metadata={"pong": "rest"})},
    )
    http = TestClient(server.starlette_app())
    res = http.post(
        "/message:send",
        headers={"A2A-Version": "1.0", "Content-Type": "application/json"},
        json={
            "message": {
                "messageId": "m-rest",
                "role": "ROLE_USER",
                "parts": [{"text": "hi"}],
                "metadata": {"capability": "demo.echo"},
            }
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    task = body.get("task") or body
    status = task.get("status") or {}
    state = str(status.get("state") or "")
    assert "COMPLETED" in state or state == "completed", body
    meta = task.get("metadata") or {}
    assert meta.get("pong") == "rest"

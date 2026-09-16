"""Bridge Network skill handlers onto the official A2A Python SDK (spec 1.0)."""
from __future__ import annotations

import json
from typing import Any, TYPE_CHECKING
from uuid import uuid4

from google.protobuf.json_format import MessageToDict, ParseDict
from a2a.client.card_resolver import parse_agent_card
from a2a.helpers.proto_helpers import new_task
from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes.jsonrpc_dispatcher import JsonRpcDispatcher
from a2a.server.routes.rest_routes import create_rest_routes
from a2a.server.tasks import InMemoryTaskStore
from starlette.routing import Mount
from a2a.types.a2a_pb2 import (
    AgentCard,
    Artifact,
    Message,
    Part,
    Role,
    Task,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)

if TYPE_CHECKING:
    from agent_network.a2a_server import A2AServer

_STATE_TO_PROTO = {
    "completed": TaskState.TASK_STATE_COMPLETED,
    "failed": TaskState.TASK_STATE_FAILED,
    "canceled": TaskState.TASK_STATE_CANCELED,
    "cancelled": TaskState.TASK_STATE_CANCELED,
    "submitted": TaskState.TASK_STATE_SUBMITTED,
    "working": TaskState.TASK_STATE_WORKING,
    "rejected": TaskState.TASK_STATE_REJECTED,
}

_PROTO_STATE_TO_WIRE = {
    "TASK_STATE_COMPLETED": "completed",
    "TASK_STATE_FAILED": "failed",
    "TASK_STATE_CANCELED": "canceled",
    "TASK_STATE_SUBMITTED": "submitted",
    "TASK_STATE_WORKING": "working",
    "TASK_STATE_REJECTED": "rejected",
    "TASK_STATE_INPUT_REQUIRED": "input-required",
    "TASK_STATE_AUTH_REQUIRED": "auth-required",
}


def restore_json_numbers(value: Any) -> Any:
    """Protobuf Struct stores numbers as float. Canonical JSON signatures need ints."""
    if isinstance(value, float) and value.is_integer() and abs(value) < 2**53:
        return int(value)
    if isinstance(value, dict):
        return {str(k): restore_json_numbers(v) for k, v in value.items()}
    if isinstance(value, list):
        return [restore_json_numbers(v) for v in value]
    return value


def jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def official_agent_card(card: dict[str, Any]) -> AgentCard:
    payload = json.loads(json.dumps(card, default=str))
    payload.setdefault("description", payload.get("name") or "agent")
    payload.setdefault("version", payload.get("version") or "0.2.0")
    payload.setdefault("defaultInputModes", ["text"])
    payload.setdefault("defaultOutputModes", ["text"])
    payload.setdefault("capabilities", {"streaming": False})
    skills = []
    for raw in payload.get("skills") or []:
        item = dict(raw)
        item.setdefault("id", item.get("name") or "skill")
        item.setdefault("name", item.get("id") or "skill")
        item.setdefault("description", item.get("name") or item["id"])
        item.setdefault("tags", [])
        skills.append(item)
    payload["skills"] = skills
    return parse_agent_card(payload)


def protobuf_message_to_dict(msg: Message) -> dict[str, Any]:
    parts: list[dict[str, Any]] = []
    for part in msg.parts:
        which = part.WhichOneof("content")
        if which == "text":
            parts.append({"kind": "text", "text": part.text})
        elif which == "data":
            data = MessageToDict(part.data)
            if not isinstance(data, dict):
                data = {"value": data}
            parts.append({"kind": "data", "data": restore_json_numbers(data)})
        elif which == "url":
            parts.append({"kind": "file", "file": {"uri": part.url, "mimeType": part.media_type}})
        elif which == "raw":
            parts.append({"kind": "file", "file": {"bytes": part.raw, "mimeType": part.media_type}})
    metadata: dict[str, Any] = {}
    if msg.HasField("metadata"):
        metadata = restore_json_numbers(MessageToDict(msg.metadata))
    role = "user" if msg.role in (Role.ROLE_USER, 1) else "agent"
    return {
        "messageId": msg.message_id,
        "role": role,
        "parts": parts,
        "metadata": metadata,
        "taskId": msg.task_id,
        "contextId": msg.context_id,
    }


def dict_to_protobuf_task(result: dict[str, Any], *, task_id: str, context_id: str) -> Task:
    state_name = str((result.get("status") or {}).get("state") or "completed")
    state = _STATE_TO_PROTO.get(state_name, TaskState.TASK_STATE_COMPLETED)
    artifacts: list[Artifact] = []
    for item in result.get("artifacts") or []:
        if not isinstance(item, dict):
            continue
        art = Artifact(
            artifact_id=str(item.get("artifactId") or item.get("artifact_id") or ""),
            name=str(item.get("name") or ""),
        )
        for part in item.get("parts") or []:
            proto = Part()
            if part.get("kind") == "text" or ("text" in part and "data" not in part):
                proto.text = str(part.get("text") or "")
            else:
                ParseDict(jsonable(part.get("data") or {}), proto.data)
            art.parts.append(proto)
        artifacts.append(art)
    task = new_task(task_id, context_id, state, artifacts=artifacts)
    meta = result.get("metadata")
    if isinstance(meta, dict) and meta:
        ParseDict(jsonable(meta), task.metadata)
    return task


def skill_message_to_send_params(message: dict[str, Any]) -> dict[str, Any]:
    parts: list[dict[str, Any]] = []
    for part in message.get("parts") or []:
        if part.get("kind") == "text" or ("text" in part and part.get("kind") != "data"):
            parts.append({"text": part.get("text") or ""})
        elif part.get("kind") == "data" or "data" in part:
            parts.append({"data": part.get("data") or {}})
        elif part.get("kind") == "file":
            file_obj = part.get("file") or {}
            if file_obj.get("uri"):
                parts.append({"url": file_obj["uri"], "mediaType": file_obj.get("mimeType") or ""})
            elif file_obj.get("bytes"):
                parts.append({"raw": file_obj["bytes"], "mediaType": file_obj.get("mimeType") or ""})
    role = str(message.get("role") or "user")
    proto_role = "ROLE_USER" if role.lower() in {"user", "role_user"} else "ROLE_AGENT"
    msg: dict[str, Any] = {
        "messageId": str(message.get("messageId") or message.get("message_id") or uuid4()),
        "role": proto_role,
        "parts": parts or [{"text": ""}],
    }
    if message.get("metadata"):
        msg["metadata"] = jsonable(message["metadata"])
    task_id = message.get("taskId") or message.get("task_id")
    if task_id:
        msg["taskId"] = str(task_id)
    context_id = message.get("contextId") or message.get("context_id")
    if context_id:
        msg["contextId"] = str(context_id)
    return {"message": msg}


def normalize_task_result(result: dict[str, Any] | None) -> dict[str, Any]:
    if not result:
        return {}
    task = result["task"] if isinstance(result.get("task"), dict) else result
    status = dict(task.get("status") or {})
    state = str(status.get("state") or "")
    status["state"] = _PROTO_STATE_TO_WIRE.get(state, state.replace("_", "-").lower() if state.startswith("TASK_STATE_") else state)
    artifacts = []
    for item in task.get("artifacts") or []:
        art = dict(item)
        parts = []
        for part in art.get("parts") or []:
            p = dict(part)
            if "kind" not in p:
                if "text" in p:
                    p["kind"] = "text"
                elif "data" in p:
                    p["kind"] = "data"
            if "data" in p:
                p["data"] = restore_json_numbers(p["data"])
            parts.append(p)
        art["parts"] = parts
        artifacts.append(art)
    out = dict(task)
    out["status"] = status
    out["artifacts"] = artifacts
    if isinstance(out.get("metadata"), dict):
        out["metadata"] = restore_json_numbers(out["metadata"])
    return out


def ensure_message_id(body: dict[str, Any]) -> None:
    params = body.get("params")
    if not isinstance(params, dict):
        return
    msg = params.get("message")
    if not isinstance(msg, dict):
        return
    if not msg.get("messageId") and not msg.get("message_id"):
        msg["messageId"] = str(uuid4())


class SkillAgentExecutor(AgentExecutor):
    def __init__(self, server: A2AServer) -> None:
        self.server = server

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        message = context.message
        skill_msg = protobuf_message_to_dict(message) if message is not None else {"parts": [], "metadata": {}, "role": "user"}
        metadata = dict(skill_msg.get("metadata") or {})
        if context.task_id:
            metadata["task_id"] = context.task_id
        skill_msg["metadata"] = metadata
        result = await self.server.handle_message(skill_msg)
        task = dict_to_protobuf_task(
            result,
            task_id=str(context.task_id or result.get("id") or uuid4()),
            context_id=str(context.context_id or ""),
        )
        await event_queue.enqueue_event(task)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        task_id = str(context.task_id or "")
        stored = self.server.tasks.get(task_id)
        if stored is not None:
            stored["status"] = {"state": "canceled"}
        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                task_id=task_id,
                context_id=str(context.context_id or ""),
                status=TaskStatus(state=TaskState.TASK_STATE_CANCELED),
                final=True,
            )
        )


def official_request_handler(server: A2AServer) -> DefaultRequestHandler:
    return DefaultRequestHandler(
        agent_executor=SkillAgentExecutor(server),
        task_store=InMemoryTaskStore(),
        agent_card=official_agent_card(server.card),
    )


def official_jsonrpc_dispatcher(server: A2AServer, handler: DefaultRequestHandler | None = None) -> JsonRpcDispatcher:
    return JsonRpcDispatcher(
        request_handler=handler or official_request_handler(server),
        enable_v0_3_compat=True,
    )


def official_rest_routes(server: A2AServer, handler: DefaultRequestHandler | None = None) -> list:
    routes = create_rest_routes(
        handler or official_request_handler(server),
        enable_v0_3_compat=False,
        path_prefix="",
    )
    return [route for route in routes if not isinstance(route, Mount)]


class BodyRequest:
    """Starlette Request stand-in that returns a pre-parsed JSON body."""

    def __init__(self, request: Any, body: dict[str, Any]) -> None:
        self._request = request
        self._body = body
        self.scope = request.scope
        self.headers = request.headers
        self.method = request.method
        self.url = request.url

    async def json(self) -> dict[str, Any]:
        return self._body

    def __getattr__(self, name: str) -> Any:
        return getattr(self._request, name)

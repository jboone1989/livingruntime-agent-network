from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

import httpx

from agent_network.a2a_official import normalize_task_result, skill_message_to_send_params
from agent_network.errors import NetworkError


def _origin(url: str) -> str:
    parts = urlsplit(url)
    if not parts.scheme:
        return "http://test"
    return f"{parts.scheme}://{parts.netloc}"


def _path(url: str) -> str:
    parts = urlsplit(url)
    return parts.path or "/"


class A2AClient:
    def __init__(self, endpoint: str, timeout: float = 120.0, transport: Any | None = None) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout
        self.transport = transport

    async def message_send(self, message: dict[str, Any]) -> dict[str, Any]:
        params = skill_message_to_send_params(message)
        try:
            result = await self._rpc("SendMessage", params, version="1.0")
            return normalize_task_result(result)
        except NetworkError as exc:
            if exc.code not in {"-32601", "MethodNotFoundError"}:
                raise
            result = await self._rpc("message/send", {"message": message}, version="0.3")
            return normalize_task_result(result)

    async def tasks_get(self, task_id: str) -> dict[str, Any]:
        try:
            result = await self._rpc("GetTask", {"id": task_id}, version="1.0")
            return normalize_task_result(result)
        except NetworkError:
            result = await self._rpc("tasks/get", {"id": task_id}, version="0.3")
            return normalize_task_result(result)

    async def tasks_cancel(self, task_id: str) -> dict[str, Any]:
        try:
            result = await self._rpc("CancelTask", {"id": task_id}, version="1.0")
            return normalize_task_result(result)
        except NetworkError:
            result = await self._rpc("tasks/cancel", {"id": task_id}, version="0.3")
            return normalize_task_result(result)

    async def _rpc(self, method: str, params: dict[str, Any], *, version: str | None = None) -> dict[str, Any]:
        payload = {"jsonrpc": "2.0", "id": "1", "method": method, "params": params}
        headers: dict[str, str] = {}
        if version:
            headers["A2A-Version"] = version
        client_kwargs: dict[str, Any] = {"timeout": self.timeout}
        target = self.endpoint
        if self.transport is not None:
            client_kwargs["transport"] = self.transport
            client_kwargs["base_url"] = _origin(self.endpoint)
            target = _path(self.endpoint)
        async with httpx.AsyncClient(**client_kwargs) as client:
            response = await client.post(target, json=payload, headers=headers)
            response.raise_for_status()
            body = response.json()
        if body.get("error"):
            err = body["error"]
            raise NetworkError(str(err.get("code", "A2A_ERROR")), str(err.get("message", "")))
        return body.get("result") or {}

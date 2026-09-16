"""A2A JSON-RPC server via the official a2a-sdk. Network is not in the message path."""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol
from uuid import uuid4

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from agent_network.crypto import Identity, file_sha256
from agent_network.errors import ErrorEnvelope
from agent_network.idempotency import IdempotencyStore
from agent_network.models import ArtifactManifest, TaskContract, new_id, utc_now

SkillHandler = Callable[[dict[str, Any]], Awaitable["SkillResult"] | "SkillResult"]


class SkillResult(Protocol):
    pass


@dataclass
class HandlerResult:
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    status: str = "completed"
    error_code: str | None = None
    message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    contract: TaskContract | None = None


class A2AServer:
    def __init__(
        self,
        *,
        identity: Identity,
        card: dict[str, Any],
        handlers: dict[str, SkillHandler],
        host: str = "127.0.0.1",
        port: int = 0,
    ) -> None:
        self.identity = identity
        self.card = card
        self.handlers = dict(handlers)
        self.host = host
        self.port = port
        self.tasks: dict[str, dict[str, Any]] = {}
        self.idempotency = IdempotencyStore()
        if "task.propose" not in self.handlers:
            self.handlers["task.propose"] = self._handle_propose
        self.artifact_blobs: dict[str, dict[str, Any]] = {}

    def card_with_url(self, url: str) -> dict[str, Any]:
        card = dict(self.card)
        card["url"] = url
        return card

    def starlette_app(
        self,
        on_start: Callable[[], Awaitable[None]] | None = None,
        extra_routes: list[Route] | None = None,
    ) -> Starlette:
        async def well_known(_: Request) -> Response:
            return JSONResponse(self.card)

        async def health(_: Request) -> Response:
            return JSONResponse({"ok": True, "agent_id": self.identity.agent_id})

        async def artifacts_get(request: Request) -> Response:
            from agent_network.artifact_ref import authorize_artifact_get

            aid = request.path_params["artifact_id"]
            blob = self.artifact_blobs.get(aid)
            if blob is None:
                return JSONResponse({"error": ErrorEnvelope.of("ARTIFACT_NOT_FOUND").to_dict()}, status_code=404)
            err, status = authorize_artifact_get(
                artifact_id=aid,
                headers=request.headers,
                allowed=blob.get("allowed") or set(),
                party_keys=blob.get("party_keys") or {},
            )
            if err is not None:
                return JSONResponse({"error": err.to_dict()}, status_code=status)
            return Response(content=blob["data"], media_type="application/octet-stream", headers={"X-Artifact-SHA256": blob["sha256"]})

        from agent_network.a2a_official import (
            BodyRequest,
            ensure_message_id,
            official_jsonrpc_dispatcher,
            official_request_handler,
            official_rest_routes,
        )

        handler = official_request_handler(self)
        dispatcher = official_jsonrpc_dispatcher(self, handler)

        async def a2a(request: Request) -> Response:
            body = await request.json()
            ensure_message_id(body)
            return await dispatcher.handle_requests(BodyRequest(request, body))

        @asynccontextmanager
        async def lifespan(_app: Starlette):
            import asyncio

            start_task = None
            if on_start is not None:
                # Do not block listen: ANNOUNCE reachability needs this process to be up.
                async def _run_start() -> None:
                    await asyncio.sleep(0.15)
                    last: Exception | None = None
                    for _ in range(5):
                        try:
                            await on_start()
                            return
                        except Exception as exc:  # noqa: BLE001
                            last = exc
                            await asyncio.sleep(0.4)
                    if last is not None:
                        print(f"on_start failed: {type(last).__name__}: {last}")

                start_task = asyncio.create_task(_run_start())
            yield
            if start_task is not None:
                start_task.cancel()

        routes = [
            Route("/.well-known/agent-card.json", well_known),
            Route("/a2a", a2a, methods=["POST"]),
            Route("/health", health),
            Route("/artifacts/{artifact_id}", artifacts_get, methods=["GET"]),
            *official_rest_routes(self, handler),
        ]
        if extra_routes:
            routes.extend(extra_routes)
        return Starlette(routes=routes, lifespan=lifespan)

    async def handle_message(self, message: dict[str, Any]) -> dict[str, Any]:
        metadata = dict(message.get("metadata") or {})
        capability = str(metadata.get("capability") or _text_capability(message) or "")
        task_id = str(metadata.get("task_id") or new_id("task"))
        handler = self.handlers.get(capability)
        if handler is None:
            envelope = ErrorEnvelope.of("UNSUPPORTED_CAPABILITY", f"no handler for {capability}")
            task = {
                "id": task_id,
                "status": {"state": "failed"},
                "metadata": {"error": envelope.code, "error_envelope": envelope.to_dict(), "capability": capability},
            }
            self.tasks[task_id] = task
            return task

        idem_key = str(metadata.get("idempotency_key") or "")
        message_id = str(message.get("messageId") or metadata.get("message_id") or "")
        sender = str(metadata.get("requester_agent_id") or metadata.get("sender_agent_id") or "")
        if message_id and sender:
            cached = self.idempotency.get_message(sender, message_id)
            if cached is not None:
                return cached
        if idem_key:
            cached = self.idempotency.get(idem_key)
            if cached is not None:
                return cached

        contract_raw = metadata.get("contract") or {}
        if contract_raw and capability not in {"task.propose"}:
            req_sig = contract_raw.get("requester_signature")
            exe_sig = contract_raw.get("executor_signature")
            if not req_sig or not exe_sig:
                envelope = ErrorEnvelope.of("TASK_REJECTED", "unsigned contract")
                task = {
                    "id": task_id,
                    "status": {"state": "failed"},
                    "metadata": {"error": envelope.code, "error_envelope": envelope.to_dict()},
                }
                self.tasks[task_id] = task
                return task
            from agent_network.crypto import verify_object

            if not verify_object(self.identity.public_key, contract_raw, exe_sig):
                envelope = ErrorEnvelope.of("INVALID_SIGNATURE", "executor_signature mismatch")
                task = {
                    "id": task_id,
                    "status": {"state": "failed"},
                    "metadata": {"error": envelope.code, "error_envelope": envelope.to_dict()},
                }
                self.tasks[task_id] = task
                return task

        payload = {
            "message": message,
            "metadata": metadata,
            "capability": capability,
            "task_id": task_id,
            "identity": self.identity,
        }
        result = handler(payload)
        if hasattr(result, "__await__"):
            result = await result  # type: ignore[misc]
        if not isinstance(result, HandlerResult):
            raise TypeError("skill handler must return HandlerResult")

        artifacts = []
        contract_raw = (result.contract.to_dict() if result.contract else None) or metadata.get("contract") or {}
        for item in result.artifacts:
            if isinstance(item, ArtifactManifest):
                self._publish_artifact(item, contract_raw)
                artifacts.append(_a2a_artifact(item))
            else:
                artifacts.append(item)

        state = "completed" if result.status == "completed" else "failed"
        if result.status in {"FAILED", "failed"}:
            state = "failed"
        envelope = None
        if state == "failed" and result.error_code:
            envelope = ErrorEnvelope.of(result.error_code, result.message or result.error_code)
        task = {
            "id": task_id,
            "status": {"state": state},
            "artifacts": artifacts,
            "metadata": {
                **result.metadata,
                "error": result.error_code,
                "message": result.message,
                "error_envelope": envelope.to_dict() if envelope else None,
                "contract": result.contract.to_dict()
                if result.contract
                else result.metadata.get("contract") or metadata.get("contract"),
            },
            "updated_at": utc_now(),
        }
        self.tasks[task_id] = task
        if idem_key:
            self.idempotency.put(idem_key, task)
        if message_id and sender:
            self.idempotency.put_message(sender, message_id, task)
        return task

    async def _handle_propose(self, payload: dict[str, Any]) -> HandlerResult:
        from agent_network.proposal import TaskProposal

        message = payload["message"]
        metadata = payload["metadata"]
        body: dict[str, Any] = {}
        for part in message.get("parts") or []:
            if part.get("kind") == "data" and isinstance(part.get("data"), dict):
                body = dict(part["data"])
                break
        proposal_raw = dict(body)
        if isinstance(metadata.get("proposal"), dict):
            proposal_raw.update(metadata["proposal"])
        capability = proposal_raw.get("capability")
        cap_id = capability.get("id") if isinstance(capability, dict) else capability
        cap_id = cap_id or proposal_raw.get("capability_id")
        work_handlers = {k for k in self.handlers if k != "task.propose"}
        if cap_id and cap_id not in work_handlers:
            return HandlerResult(
                status="failed",
                error_code="UNSUPPORTED_CAPABILITY",
                metadata={"decision": "REJECT"},
            )
        if not cap_id:
            return HandlerResult(metadata={"decision": "ACCEPT"})
        proposal = TaskProposal.from_dict(proposal_raw) if "proposal_id" in proposal_raw else TaskProposal.create(
            requester=str(proposal_raw.get("requester") or metadata.get("requester_agent_id") or ""),
            target=self.identity.agent_id,
            capability_id=str(cap_id),
            objective=str(proposal_raw.get("objective") or ""),
            constraints=list(proposal_raw.get("constraints") or []),
            deliverables=list(proposal_raw.get("deliverables") or []),
            verification=proposal_raw.get("verification"),
            side_effects=str(proposal_raw.get("side_effects") or "NONE"),
        )
        if metadata.get("action") == "REJECT":
            return HandlerResult(status="failed", error_code="TASK_REJECTED", metadata={"decision": "REJECT"})
        contract = TaskContract.create(
            requester=proposal.requester,
            executor=self.identity.agent_id,
            capability=proposal.capability["id"],
            objective=proposal.objective,
            constraints=proposal.constraints,
            deliverables=proposal.deliverables,
            verification=proposal.verification,
            metadata=dict(proposal_raw.get("metadata") or metadata.get("task_metadata") or {}),
        )
        contract.proposal_id = proposal.proposal_id
        contract.proposal_revision = proposal.revision
        contract.proposal_hash = self.identity.object_hash(proposal.to_dict())
        contract.side_effects = proposal.side_effects
        contract.status = "SIGNED"
        contract.executor_key_id = self.identity.key_id
        contract.requester_key_id = str(metadata.get("requester_key_id") or proposal_raw.get("requester_key_id") or "")
        from agent_network.verification_policy import policy_hash

        contract.verification_policy_hash = policy_hash(proposal.verification)
        contract.executor_signature = self.identity.sign_object(contract.to_dict())
        contract.contract_hash = self.identity.object_hash(contract.to_dict())
        return HandlerResult(
            metadata={
                "decision": "ACCEPT",
                "contract": contract.to_dict(),
                "proposal": proposal.to_dict(),
            }
        )

    def _publish_artifact(self, manifest: ArtifactManifest, contract: dict[str, Any]) -> None:
        from agent_network.crypto import b64decode
        from pathlib import Path

        raw: bytes | None = None
        if manifest.inline and manifest.inline.get("data") is not None:
            enc = manifest.inline.get("encoding") or "utf-8"
            data = manifest.inline["data"]
            raw = b64decode(data) if enc == "base64" else data.encode(enc)
        elif manifest.local_path:
            p = Path(manifest.local_path)
            if p.exists():
                raw = p.read_bytes()
        if raw is None:
            return
        allowed = {contract.get("requester"), contract.get("executor"), self.identity.agent_id}
        verification = contract.get("verification") or {}
        verifier = verification.get("verifier_agent_id")
        if verifier:
            allowed.add(verifier)
        for item in verification.get("verifiers") or []:
            if item:
                allowed.add(str(item))
        party_keys = dict((contract.get("metadata") or {}).get("party_keys") or {})
        for agent_id, key in (
            (contract.get("requester"), contract.get("requester_public_key")),
            (contract.get("executor"), contract.get("executor_public_key")),
            (verifier, verification.get("verifier_public_key")),
        ):
            if agent_id and key:
                party_keys[str(agent_id)] = str(key)
        self.artifact_blobs[manifest.artifact_id] = {
            "data": raw,
            "sha256": manifest.sha256,
            "allowed": {a for a in allowed if a},
            "party_keys": party_keys,
        }


def _text_capability(message: dict[str, Any]) -> str:
    for part in message.get("parts") or []:
        if part.get("kind") == "data" and part.get("data", {}).get("capability"):
            return str(part["data"]["capability"])
    return ""


def _a2a_artifact(manifest: ArtifactManifest) -> dict[str, Any]:
    return {
        "artifactId": manifest.artifact_id,
        "name": manifest.type,
        "parts": [
            {
                "kind": "data",
                "data": manifest.to_dict(),
            }
        ],
    }


def text_message(*, capability: str, text: str, contract: dict[str, Any] | None = None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    metadata = {"capability": capability}
    if contract:
        metadata["contract"] = contract
        metadata["task_id"] = contract.get("metadata", {}).get("task_id") or new_id("task")
    if extra:
        metadata.update(extra)
    if "idempotency_key" not in metadata:
        from uuid import uuid4 as _uuid4

        metadata["idempotency_key"] = str(_uuid4())
    return {
        "messageId": str(uuid4()),
        "role": "user",
        "parts": [{"kind": "text", "text": text}],
        "metadata": metadata,
    }


def artifact_from_file(
    *,
    task_id: str,
    path,
    artifact_type: str,
    owner: str,
    metadata: dict[str, Any] | None = None,
    identity: Identity | None = None,
    public_base: str | None = None,
    revision: int = 1,
    artifact_id: str | None = None,
) -> ArtifactManifest:
    from pathlib import Path

    from agent_network.artifact_ref import INLINE_MAX_BYTES
    from agent_network.crypto import b64encode

    p = Path(path)
    raw = p.read_bytes()
    digest = file_sha256(p)
    aid = artifact_id or p.stem
    locations: list[dict[str, str]] = []
    inline = None
    if len(raw) <= INLINE_MAX_BYTES:
        inline = {"encoding": "base64", "data": b64encode(raw)}
    if public_base:
        locations.append(
            {
                "transport": "https" if str(public_base).startswith("https") else "http",
                "url": f"{public_base.rstrip('/')}/artifacts/{aid}",
            }
        )
    public_uri = locations[0]["url"] if locations else f"artifact:{aid}"
    manifest = ArtifactManifest(
        artifact_id=aid,
        task_id=task_id,
        type=artifact_type,
        uri=public_uri,
        sha256=digest,
        owner=owner,
        revision=revision,
        media_type="application/octet-stream",
        locations=locations,
        inline=inline,
        metadata=metadata or {},
        local_path=str(p.resolve()),
    )
    if identity is not None:
        manifest.signature = identity.sign_object(manifest.to_dict())
    return manifest


def json_artifact(
    *,
    task_id: str,
    artifact_type: str,
    payload: dict[str, Any],
    owner: str,
    directory,
    identity: Identity | None = None,
    public_base: str | None = None,
) -> ArtifactManifest:
    from pathlib import Path

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    artifact_id = new_id("artifact")
    path = directory / f"{artifact_id}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return artifact_from_file(
        task_id=task_id,
        path=path,
        artifact_type=artifact_type,
        owner=owner,
        metadata={"payload_keys": list(payload.keys())},
        identity=identity,
        artifact_id=artifact_id,
        public_base=public_base,
    )

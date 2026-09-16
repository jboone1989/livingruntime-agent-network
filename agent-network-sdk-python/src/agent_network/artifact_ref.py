from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from agent_network.crypto import Identity, b64decode, b64encode, sha256_hex, verify_object
from agent_network.errors import ErrorEnvelope
from agent_network.models import utc_now

ARTIFACT_GET_MAX_SKEW = timedelta(minutes=5)

INLINE_MAX_BYTES = 64 * 1024


class ArtifactHashMismatch(ValueError):
    def __init__(self) -> None:
        super().__init__("ARTIFACT_HASH_MISMATCH")


@dataclass
class ArtifactRef:
    artifact_id: str
    task_id: str
    producer_agent_id: str
    sha256: str
    revision: int = 1
    media_type: str = "application/octet-stream"
    size: int = 0
    locations: list[dict[str, str]] = field(default_factory=list)
    inline: dict[str, str] | None = None
    created_at: str | None = None
    signature: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ArtifactRef:
        payload = dict(data)
        if "producer_agent_id" not in payload and payload.get("owner"):
            payload["producer_agent_id"] = payload["owner"]
        payload.setdefault("task_id", "")
        payload.setdefault("producer_agent_id", payload.get("producer_agent_id") or "")
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in payload.items() if k in known})

    @classmethod
    def from_inline(
        cls,
        *,
        artifact_id: str,
        task_id: str,
        producer_agent_id: str,
        data: bytes,
        media_type: str = "application/octet-stream",
        revision: int = 1,
    ) -> ArtifactRef:
        if len(data) > INLINE_MAX_BYTES:
            raise ValueError("inline artifact exceeds 64 KiB")
        return cls(
            artifact_id=artifact_id,
            task_id=task_id,
            producer_agent_id=producer_agent_id,
            sha256=sha256_hex(data),
            revision=revision,
            media_type=media_type,
            size=len(data),
            inline={"encoding": "base64", "data": b64encode(data)},
        )

    def with_revision(self, data: bytes) -> ArtifactRef:
        nxt = ArtifactRef.from_inline(
            artifact_id=self.artifact_id,
            task_id=self.task_id,
            producer_agent_id=self.producer_agent_id,
            data=data,
            media_type=self.media_type,
            revision=self.revision + 1,
        )
        nxt.locations = list(self.locations)
        return nxt


def materialize_artifact(ref: ArtifactRef | dict[str, Any]) -> bytes:
    obj = ref if isinstance(ref, ArtifactRef) else ArtifactRef.from_dict(ref)
    if isinstance(obj.inline, dict) and obj.inline.get("data") is not None:
        encoding = obj.inline.get("encoding") or "utf-8"
        raw = obj.inline["data"]
        body = b64decode(raw) if encoding == "base64" else raw.encode(encoding)
        if sha256_hex(body) != obj.sha256:
            raise ArtifactHashMismatch()
        return body
    raise ValueError("ARTIFACT_NOT_FOUND")


def artifact_download_headers(identity: Identity, artifact_id: str, timestamp: str | None = None) -> dict[str, str]:
    ts = timestamp or utc_now()
    payload = {"artifact_id": artifact_id, "timestamp": ts}
    return {
        "X-Agent-Id": identity.agent_id,
        "X-Timestamp": ts,
        "X-Public-Key": identity.public_key,
        "X-Signature": identity.sign_object(payload),
    }


def authorize_artifact_get(
    *,
    artifact_id: str,
    headers: Mapping[str, str],
    allowed: set[str],
    party_keys: dict[str, str] | None = None,
) -> tuple[ErrorEnvelope | None, int]:
    agent_id = headers.get("X-Agent-Id") or headers.get("x-agent-id") or ""
    timestamp = headers.get("X-Timestamp") or headers.get("x-timestamp") or ""
    signature = headers.get("X-Signature") or headers.get("x-signature") or ""
    presented = headers.get("X-Public-Key") or headers.get("x-public-key") or ""
    if not agent_id:
        return ErrorEnvelope.of("INVALID_REQUEST", "X-Agent-Id required"), 401
    if allowed and agent_id not in allowed:
        return ErrorEnvelope.of("INVALID_REQUEST", "not a contract party"), 403
    if not timestamp or not signature:
        return ErrorEnvelope.of("INVALID_REQUEST", "signed artifact GET required"), 401
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        skew = abs(datetime.now(timezone.utc) - parsed)
        if skew > ARTIFACT_GET_MAX_SKEW:
            return ErrorEnvelope.of("INVALID_REQUEST", "timestamp outside window"), 401
    except ValueError:
        return ErrorEnvelope.of("INVALID_REQUEST", "invalid timestamp"), 401
    public_key = (party_keys or {}).get(agent_id) or presented
    if not public_key:
        return ErrorEnvelope.of("INVALID_REQUEST", "X-Public-Key required"), 401
    if not verify_object(public_key, {"artifact_id": artifact_id, "timestamp": timestamp}, signature):
        return ErrorEnvelope.of("INVALID_SIGNATURE", "artifact GET signature failed"), 401
    return None, 200


async def fetch_artifact(
    ref: ArtifactRef | dict[str, Any],
    *,
    identity: Identity,
    timeout: float = 15.0,
    client: Any | None = None,
) -> bytes:
    obj = ref if isinstance(ref, ArtifactRef) else ArtifactRef.from_dict(ref)
    try:
        return materialize_artifact(obj)
    except ArtifactHashMismatch:
        raise
    except ValueError:
        pass
    import httpx

    own_client = client is None
    http = client or httpx.AsyncClient(timeout=timeout)
    try:
        headers = artifact_download_headers(identity, obj.artifact_id)
        for loc in obj.locations:
            url = loc.get("url") or ""
            if loc.get("transport") not in {"http", "https"} and not url.startswith("http"):
                continue
            res = await http.get(url, headers=headers)
            if res.status_code >= 400:
                continue
            body = res.content
            if sha256_hex(body) != obj.sha256:
                raise ArtifactHashMismatch()
            return body
    finally:
        if own_client:
            await http.aclose()
    raise ValueError("ARTIFACT_NOT_FOUND")

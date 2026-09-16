from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

CONTRACT_STATUSES = (
    "PROPOSED",
    "NEGOTIATING",
    "SIGNED",
    "ACTIVE",
    "ACCEPTED",
    "EXECUTING",
    "DELIVERED",
    "VERIFYING",
    "VERIFIED",
    "ACCEPTED_FINAL",
    "REJECTED",
    "FAILED",
    "CANCELED",
    "EXPIRED",
    "VERIFICATION_FAILED",
    "DISPUTED",
    "CLOSED",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


@dataclass
class AgentRegistration:
    agent_id: str
    name: str
    agent_card_url: str
    public_key: str
    capabilities: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)
    signature: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if data.get("signature") is None:
            data.pop("signature")
        return data


@dataclass
class AgentSummary:
    agent_id: str
    name: str
    agent_card_url: str
    endpoint: str | None
    online: bool
    public_key: str | None = None
    capabilities: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentSummary:
        return cls(
            agent_id=data["agent_id"],
            name=data.get("name") or data["agent_id"],
            agent_card_url=data.get("agent_card_url") or "",
            endpoint=data.get("endpoint"),
            online=bool(data.get("online", False)),
            public_key=data.get("public_key"),
            capabilities=list(data.get("capabilities") or []),
            raw=data,
        )


@dataclass
class TaskContract:
    contract_id: str
    requester: str
    executor: str
    capability: str
    objective: str
    constraints: list[str]
    deliverables: list[str]
    verification: dict[str, Any]
    created_at: str
    status: str = "SIGNED"
    expires_at: str | None = None
    economic_terms: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)
    proposal_id: str | None = None
    proposal_revision: int | None = None
    proposal_hash: str | None = None
    side_effects: str = "NONE"
    requester_signature: str | None = None
    executor_signature: str | None = None
    schema_version: str = "0.2"
    canonicalization: str = "agent-json-v0.1"
    signature_suite: str = "ed25519-sha256-v1"
    requester_key_id: str | None = None
    executor_key_id: str | None = None
    verification_policy_hash: str | None = None
    contract_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def create(
        cls,
        *,
        requester: str,
        executor: str,
        capability: str,
        objective: str,
        constraints: list[str] | None = None,
        deliverables: list[str] | None = None,
        verification: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TaskContract:
        verification = verification or {"required": False}
        from agent_network.verification_policy import policy_hash

        return cls(
            contract_id=new_id("contract"),
            requester=requester,
            executor=executor,
            capability=capability,
            objective=objective,
            constraints=list(constraints or []),
            deliverables=list(deliverables or []),
            verification=verification,
            created_at=utc_now(),
            status="SIGNED",
            metadata=dict(metadata or {}),
            verification_policy_hash=policy_hash(verification),
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskContract:
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        payload = {k: v for k, v in data.items() if k in known}
        return cls(**payload)


@dataclass
class ArtifactManifest:
    artifact_id: str
    task_id: str
    type: str
    uri: str
    sha256: str
    owner: str | None = None
    revision: int = 1
    media_type: str | None = None
    locations: list[dict[str, str]] = field(default_factory=list)
    inline: dict[str, str] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    signature: str | None = None
    local_path: str | None = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("local_path", None)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ArtifactManifest:
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class VerificationReceipt:
    verification_id: str
    task_id: str
    artifact_id: str
    artifact_hash: str
    verifier: str
    result: str
    timestamp: str
    signature: str
    checks: dict[str, Any] = field(default_factory=dict)
    schema_version: str = "0.2"
    contract_id: str | None = None
    contract_hash: str | None = None
    artifact_manifest_hash: str | None = None
    verifier_key_id: str | None = None
    verification_policy_hash: str | None = None
    verification_method: str | None = None
    evidence_hashes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VerificationReceipt:
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class TaskAcceptance:
    contract_id: str
    requester_agent_id: str
    result: str
    signature: str
    artifact_id: str | None = None
    artifact_manifest_hash: str | None = None
    verification_id: str | None = None
    timestamp: str | None = None
    schema_version: str = "0.2"
    requester_key_id: str | None = None
    contract_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskAcceptance:
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class TaskLifecycleEvent:
    event_id: str
    contract_id: str
    contract_hash: str
    previous_event_hash: str
    status: str
    actor_agent_id: str
    actor_key_id: str
    timestamp: str
    signature: str = ""
    artifact_hashes: list[str] = field(default_factory=list)
    schema_version: str = "0.2"
    canonicalization: str = "agent-json-v0.1"
    signature_suite: str = "ed25519-sha256-v1"
    event_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskLifecycleEvent:
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})

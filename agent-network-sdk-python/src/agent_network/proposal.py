from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from agent_network.crypto import Identity
from agent_network.models import TaskContract, new_id, utc_now
from agent_network.verification_policy import validate_verification


@dataclass
class TaskProposal:
    proposal_id: str
    revision: int
    requester: str
    target: str
    capability: dict[str, str]
    objective: str
    constraints: list[str] = field(default_factory=list)
    deliverables: list[str] = field(default_factory=list)
    verification: dict[str, Any] = field(default_factory=dict)
    side_effects: str = "NONE"
    expires_at: str | None = None
    idempotency_key: str | None = None
    signature: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def create(
        cls,
        *,
        requester: str,
        target: str,
        capability_id: str,
        objective: str,
        capability_version: str = "1.0.0",
        constraints: list[str] | None = None,
        deliverables: list[str] | None = None,
        verification: dict[str, Any] | None = None,
        side_effects: str = "NONE",
        idempotency_key: str | None = None,
    ) -> TaskProposal:
        verification = dict(verification or {"required": False})
        if verification.get("required"):
            validate_verification(verification, executor=target)
        return cls(
            proposal_id=new_id("proposal"),
            revision=1,
            requester=requester,
            target=target,
            capability={"id": capability_id, "version": capability_version},
            objective=objective,
            constraints=list(constraints or []),
            deliverables=list(deliverables or []),
            verification=verification,
            side_effects=side_effects,
            idempotency_key=idempotency_key,
        )

    def counter(self, **changes: Any) -> TaskProposal:
        data = self.to_dict()
        data.update(changes)
        data["revision"] = self.revision + 1
        data["signature"] = None
        return TaskProposal(**{k: v for k, v in data.items() if k in TaskProposal.__dataclass_fields__})

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskProposal:
        payload = dict(data)
        cap = payload.get("capability")
        if isinstance(cap, str):
            payload["capability"] = {"id": cap, "version": payload.get("capability_version") or "1.0.0"}
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        payload.setdefault("proposal_id", new_id("proposal"))
        payload.setdefault("revision", 1)
        payload.setdefault("requester", "")
        payload.setdefault("target", "")
        payload.setdefault("capability", {"id": "", "version": "1.0.0"})
        payload.setdefault("objective", "")
        return cls(**{k: v for k, v in payload.items() if k in known})


def sign_contract_from_proposal(
    proposal: TaskProposal,
    *,
    requester: Identity,
    executor: Identity,
) -> TaskContract:
    if proposal.verification.get("required"):
        validate_verification(proposal.verification, executor=proposal.target)
    contract = TaskContract.create(
        requester=proposal.requester,
        executor=proposal.target,
        capability=proposal.capability["id"],
        objective=proposal.objective,
        constraints=proposal.constraints,
        deliverables=proposal.deliverables,
        verification=proposal.verification,
        metadata={"proposal_id": proposal.proposal_id},
    )
    contract.proposal_id = proposal.proposal_id
    contract.proposal_revision = proposal.revision
    contract.proposal_hash = requester.object_hash(proposal.to_dict())
    contract.side_effects = proposal.side_effects
    contract.status = "SIGNED"
    contract.requester_key_id = requester.key_id
    contract.executor_key_id = executor.key_id
    from agent_network.verification_policy import policy_hash

    contract.verification_policy_hash = policy_hash(proposal.verification)
    contract.requester_signature = requester.sign_object(contract.to_dict())
    contract.executor_signature = executor.sign_object(contract.to_dict())
    contract.contract_hash = requester.object_hash(contract.to_dict())
    return contract

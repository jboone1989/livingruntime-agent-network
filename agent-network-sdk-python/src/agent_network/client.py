from __future__ import annotations

from typing import Any

from agent_network.a2a_card import resolve_a2a_url
from agent_network.a2a_client import A2AClient
from agent_network.a2a_server import text_message
from agent_network.capability import schema_validate
from agent_network.crypto import Identity, verify_object
from agent_network.errors import IdentityInvalid, NetworkError
from agent_network.models import AgentSummary, ArtifactManifest, TaskContract, VerificationReceipt


class Peer:
    def __init__(self, network: Any, agent: AgentSummary, card: dict[str, Any], endpoint: str) -> None:
        self.network = network
        self.agent = agent
        self.card = card
        self.endpoint = endpoint.rstrip("/")
        self.a2a = A2AClient(self.endpoint)

    async def propose_task(
        self,
        *,
        capability: str,
        objective: str,
        constraints: list[str] | None = None,
        deliverables: list[str] | None = None,
        verification: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        capability_input: dict[str, Any] | None = None,
        text: str | None = None,
        capability_version: str = "1.0.0",
        side_effects: str = "NONE",
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        from agent_network.proposal import TaskProposal

        if self.network.identity is None:
            raise NetworkError("IDENTITY_MISSING", "requester identity required")
        verification = dict(verification or {"required": False})
        if verification.get("required") and not verification.get("policy"):
            verification["policy"] = "REQUESTER_SELECTS"
        schema = ((getattr(self.agent, "raw", None) or {}).get("capability") or {}).get("input_schema")
        if schema:
            if capability_input is not None:
                schema_validate(schema, dict(capability_input))
            else:
                # Backward compatibility for generic capabilities whose schema describes the
                # original objective/constraints/deliverables proposal payload.
                schema_validate(schema, {
                    "objective": objective,
                    "constraints": list(constraints or []),
                    "deliverables": list(deliverables or []),
                })
        task_metadata = dict(metadata or {})
        if capability_input is not None:
            existing_input = task_metadata.get("capability_input")
            if existing_input is not None and existing_input != capability_input:
                raise ValueError("metadata capability_input conflicts with capability_input argument")
            task_metadata["capability_input"] = dict(capability_input)
        proposal = TaskProposal.create(
            requester=self.network.identity.agent_id,
            target=self.agent.agent_id,
            capability_id=capability,
            capability_version=capability_version,
            objective=objective,
            constraints=constraints,
            deliverables=deliverables,
            verification=verification,
            side_effects=side_effects,
            idempotency_key=idempotency_key,
        )
        proposal.signature = self.network.identity.sign_object(proposal.to_dict())
        offered = await self.a2a.message_send(
            {
                "messageId": proposal.proposal_id,
                "role": "user",
                "parts": [{"kind": "data", "data": proposal.to_dict()}],
                "metadata": {
                    "capability": "task.propose",
                    "proposal": proposal.to_dict(),
                    "requester_agent_id": self.network.identity.agent_id,
                    "requester_key_id": self.network.identity.key_id,
                    "task_metadata": task_metadata,
                },
            }
        )
        meta = offered.get("metadata") or {}
        if meta.get("decision") == "COUNTER" and meta.get("proposal"):
            counter = TaskProposal.from_dict(meta["proposal"])
            counter.signature = self.network.identity.sign_object(counter.to_dict())
            offered = await self.a2a.message_send(
                {
                    "role": "user",
                    "parts": [{"kind": "data", "data": counter.to_dict()}],
                    "metadata": {
                        "capability": "task.propose",
                        "action": "ACCEPT",
                        "proposal": counter.to_dict(),
                        "requester_agent_id": self.network.identity.agent_id,
                        "requester_key_id": self.network.identity.key_id,
                        "task_metadata": task_metadata,
                    },
                }
            )
            meta = offered.get("metadata") or {}
        if (offered.get("status") or {}).get("state") == "failed" or meta.get("decision") == "REJECT":
            return offered
        contract_raw = meta.get("contract")
        if not contract_raw or not contract_raw.get("executor_signature"):
            raise NetworkError("TASK_REJECTED", "executor did not sign a contract")
        contract = TaskContract.from_dict(contract_raw)
        contract.requester_signature = self.network.identity.sign_object(contract.to_dict())
        contract.status = "SIGNED"
        contract.contract_hash = self.network.identity.object_hash(contract.to_dict())
        if hasattr(self.network, "submit_contract"):
            await self.network.submit_contract(contract)
        extra = {
            "task_id": contract.metadata.get("task_id") or contract.contract_id,
            "proposal": proposal.to_dict(),
            "requester_agent_id": self.network.identity.agent_id,
        }
        if idempotency_key:
            extra["idempotency_key"] = idempotency_key
        result = await self.a2a.message_send(
            text_message(
                capability=capability,
                text=text or objective,
                contract=contract.to_dict(),
                extra=extra,
            )
        )
        result.setdefault("metadata", {})
        result["metadata"]["contract"] = contract.to_dict()
        return result

    async def request_verification(
        self,
        *,
        task: dict[str, Any],
        artifacts: list[dict[str, Any] | ArtifactManifest],
        capability: str = "software.review",
        objective: str = "Independently verify delivered artifacts",
    ) -> dict[str, Any]:
        manifests = []
        for item in artifacts:
            manifests.append(item.to_dict() if isinstance(item, ArtifactManifest) else item)
        return await self.propose_task(
            capability=capability,
            objective=objective,
            deliverables=["verification_receipt"],
            verification={"required": False},
            metadata={
                "subject_task": task,
                "subject_contract": (task.get("metadata") or {}).get("contract") or {},
                "artifacts": manifests,
            },
            text=objective,
        )


def subject_contract(metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Receipts bind to the original work contract, not the review envelope."""
    meta = metadata or {}
    work = meta.get("contract") or {}
    nested = work.get("metadata") or {}
    subject_task = meta.get("subject_task") or nested.get("subject_task") or {}
    return (
        meta.get("subject_contract")
        or nested.get("subject_contract")
        or (subject_task.get("metadata") or {}).get("contract")
        or work
    )


SIGNED_RECEIPT_FIELDS = (
    "verification_id",
    "verifier",
    "verifier_key_id",
    "contract_id",
    "contract_hash",
    "artifact_manifest_hash",
    "result",
    "signature",
)


def signed_verification_receipt(obj: dict[str, Any] | None, public_key: str | None = None) -> dict[str, Any] | None:
    if not isinstance(obj, dict):
        return None
    if any(not obj.get(key) for key in SIGNED_RECEIPT_FIELDS):
        return None
    if public_key and not verify_object(public_key, obj, str(obj.get("signature") or "")):
        return None
    if public_key is None and not obj.get("signature"):
        return None
    return dict(obj)


def verification_receipt_from_task(task: dict[str, Any] | None) -> dict[str, Any]:
    import json

    from agent_network.artifact_ref import materialize_artifact

    for man in parse_artifacts(task or {}):
        payload = man
        try:
            payload = json.loads(materialize_artifact(man))
        except Exception:
            payload = man
        receipt = signed_verification_receipt(payload if isinstance(payload, dict) else None)
        if receipt is not None:
            return receipt
    return {}


def parse_artifacts(task: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for art in task.get("artifacts") or []:
        for part in art.get("parts") or []:
            if part.get("kind") == "data" and isinstance(part.get("data"), dict):
                out.append(part["data"])
    return out


def verify_peer_signature(public_key: str, obj: dict[str, Any], signature: str | None) -> None:
    if not signature or not verify_object(public_key, obj, signature):
        raise IdentityInvalid()

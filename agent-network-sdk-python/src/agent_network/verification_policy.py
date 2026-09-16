from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class VerifierSelectionError(ValueError):
    pass


ALLOWED_POLICIES = {"REQUESTER_SELECTS", "MULTI_VERIFIER", "REPUTATION_WEIGHTED"}
RESERVED_POLICIES = {"MUTUAL_SELECTION", "NETWORK_RANDOM"}


def _named_verifiers(verification: dict[str, Any]) -> list[str]:
    verifiers = [str(item) for item in (verification.get("verifiers") or []) if item]
    unique = list(dict.fromkeys(verifiers))
    if verification.get("verifier_agent_id") and verification["verifier_agent_id"] not in unique:
        unique.append(str(verification["verifier_agent_id"]))
    return unique


def _validate_named_verifiers(
    verification: dict[str, Any],
    *,
    executor: str,
    min_count: int,
    min_passes: int,
) -> None:
    unique = _named_verifiers(verification)
    if executor in unique:
        raise VerifierSelectionError("executor cannot verify itself")
    if len(unique) < min_count:
        raise VerifierSelectionError(f"policy requires at least {min_count} verifier(s)")
    raw = verification.get("required_passes")
    passes = int(raw if raw is not None else min_passes)
    if passes < min_passes or passes > len(unique):
        raise VerifierSelectionError("required_passes must be between the minimum and the verifier count")


def validate_verification(verification: dict[str, Any], *, executor: str) -> None:
    if not verification or not verification.get("required"):
        return
    policy = verification.get("policy") or "REQUESTER_SELECTS"
    if policy in RESERVED_POLICIES:
        raise VerifierSelectionError(f"UNSUPPORTED_POLICY:{policy}")
    if policy not in ALLOWED_POLICIES:
        raise VerifierSelectionError("INVALID_REQUEST")
    verifier = verification.get("verifier_agent_id")
    if policy == "MULTI_VERIFIER":
        unique = _named_verifiers(verification)
        if executor in unique:
            raise VerifierSelectionError("executor cannot verify itself")
        if len(unique) < 2:
            raise VerifierSelectionError("MULTI_VERIFIER requires at least two verifiers")
        passes = int(verification.get("required_passes") or 0)
        if passes < 2 or passes > len(unique):
            raise VerifierSelectionError("required_passes must be between 2 and the verifier count")
        return
    if policy == "REPUTATION_WEIGHTED":
        _validate_named_verifiers(verification, executor=executor, min_count=1, min_passes=1)
        return
    if not verifier:
        raise VerifierSelectionError("verifier_agent_id required for REQUESTER_SELECTS")
    if verifier == executor:
        raise VerifierSelectionError("executor cannot verify itself")


def canonical_policy(verification: dict[str, Any] | None) -> dict[str, Any]:
    if not verification or not verification.get("required"):
        return {"policy": "NONE", "required": False, "verifiers": [], "required_passes": 0, "acceptance": []}
    verifiers = list(verification.get("verifiers") or [])
    if verification.get("verifier_agent_id") and verification["verifier_agent_id"] not in verifiers:
        verifiers.append(verification["verifier_agent_id"])
    return {
        "policy": verification.get("policy") or "REQUESTER_SELECTS",
        "verifiers": verifiers,
        "required_passes": int(verification.get("required_passes") or 1),
        "acceptance": list(verification.get("acceptance") or []),
        "required": True,
    }


def policy_hash(verification: dict[str, Any] | None) -> str:
    from agent_network.crypto import canonical_json, sha256_hex

    return sha256_hex(canonical_json(canonical_policy(verification)))


def authorized_verifiers(verification: dict[str, Any] | None) -> set[str]:
    return {str(item) for item in canonical_policy(verification).get("verifiers") or [] if item}


def required_pass_count(verification: dict[str, Any] | None) -> int:
    policy = canonical_policy(verification)
    if not policy.get("required"):
        return 0
    return max(1, int(policy.get("required_passes") or 1))


def qualifying_pass_verifiers(
    verification: dict[str, Any] | None,
    receipts: list[dict[str, Any]],
    *,
    contract_id: str,
    contract_hash: str,
    artifact_manifest_hash: str | None = None,
) -> set[str]:
    allowed = authorized_verifiers(verification)
    found: set[str] = set()
    for row in receipts:
        if row.get("contract_id") != contract_id or row.get("contract_hash") != contract_hash:
            continue
        if artifact_manifest_hash and row.get("artifact_manifest_hash") != artifact_manifest_hash:
            continue
        if row.get("result") != "PASS":
            continue
        if not row.get("signature"):
            continue
        verifier = str(row.get("verifier") or "")
        if not verifier:
            continue
        if allowed and verifier not in allowed:
            continue
        found.add(verifier)
    return found


def apply_available_quorum(verification: dict[str, Any]) -> dict[str, Any]:
    """Fill omitted required_passes. An explicit quorum is never lowered."""
    out = dict(verification)
    if (out.get("policy") or "") != "REPUTATION_WEIGHTED":
        return out
    names = _named_verifiers(out)
    out["verifiers"] = names
    if "required_passes" not in verification or verification.get("required_passes") is None:
        out["required_passes"] = 2 if len(names) >= 2 else 1
    else:
        out["required_passes"] = int(verification["required_passes"])
    return out


def quorum_met(
    verification: dict[str, Any] | None,
    receipts: list[dict[str, Any]],
    *,
    contract_id: str,
    contract_hash: str,
    artifact_manifest_hash: str | None = None,
) -> bool:
    needed = required_pass_count(verification)
    if needed <= 0:
        return True
    return (
        len(
            qualifying_pass_verifiers(
                verification,
                receipts,
                contract_id=contract_id,
                contract_hash=contract_hash,
                artifact_manifest_hash=artifact_manifest_hash,
            )
        )
        >= needed
    )

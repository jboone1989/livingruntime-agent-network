from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


RETRYABLE_CODES = {
    "AGENT_BUSY",
    "AGENT_UNREACHABLE",
    "RATE_LIMITED",
    "INTERNAL_ERROR",
}

NON_RETRYABLE_CODES = {
    "INVALID_SIGNATURE",
    "INVALID_REQUEST",
    "UNSUPPORTED_CAPABILITY",
    "UNSUPPORTED_VERSION",
    "TASK_REJECTED",
    "TASK_EXPIRED",
    "TASK_FAILED",
    "ARTIFACT_NOT_FOUND",
    "ARTIFACT_HASH_MISMATCH",
    "VERIFICATION_FAILED",
    "IMMUTABLE_OBJECT_CONFLICT",
    "CONTRACT_IMMUTABLE",
    "TAMPER_DETECTED",
    "ROLLBACK_DETECTED",
    "KEY_NOT_VALID_AT",
    "ROLE_FORBIDDEN",
    "SELF_VERIFICATION_FORBIDDEN",
    "CAUSAL_CHAIN_CONFLICT",
    "VERIFIER_NOT_AUTHORIZED",
    "UNTRUSTED_PEER",
    "VERIFICATION_INVALID",
    "CLOCK_SKEW",
    "SCHEMA_INVALID",
    "SEAL_CONFLICT",
    "HISTORICAL_IMPORT_DISABLED",
    "EQUIVOCATION",
    "VERIFIER_EQUIVOCATION",
    "VERIFICATION_NOT_READY",
    "PEER_KEY_CONFLICT",
    "KEY_NOT_FOUND",
}


@dataclass
class ErrorEnvelope:
    code: str
    message: str
    retryable: bool
    retry_after_ms: int | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def of(cls, code: str, message: str = "", retry_after_ms: int | None = None, details: dict | None = None) -> ErrorEnvelope:
        retryable = code in RETRYABLE_CODES
        return cls(
            code=code,
            message=message or code,
            retryable=retryable,
            retry_after_ms=retry_after_ms if retryable else None,
            details=details or {},
        )


def can_retry(envelope: ErrorEnvelope, *, side_effects: str, has_idempotency: bool) -> bool:
    if not envelope.retryable:
        return False
    if side_effects == "IRREVERSIBLE" and not has_idempotency:
        return False
    return True


class NetworkError(Exception):
    def __init__(self, code: str, message: str = "", retryable: bool | None = None) -> None:
        self.code = code
        self.envelope = ErrorEnvelope.of(code, message)
        if retryable is not None:
            self.envelope.retryable = retryable
        super().__init__(message or code)


class IdentityInvalid(NetworkError):
    def __init__(self, message: str = "signature does not match identity") -> None:
        super().__init__("IDENTITY_INVALID", message)


class NoAvailableAgent(NetworkError):
    def __init__(self, capability: str) -> None:
        super().__init__("NO_AVAILABLE_AGENT", f"no agent for capability {capability}")
        self.capability = capability


class VerificationInvalid(NetworkError):
    def __init__(self, message: str = "artifact hash mismatch") -> None:
        super().__init__("VERIFICATION_INVALID", message)

"""Canonical JSON → SHA-256 → Ed25519. See agent-network-spec/docs/canonical-json.md."""
from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat

SIGNATURE_FIELDS = frozenset(
    {
        "signature",
        "requester_signature",
        "executor_signature",
        "signature_by_old_key",
        "recovery_signatures",
    }
)
DERIVED_HASH_FIELDS = frozenset({"contract_hash", "object_hash", "event_hash", "evidence_record_hash", "leaf_hashes"})
HASH_OMIT_FIELDS = SIGNATURE_FIELDS | DERIVED_HASH_FIELDS


def canonical_json(obj: Any) -> bytes:
    return json.dumps(
        obj,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def unsigned_payload(obj: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in obj.items() if k not in HASH_OMIT_FIELDS}


def sha256_digest(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def sha256_hex(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def b64encode(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def b64decode(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


def encode_public_key(raw: bytes) -> str:
    return "ed25519:" + b64encode(raw)


def encode_signature(raw: bytes) -> str:
    return "ed25519:" + b64encode(raw)


def strip_prefix(value: str, prefix: str) -> str:
    if value.startswith(prefix):
        return value[len(prefix) :]
    return value


def sign_digest(private_key: Ed25519PrivateKey, digest: bytes) -> str:
    return encode_signature(private_key.sign(digest))


def verify_digest(public_key_str: str, digest: bytes, signature_str: str) -> bool:
    try:
        raw_pk = b64decode(strip_prefix(public_key_str, "ed25519:"))
        raw_sig = b64decode(strip_prefix(signature_str, "ed25519:"))
        Ed25519PublicKey.from_public_bytes(raw_pk).verify(raw_sig, digest)
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def hash_and_sign(private_key: Ed25519PrivateKey, obj: dict[str, Any]) -> tuple[str, str]:
    digest = sha256_digest(canonical_json(unsigned_payload(obj)))
    return sha256_hex(canonical_json(unsigned_payload(obj))), sign_digest(private_key, digest)


def verify_object(public_key_str: str, obj: dict[str, Any], signature_str: str) -> bool:
    digest = sha256_digest(canonical_json(unsigned_payload(obj)))
    return verify_digest(public_key_str, digest, signature_str)


def _private_raw(sk: Ed25519PrivateKey) -> bytes:
    if hasattr(sk, "private_bytes_raw"):
        return sk.private_bytes_raw()  # type: ignore[no-any-return]
    return sk.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())


def _public_raw(sk: Ed25519PrivateKey) -> bytes:
    pk = sk.public_key()
    if hasattr(pk, "public_bytes_raw"):
        return pk.public_bytes_raw()  # type: ignore[no-any-return]
    return pk.public_bytes(Encoding.Raw, PublicFormat.Raw)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _new_key_id() -> str:
    return "key-" + uuid4().hex[:10]


@dataclass
class Identity:
    agent_id: str
    private_key: Ed25519PrivateKey
    public_key_raw: bytes
    key_id: str = ""
    revision: int = 1
    created_at: str = ""
    recovery_key_id: str = ""
    recovery_private_key: Ed25519PrivateKey | None = None
    key_provider: Any = None

    def __post_init__(self) -> None:
        if not self.key_id:
            self.key_id = _new_key_id()
        if not self.created_at:
            self.created_at = _now()
        if self.recovery_private_key is None:
            self.recovery_private_key = Ed25519PrivateKey.generate()
            self.recovery_key_id = "recovery-" + uuid4().hex[:10]
        if self.key_provider is None:
            from agent_network.trust.key_provider import InMemoryKeyProvider

            provider = InMemoryKeyProvider()
            provider.add(self.key_id, self.private_key, current=True)
            provider.add(self.recovery_key_id, self.recovery_private_key)
            self.key_provider = provider

    @property
    def public_key(self) -> str:
        return encode_public_key(self.public_key_raw)

    def sign_object(self, obj: dict[str, Any]) -> str:
        digest = sha256_digest(canonical_json(unsigned_payload(obj)))
        if self.key_provider is not None:
            return self.key_provider.sign(self.key_id, digest)
        return sign_digest(self.private_key, digest)

    def object_hash(self, obj: dict[str, Any]) -> str:
        return sha256_hex(canonical_json(unsigned_payload(obj)))

    def rotate(self) -> Identity:
        nxt = Identity.generate(self.agent_id)
        nxt.revision = self.revision + 1
        nxt.recovery_key_id = self.recovery_key_id
        nxt.recovery_private_key = self.recovery_private_key
        if nxt.key_provider is not None and self.recovery_key_id and self.recovery_private_key is not None:
            nxt.key_provider.add(self.recovery_key_id, self.recovery_private_key)
        return nxt

    def recovery_policy(self, *, threshold: int | None = None, recovery_keys: list[str] | None = None) -> dict[str, Any]:
        keys = list(recovery_keys or ([self.recovery_key_id] if self.recovery_key_id else []))
        body = {
            "type": "identity.recovery.policy",
            "agent_id": self.agent_id,
            "identity_epoch": self.revision,
            "threshold": int(threshold if threshold is not None else 1),
            "recovery_keys": keys,
            "timestamp": _now(),
            "operational_key_id": self.key_id,
        }
        body["signature"] = self.sign_object(body)
        return body

    def enrollment_message(
        self,
        *,
        agent_card_hash: str = "",
        recovery_policy_hash: str = "",
        recovery_keys: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        keys = list(recovery_keys or [])
        if not keys and self.recovery_key_id and self.key_provider is not None:
            keys = [{"key_id": self.recovery_key_id, "public_key": self.key_provider.public_key(self.recovery_key_id)}]
        body = {
            "type": "identity.enrollment",
            "agent_id": self.agent_id,
            "key_id": self.key_id,
            "public_key": self.public_key,
            "identity_epoch": 1,
            "agent_card_hash": agent_card_hash or sha256_hex(canonical_json({"agent_id": self.agent_id, "key_id": self.key_id})),
            "recovery_policy_hash": recovery_policy_hash or sha256_hex(b""),
            "created_at": self.created_at or _now(),
            "recovery_keys": keys,
        }
        body["signature"] = self.sign_object(body)
        return body

    def rotation_message(self, new: Identity) -> dict[str, Any]:
        body = {
            "type": "identity.key.rotate",
            "agent_id": self.agent_id,
            "old_key_id": self.key_id,
            "new_key": {"key_id": new.key_id, "public_key": new.public_key},
            "timestamp": _now(),
        }
        body["signature_by_old_key"] = self.sign_object(body)
        return body

    def revocation_message(self, key_id: str) -> dict[str, Any]:
        body = {
            "type": "identity.key.revoke",
            "agent_id": self.agent_id,
            "key_id": key_id,
            "timestamp": _now(),
        }
        body["signature"] = self.sign_object(body)
        return body

    def recovery_message(self, new: Identity) -> dict[str, Any]:
        body = {
            "type": "identity.key.recover",
            "agent_id": self.agent_id,
            "old_identity_epoch": self.revision,
            "new_identity_epoch": new.revision,
            "revoked_keys": [self.key_id],
            "new_operational_key": {"key_id": new.key_id, "public_key": new.public_key},
            "timestamp": _now(),
        }
        digest = sha256_digest(canonical_json(unsigned_payload(body)))
        assert self.recovery_private_key is not None
        body["recovery_signatures"] = [
            {"key_id": self.recovery_key_id, "signature": sign_digest(self.recovery_private_key, digest)}
        ]
        return body

    def to_record(self, *, include_recovery_private: bool = False) -> dict[str, Any]:
        rec_sk = self.recovery_private_key
        recovery_keys: list[dict[str, Any]] = []
        if self.recovery_key_id and rec_sk is not None:
            item: dict[str, Any] = {
                "key_id": self.recovery_key_id,
                "public_key": encode_public_key(_public_raw(rec_sk)),
            }
            if include_recovery_private:
                item["private_key"] = "ed25519:" + b64encode(_private_raw(rec_sk))
            recovery_keys.append(item)
        return {
            "agent_id": self.agent_id,
            "key_id": self.key_id,
            "revision": self.revision,
            "created_at": self.created_at,
            "public_key": self.public_key,
            "private_key": "ed25519:" + b64encode(_private_raw(self.private_key)),
            "recovery": {
                "threshold": 1,
                "keys": recovery_keys,
            },
        }

    def to_recovery_record(self) -> dict[str, Any]:
        rec_sk = self.recovery_private_key
        if rec_sk is None:
            raise ValueError("no recovery key")
        return {
            "agent_id": self.agent_id,
            "keys": [
                {
                    "key_id": self.recovery_key_id,
                    "public_key": encode_public_key(_public_raw(rec_sk)),
                    "private_key": "ed25519:" + b64encode(_private_raw(rec_sk)),
                }
            ],
        }

    @classmethod
    def recovery_path(cls, path: Path) -> Path:
        return path.with_name(path.stem + ".recovery.json")

    @classmethod
    def generate(cls, agent_id: str) -> Identity:
        sk = Ed25519PrivateKey.generate()
        return cls(agent_id=agent_id, private_key=sk, public_key_raw=_public_raw(sk))

    @classmethod
    def from_record(cls, record: dict[str, Any], recovery_record: dict[str, Any] | None = None) -> Identity:
        raw = b64decode(strip_prefix(record["private_key"], "ed25519:"))
        sk = Ed25519PrivateKey.from_private_bytes(raw)
        rec_id = ""
        rec_sk = None
        rec = recovery_record or record.get("recovery") or {}
        keys = rec.get("keys") or []
        if keys and keys[0].get("private_key"):
            rec_id = str(keys[0].get("key_id") or "recovery-1")
            rec_sk = Ed25519PrivateKey.from_private_bytes(b64decode(strip_prefix(keys[0]["private_key"], "ed25519:")))
        elif keys:
            rec_id = str(keys[0].get("key_id") or "")
        return cls(
            agent_id=record["agent_id"],
            private_key=sk,
            public_key_raw=_public_raw(sk),
            key_id=str(record.get("key_id") or _new_key_id()),
            revision=int(record.get("revision") or 1),
            created_at=str(record.get("created_at") or _now()),
            recovery_key_id=rec_id,
            recovery_private_key=rec_sk,
        )

    @classmethod
    def load_or_create(cls, path: Path, agent_id: str) -> Identity:
        path.parent.mkdir(parents=True, exist_ok=True)
        recovery_path = cls.recovery_path(path)
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            recovery_data = json.loads(recovery_path.read_text(encoding="utf-8")) if recovery_path.exists() else None
            ident = cls.from_record(data, recovery_data)
            if ident.agent_id != agent_id:
                raise ValueError(f"identity file agent_id {ident.agent_id} != {agent_id}")
            combined = any(item.get("private_key") for item in ((data.get("recovery") or {}).get("keys") or []))
            if combined or not recovery_path.exists():
                recovery_path.write_text(json.dumps(ident.to_recovery_record(), indent=2), encoding="utf-8")
                path.write_text(json.dumps(ident.to_record(), indent=2), encoding="utf-8")
            return ident
        ident = cls.generate(agent_id)
        path.write_text(json.dumps(ident.to_record(), indent=2), encoding="utf-8")
        recovery_path.write_text(json.dumps(ident.to_recovery_record(), indent=2), encoding="utf-8")
        return ident

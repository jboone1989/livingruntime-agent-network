from __future__ import annotations

from typing import Protocol

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from agent_network.crypto import encode_public_key, sign_digest, _public_raw


class KeyProvider(Protocol):
    def public_key(self, key_id: str) -> str: ...
    def sign(self, key_id: str, digest: bytes) -> str: ...
    def current_key_id(self) -> str: ...


class InMemoryKeyProvider:
    """Development provider. OSKeyStore / TPM / HSM / CloudKMS / RemoteSigner are reserved."""

    def __init__(self) -> None:
        self._sk: dict[str, Ed25519PrivateKey] = {}
        self._pk: dict[str, str] = {}
        self._current = ""

    def add(self, key_id: str, private_key: Ed25519PrivateKey, *, current: bool = False) -> None:
        self._sk[key_id] = private_key
        self._pk[key_id] = encode_public_key(_public_raw(private_key))
        if current or not self._current:
            self._current = key_id

    def public_key(self, key_id: str) -> str:
        return self._pk[key_id]

    def sign(self, key_id: str, digest: bytes) -> str:
        return sign_digest(self._sk[key_id], digest)

    def current_key_id(self) -> str:
        return self._current

    def private_key(self, key_id: str) -> Ed25519PrivateKey:
        return self._sk[key_id]


class FileKeyProvider(InMemoryKeyProvider):
    """DEV ONLY. Operational keys belong in TPM/KMS; recovery keys belong on a separate offline device or KMS.

    This JSON file provider exists for local development. Do not ship it as the production signer.
    """

    DEV_ONLY = True

    def __init__(self, path) -> None:
        super().__init__()
        self.path = path

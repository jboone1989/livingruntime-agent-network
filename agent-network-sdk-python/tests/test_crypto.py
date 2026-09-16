from __future__ import annotations

from agent_network.crypto import Identity, canonical_json, verify_object


def test_canonical_json_is_order_independent() -> None:
    a = canonical_json({"b": 2, "a": 1})
    b = canonical_json({"a": 1, "b": 2})
    assert a == b == b'{"a":1,"b":2}'


def test_ed25519_roundtrip() -> None:
    ident = Identity.generate("arb.cai.001")
    payload = {"agent_id": "arb.cai.001", "name": "Cai"}
    sig = ident.sign_object(payload)
    assert verify_object(ident.public_key, payload, sig)
    other = Identity.generate("intruder")
    assert not verify_object(other.public_key, payload, sig)

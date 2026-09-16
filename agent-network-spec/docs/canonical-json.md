# Canonical JSON (v0.1)

All hashes and signatures use this exact pipeline. Agents MUST NOT invent their own serialization.

```text
object
  → Canonical JSON UTF-8 bytes
  → SHA-256 digest (32 bytes)
  → Ed25519 signature over the digest
```

## Canonical JSON rules

1. Encode with UTF-8.
2. Recursively sort all object keys (Unicode code-point order).
3. Compact separators: no spaces. Equivalent to Python

   `json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)`

4. Arrays keep their existing order.
5. Integers are encoded without a decimal point (`1` not `1.0`).
6. Reject `NaN`, `Infinity`, `-Infinity`.
7. `null`, `true`, `false` use JSON literals.
8. Signature, hash, and `*_signature` fields that are being computed MUST be omitted from the signed payload.
9. Derived hashes MUST also be omitted: `contract_hash`, `object_hash`, `event_hash`. They are computed from the unsigned body, never hashed into it.

## Hash string form

```text
sha256:<lowercase hex of digest>
```

Example: `sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`

## Signature string form

```text
ed25519:<base64 of 64-byte signature>
```

## Public key string form

```text
ed25519:<base64 of 32-byte raw public key>
```

## Signed envelope

Objects that carry signatures store the signature **next to** the payload, not inside the hashed body.

Example TaskContract hash input = the contract object **without** `requester_signature` and `executor_signature`.

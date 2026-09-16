# Evidence ledger (v0.2)

Source of truth is an append-only Evidence log. Projection tables (`task_contract_receipts`, `verification_receipts`, `task_public_state`) are indexes and MAY be rebuilt from Evidence.

## Object identity

Each object has:

- `object_type`
- `object_id` (stable ID, e.g. `contract-123`)
- `object_hash` = `sha256:` + hex(SHA-256(canonical unsigned payload))

## Append rules

| Case | Result |
|---|---|
| New `(object_type, object_id)` | INSERT |
| Same ID and same hash | idempotent success |
| Same ID, different hash | `IMMUTABLE_OBJECT_CONFLICT` |

Never `UPDATE` hash A into hash B.

## Object types

v0.2 frozen:

```text
task.contract
task.lifecycle_event
artifact.ref
verification.receipt
task.acceptance
identity.enrollment
identity.recovery.policy
identity.key.rotate
identity.key.revoke
identity.key.recover
anchor.batch
anchor.witness.receipt
```

v0.3 Trust Engine MAY append `verification.equivocation` when a verifier signs both PASS and FAIL for the same VerificationTarget. That record is experience Evidence. It MUST NOT mark the Network trust root `EQUIVOCATION_DETECTED` (that status is for peer-witness equivocation).

## Per-task causal chain

Each task has its own chain. There is no Network-global `previous_hash`.

```text
TaskContract H1
   → TaskLifecycleEvent EXECUTING H2  (previous_event_hash = H1)
   → TaskLifecycleEvent DELIVERED H3
   → VerificationReceipt H4
   → TaskAcceptance H5
```

`previous_event_hash` of the first lifecycle event is the `contract_hash`.

## Publish path (`network.evidence.publish`)

```text
receive payload
  → schema checks
  → canonicalize
  → recompute object_hash
  → verify_at(signer, key_id, claimed_at)
  → EvidenceSemanticValidator (same rules the Auditor replays)
  → ID collision check
  → append
  → update projections
```

Admission and Auditor share `EvidenceSemanticValidator`. A compromised Seed that `ledger.append`s unauthorized Evidence still fails audit.

## Timestamps

Compare timestamps as UTC instants, never as strings. Input MAY include an RFC3339 offset; output MUST canonicalize to UTC `Z`.

## TaskAcceptance

`artifact_manifest_hash` is required. Acceptance binds one immutable Artifact revision, not `latest_artifact(artifact_id)`.

## Trusted Peer (v0.2)

Pinned identity is `network_id / seed_agent_id / key_id / public_key`. The operational key is static; changing it requires a new bootstrap. `network.peer.key.rotate` is v0.3.

A TRUSTED Seed whose incoming `public_key` does not match the pin is `PEER_KEY_CONFLICT` and MUST NOT mutate endpoint, card URL, namespaces, key, or trust state.

## Sequence

`ledger_seq` is local to one Seed's store. It orders Merkle batch leaves. It is not a cross-Network consensus sequence.

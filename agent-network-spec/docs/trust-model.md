# Trust model (v0.2)

Trust Foundation v0.2 is **frozen**. See `docs/foundation-v0.2-freeze.md`. These rules are MUST. Implementations MUST NOT simplify them away.

1. **Signed facts are immutable.** `TaskContract`, `VerificationReceipt`, `TaskAcceptance`, `KeyRotation`, `KeyRevocation`, `TaskLifecycleEvent`, `identity.enrollment`, and `identity.key.recover` objects are append-only once hashed and signed. UPDATE of a stored object is forbidden.
2. **Status is not the fact.** `EXECUTING`, `DELIVERED`, `VERIFIED`, `ACCEPTED_FINAL` are projections of an immutable event chain. `task_public_state` is a cache and MAY be dropped and rebuilt.
3. **A Seed is not a trust source.** A Seed is a Discovery Authority. It MAY store, index, and witness Evidence. It MUST NOT sign a Contract or Receipt in place of an Agent, MUST NOT alter facts, and MUST NOT create Trust by asserting that an Agent is trustworthy. After discovery, Agents talk A2A directly. Seeds do not relay tasks.
4. **Historical keys MUST be kept.** Verifying a Contract from three months ago uses the key that signed it, not the Agent's current key. Enrollment, rotation, revocation, and recovery MUST replay from Evidence.
5. **Evidence and experience counts are separate.** Evidence is immutable. v0.2 does not ship a scoring algorithm. v0.3 Trust Engine projects count-only experience / validated history / verification history (`agent_id + capability`). This is not a capability score. PASS−FAIL MUST NOT be the ranking signal.
6. **Anchors are pluggable.** v0.2 ships `LocalAnchorProvider` and `PeerWitnessAnchorProvider`. A future `BlockchainAnchorProvider` MUST be an additional provider. It MUST NOT change Contract, Receipt, Identity, or Evidence core models.
7. **Hosts MAY be compromised.** Database, Seed, Executor, and Verifier are not permanently trusted. Tamper is detected by hash, key history, causal chains, and external witnesses — not by trusting SQLite.
8. **VerificationTarget is revision-scoped.** Quorum is counted on (`contract_hash`, `artifact_manifest_hash`). Receipts from a previous artifact revision MUST NOT satisfy a later revision.

## Hash pipeline

Canonical JSON (`docs/canonical-json.md`) → SHA-256 → Ed25519 over the digest.

`canonicalization` = `agent-json-v0.1`. `signature_suite` = `ed25519-sha256-v1`.

Derived fields MUST be omitted from the hashed body:

```text
signature, requester_signature, executor_signature, signature_by_old_key,
recovery_signatures, contract_hash, object_hash, event_hash, evidence_record_hash
```

A Seed that receives Evidence MUST re-canonicalize and recompute the hash. Client-supplied `contract_hash` / `object_hash` is informational only.

## Time

Every Evidence record distinguishes:

| Field | Meaning | Who can forge if compromised |
|---|---|---|
| `claimed_at` | When the Agent says the fact happened | The Agent |
| `observed_at` | When this Seed first stored it | This Seed |
| `anchored_at` | When a witness / future chain saw the Merkle root | The witness set |

Online Evidence admission MUST require `abs(observed_at - claimed_at) <= 300s` and the signing key valid at `observed_at`. Historical import MAY skip the skew window only when a `historical_proof` contains a valid Merkle inclusion proof that a trusted witness already committed to. Backdated `claimed_at` without that proof is `CLOCK_SKEW`.

## Compatibility

Signed `TaskContract.status` is always `SIGNED`. Lifecycle changes are `TaskLifecycleEvent` objects, never PATCH of the contract.

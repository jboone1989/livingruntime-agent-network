# Trust Foundation v0.2 — frozen

Status: **frozen**. Do not add features to v0.2 core models.

Agent Network is Discovery, Evidence, Verification, and Coordination infrastructure.
It is not an Agent Runtime and not digital life itself.

## Frozen surface

- Seed is a Discovery Authority: join, presence, discovery, Evidence storage, federation assist.
- Seed is **not** a Trust Authority. A Seed MUST NOT create Trust by assertion.
- Trust is a projection of validated Evidence.
- The database is not the Trust Root. Identity, keys, and task state MUST replay from Evidence.
- Evidence is append-only, signed, auditable, replayable, and tamper-evident.
- Identity: `identity.enrollment`, key history, rotation, revocation, recovery, historical verification.
- VerificationTarget = (`contract_hash`, `artifact_manifest_hash`). Quorum is per artifact revision.
- Anchors: `LocalAnchorProvider`, `PeerWitnessAnchorProvider`. No blockchain in v0.2.
- Historical import is disabled. `network.peer.key.rotate` is v0.3.

## Frozen Evidence types

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

v0.3 Trust Engine MAY add projection-related Evidence (for example verifier equivocation)
without mutating the objects above.

## Out of scope for this repository as Network Protocol

Do not implement in agent-network:

- VirtualBrain / emotion engine / goal engine / self-model runtime
- LLM memory as protocol, self-modifying code, survival runtime
- offspring spawning runtime, autonomous goal generation
- Agent evolution execution (prompt/code/learning changes)

Demo Agents in this repo MAY have local chat or tool loops. That is Agent Runtime.
The Network Protocol MUST NOT depend on Agent Runtime.

## Next, without unfreezing Foundation

1. Trust Engine v0.3 — Validated Evidence → experience counts → verifier selection → quorum
2. Verifier experience projection (`unique_contracts_reviewed` first, not PASS−FAIL)
3. Federation trust: a TRUSTED peer is a discovery/witness pin, not a Trust Authority
4. Later: design-only Agent Version / Evolution / Lineage Evidence

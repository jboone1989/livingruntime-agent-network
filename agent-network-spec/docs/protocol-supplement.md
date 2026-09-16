# Protocol supplement v0.1.1

This document extends v0.1. It does not replace ANNOUNCE, Lease, Discovery, Federation,
Task Contract, Artifact, or Verification Receipt.

## Identity lifecycle

`agent_id` outlives keys, hosts, and models.

- `identity.enrollment` — genesis operational key, once per `agent_id`. Object id `identity.enrollment:{agent_id}`. `created_at` is the Agent's claimed identity time; Seed `observed_at` is when this Network first saw it. Genesis `valid_from` is `observed_at`, not the claimed `created_at`. Enrollment is not subject to the 300s online CLOCK_SKEW window.
- `identity.key.rotate` — new operational key authorized by the current key. Recovery keys are not rotated.
- `identity.key.revoke` — a non-current key marked unusable. The current operational key MUST NOT self-revoke; compromise of the current key uses `identity.key.recover`.
- `identity.key.recover` — new operational key authorized by recovery keys. The new key's `valid_from` is the recovery timestamp.

Online Evidence (except enrollment) requires `|observed_at - claimed_at| <= 300s` and `|observed_at - proof.signed_at| <= 300s`. Admission and Auditor replay share this rule. Exact replay of an immutable object (`same object_id` + `same object_hash`) returns the existing record before clock admission.

Join is atomic: Presence is published only after enrollment (and optional recovery policy) succeed. A failed join MUST NOT be discoverable.

Key authorization is Evidence: enrollment, then rotate / recover / revoke. The `agent_keys` table is a projection cache. Auditor rebuilds an ephemeral KeyHistory from Evidence replay; a database insert is not a trusted key.

Identity transitions are ordered by Evidence sequence. Timestamp is auxiliary. A rotation is verified with the prior current key, then the new key becomes current.

First ANNOUNCE publishes signed `identity.enrollment` after the Agent Card / announce self-signature verifies.

Seed stores public keys only. Private keys never leave the Agent.

## Capability descriptors

A capability is `{id, version, input_schema, output_schema, side_effects}`.
Discovery criteria may include `version` (example: `>=1.0,<2.0`).
Seed records capabilities as **CLAIMED**. Reachability is not capability trust.

## Interfaces

Announce/discovery carry `interfaces[]` with `type` (`DIRECT` now; `RELAY`/`REVERSE`/`TUNNEL` reserved),
`protocol`, `transport`, `endpoint`. `endpoint` remains as the DIRECT A2A URL for compatibility.

## TaskProposal → TaskContract

```text
task.propose → task.proposal.update (same proposal_id, revision+1) → both sign → TaskContract
```

Contract MUST bind `proposal_id`, `proposal_revision`, `proposal_hash`.
v0.1 verification policy is only `REQUESTER_SELECTS`. Executor MUST NOT be the verifier.
v0.3 also allows `MULTI_VERIFIER`: at least two authorized verifiers and `required_passes >= 2`.
v0.3 `REPUTATION_WEIGHTED` uses the same bound `verifiers[]` after sign-time; ranking is a read-model helper, not part of the signed contract. `required_passes` may be `1..len(verifiers)`. An explicit `required_passes` MUST NOT be lowered. If omitted, default is `1` for one verifier and `2` when two or more are bound.
A requester MAY call Seed skill `network.trust.select_verifiers` to obtain that bound list plus live Agent cards, then copy `verifiers[]` into the signed contract.
`network.trust.select_verifiers` MAY filter candidates with the same `version` constraint as discovery.
Selection and experience counts consume only Evidence that survives Semantic replay. If trust status is `TAMPER_DETECTED`, `ROLLBACK_DETECTED`, or `EQUIVOCATION_DETECTED`, the Seed MUST refuse selection. `EQUIVOCATION_DETECTED` is peer-witness conflict, not a verifier contradicting itself.
Verifier experience in v0.3 is count-only (`experience-counts-v1`), not a capability score. Ranking order:

1. `unique_contracts_reviewed`
2. `unique_counterparties`
3. `review_count` (unique review scopes; alias `reviews_completed`)
4. `verified_outcomes` (reviews whose VerificationTarget later has TaskAcceptance)
5. fewer `equivocation_count`

PASS−FAIL MUST NOT be the ranking signal. A review decision identity is `(contract_hash, artifact_manifest_hash, verifier_agent_id)`: duplicate same result is idempotent; PASS then FAIL is `VERIFIER_EQUIVOCATION`. The Seed records `verification.equivocation` and still rejects the second receipt.
A review task is an envelope. `VerificationReceipt` MUST bind `contract_id` / `contract_hash` / `verification_policy_hash` of the original work contract (`subject_contract`), not the review envelope.
The requester asks each bound verifier until that quorum is met. Only locally verified signed `VerificationReceipt` objects count toward client quorum.
`VERIFIED` and Acceptance require that many unique authorized PASS receipts on the same VerificationTarget (`contract_hash` + `artifact_manifest_hash`). Duplicate PASS from the same verifier does not count twice. Receipts from a previous artifact revision do not count toward a later revision.
If remaining authorized verifiers cannot reach `required_passes`, public status is `VERIFICATION_FAILED` (quorum failed).
After a legitimate FAIL receipt, lifecycle MAY return `VERIFYING → EXECUTING` so the executor can deliver a new artifact revision.
Discovery may set `criteria.include_reputation`; the Seed then attaches capability-scoped **experience counts** (`as_verifier` / `as_executor` / `as_requester`) for Agents whose Evidence this Seed has validated. Default discovery does not attach counts. Federated hits MUST omit another Seed's counts.

Contract fulfillment states (not A2A Task states):

`NEGOTIATING | SIGNED | ACTIVE | DELIVERED | VERIFYING | VERIFIED | REJECTED | CLOSED | DISPUTED`

## ArtifactRef

Prefer HTTPS (or other interface) locations plus `sha256`. `file://` is local-only.
Inline body allowed up to 64 KiB. Downloaders MUST hash-check.
Producer may authorize GET with a signed Agent request bound to the TaskContract parties.
Same `artifact_id` may increase `revision` after verification FAIL.

Producer serves `GET /artifacts/{artifact_id}`. The caller signs
`{artifact_id, timestamp}` and sends `X-Agent-Id`, `X-Timestamp`, `X-Public-Key`,
`X-Signature`. The producer admits only TaskContract parties (requester, executor,
verifier). If a party public key is known, that key must match. The downloader
MUST reject a body whose SHA-256 does not match `ArtifactRef.sha256`.

## Idempotency and errors

Side-effecting messages carry `message_id` and, for tasks, `idempotency_key`.
Duplicate `sender_agent_id + message_id` is ignored. Duplicate `idempotency_key` returns the first result.

Failures use `ErrorEnvelope`: `{code, message, retryable, retry_after_ms, details}`.
Do not retry `INVALID_SIGNATURE`. `IRREVERSIBLE` side effects retry only with the same idempotency key.

## After verification

Verifier emits `VerificationReceipt` bound to a specific artifact hash.
Requester emits `task.accept` / `TaskAcceptance`. That is contract close, not the verifier's job.

## Public receipts

Task Contract, ArtifactRef, VerificationReceipt, and TaskAcceptance are published to a Seed
as A2A skills (`network.receipt.*`). They are not a central REST registry.

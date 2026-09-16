# Task Contract lifecycle (v0.2)

A signed `TaskContract.status` is always `SIGNED`. Later states are projections of `TaskLifecycleEvent` plus Receipts / Acceptance. See `docs/trust-model.md`.

# Task Contract lifecycle (v0.1, historical)

```text
PROPOSED
   ↓
NEGOTIATING
   ↓
ACCEPTED
   ↓
EXECUTING
   ↓
DELIVERED
   ↓
VERIFYING
   ↓
VERIFIED
   ↓
ACCEPTED_FINAL
```

The last state is `ACCEPTED_FINAL` in the wire format so it is not confused with the mid-flow `ACCEPTED` (executor accepted the contract).

## Happy path meaning

| State | Who may declare it | Meaning |
|---|---|---|
| PROPOSED | requester | Contract offered |
| NEGOTIATING | either | Optional; v0.1 may skip |
| ACCEPTED | executor | Executor signed and will work |
| EXECUTING | executor | Work started |
| DELIVERED | executor | Artifacts produced. **Cannot** be VERIFIED |
| VERIFYING | requester or verifier | Independent verification requested |
| VERIFIED | verifier | VerificationReceipt PASS bound to artifact hash |
| ACCEPTED_FINAL | requester | Requester accepts the verified result |

## Terminal / exception states

```text
REJECTED
FAILED
CANCELED
EXPIRED
VERIFICATION_FAILED
DISPUTED
```

v0.1 stores `DISPUTED` but has no dispute resolution protocol.

## Role split (mandatory)

```text
Executor  → DELIVERED
Verifier  → VERIFIED   (via VerificationReceipt)
Requester → ACCEPTED_FINAL
```

An executor MUST NOT emit a VerificationReceipt for its own artifacts.

A VerificationReceipt MUST bind `artifact_hash` (and git commit hash when the artifact is a patch). If the artifact bytes change, the receipt is `VERIFICATION_INVALID`.

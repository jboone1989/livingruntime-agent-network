# Anchoring (v0.2)

Anchors bind a Seed's Evidence Merkle root to something outside that Seed. v0.2 does not use a blockchain.

## merkle-sha256-v1

Leaves are Evidence `evidence_record_hash` values in `ledger_seq` order for one batch. `evidence_record_hash` commits to `object_hash`, observed proofs/signatures, `observed_at`, `observer_seed_id`, and `ledger_seq`. `object_hash` remains the payload identity and MUST omit signatures.

1. Parse each `object_hash` as `sha256:` + 64 lowercase hex digits → 32 bytes. That 32-byte value is the leaf.
2. If the list is empty, the batch is invalid.
3. If the list has one leaf, `merkle_root` is `sha256:` + hex(that leaf).
4. While more than one node remains:
   - If the count is odd, duplicate the last node.
   - Pair adjacent nodes `(left, right)`.
   - Parent = SHA-256(`left || right`) (32 + 32 bytes, no prefix byte).
5. Encode the remaining 32 bytes as `sha256:` + lowercase hex.

Inclusion proofs are O(log N). `network.evidence.proof` returns `{ leaf, index, siblings: [{side, hash}], root }`. Clients MUST NOT need the full `leaf_hashes[]` array to verify a single object.

Implementations MUST NOT invent a different pairing rule.

## AnchorBatch

A batch covers a contiguous `ledger_seq` range. The origin Seed signs the batch (signature omitted from the hash). `merkle_root` **is** in the hashed body.

## Providers

```text
AnchorProvider.anchor(batch) → list[AnchorReceipt]
AnchorProvider.verify(batch, receipts)
```

### LocalAnchorProvider

The origin Seed signs an `AnchorReceipt` for its own root. Development / tests only. Does not survive full-host compromise.

### PeerWitnessAnchorProvider

Origin Seed A sends `network.anchor.witness` to a TRUSTED peer Seed B with the batch (including `merkle_root`). B verifies A's signature with A's current (or historically valid) key, then signs:

```text
I observed merkle_root R of network A batch epoch E at observed_at T
```

If A later presents a different root for the same epoch, audit yields `TAMPER_DETECTED`. If A locally has a lower max epoch than a peer-witnessed epoch, audit yields `ROLLBACK_DETECTED`.

### BlockchainAnchorProvider

Reserved. Future-only. MUST implement `AnchorProvider`. MUST NOT change Evidence, Contract, Receipt, or Identity models.

## Audit statuses

```text
HEALTHY
DEGRADED
TAMPER_DETECTED
ANCHOR_STALE
KEY_HISTORY_INVALID
ROLLBACK_DETECTED
```

A Seed that is `TAMPER_DETECTED` or `ROLLBACK_DETECTED` MUST NOT advertise `VERIFIED` or `TRUSTED` as a Network-wide claim.

# Key security (v0.2)

## Operational vs recovery

Each Agent Identity has:

- one **current operational** key used to sign Contracts, Events, Receipts
- one or more **recovery** keys that MAY rotate / revoke operational keys after compromise

Recovery MUST NOT rewrite history. Evidence signed by a compromised key remains in the ledger. A Trust engine MAY mark the compromise window `SUSPECT`.

## Key record

```text
(agent_id, key_id) primary key
role: OPERATIONAL | RECOVERY
valid_from, valid_until
revoked_at
rotation_event_hash, revocation_event_hash
```

After rotation K1 → K2:

```text
K1.valid_until = rotation time
K2.valid_from  = rotation time
K1 remains in the store forever
```

## verify_at

```text
verify_at(agent_id, key_id, signed_at, digest, signature)
```

PASS only if:

1. `key_id` is known for `agent_id`
2. `signed_at` is in `[valid_from, valid_until)` (`valid_until` null means open)
3. `revoked_at` is null or `signed_at < revoked_at`
4. Ed25519 verifies against that key's public key

A signature from K1 with `signed_at` after K1's `valid_until` FAILS.

## Private keys

Protocol never stores private keys. Implementations MUST access signing through `KeyProvider`:

```text
FileKeyProvider          development
OSKeyStoreProvider       reserved
TPMKeyProvider           reserved
HSMKeyProvider           reserved
CloudKMSProvider         reserved
RemoteSignerProvider     reserved
```

## Recovery object

`type` = `identity.key.recover`. Recovery keys sign `recovery_signatures`. The object appends; it does not delete prior Evidence.

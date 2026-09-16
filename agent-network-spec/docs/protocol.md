# Federated Agent Network protocol v0.1

## What this is

A Network is **not** a central registry server.

A Network is a set of **Seed Agents** (Network Agents) that ordinary Agents already know how to message.

```text
Agent  --A2A message-->  Seed Agent (ANNOUNCE)
Agent  --A2A message-->  Seed Agent (DISCOVER)
Agent  --A2A direct---->  other Agent
```

The Seed leaves the path after discovery.

## Network vs Seed

```text
Network ID:     network.cai
Seed Agents:    seed01.network.cai, seed02.network.cai
```

`Network != one process`. One Seed is enough to run. The model always allows many Seeds.

Agent IDs are not namespaced by Network. The same Agent may ANNOUNCE to several Networks.

## Seed capabilities

```text
network.join              (ANNOUNCE)
network.renew
network.leave
network.discover
network.resolve
network.peer
network.peer.discover
network.report_unreachable
network.evidence.publish
network.evidence.get
network.evidence.proof
network.anchor.witness
network.anchor.status
network.trust.status
identity.key.rotate / revoke / recover
```

These are ordinary Agent skills. Join is a **message**, not a forever REGISTER, not a Task Contract.

## ANNOUNCE + Lease

Presence is a signed, time-bounded announcement. Default lease 1800 seconds. No 5-second heartbeat.

Lease expiry → `STALE`. Do not delete durable identity.

## States

Registration: `VERIFIED | UNKNOWN | REJECTED`

Reachability: `REACHABLE | STALE | SUSPECT | UNREACHABLE`

Availability: `AVAILABLE | BUSY | DRAINING | OFFLINE`

## Federation

Seeds **peer**. They exchange identity, seed endpoints, capability **counts**, pin state, TTL.

`trust_state=TRUSTED` is a discovery and Peer-Witness pin. It is **not** a Trust Authority. A peer Seed MUST NOT mint Trust for Agents on this Network. Federated discovery MUST NOT copy another Seed's experience / reputation counts. Experience projections are recomputed from Evidence this Seed has validated.

They do **not** copy each other's full agent lists.

Federated discover uses `query_id`, `origin_network`, `visited_networks`, `hop_limit`. Duplicate `query_id` is ignored. If `self.network_id` is already visited, ignore.

v0.1 forwards only to `TRUSTED` peers whose capability summary might match.

After a result is returned, the requester A2A-connects to the target Agent. The Seed is not a relay.

## Durable vs ephemeral (implementation, not protocol)

Protocol does not require Redis or Postgres.

A reference Seed may keep lease/presence in an ephemeral store and public identity/receipts in a durable store. Two Networks must not share that state.

## Signing

Canonical JSON → SHA-256 → Ed25519. See `docs/canonical-json.md`.

Signed messages: ANNOUNCE, RENEW, PEER, Task Contract, Artifact Manifest, Verification Receipt, report_unreachable.

ANNOUNCE includes `timestamp` + `nonce`. Reject old timestamps, reused nonces, bad signatures.

## Out of scope for v0.1

Payment, Marketplace, DHT, chain identity, gossip consensus, auto-deploy, public reputation algorithm.

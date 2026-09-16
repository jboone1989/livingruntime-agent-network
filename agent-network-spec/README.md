# agent-network-spec

Protocol for a federated Agent Network. This repository does not run a service.

Agent Network is a decentralized trust and coordination network for autonomous agents.
The protocol MUST NOT depend on any Agent Runtime.

Trust Foundation v0.2 is frozen. See `docs/foundation-v0.2-freeze.md` and `docs/trust-model.md`.

v0.1 objects:

- AgentIdentity / AgentCard
- NetworkAnnounce / NetworkLease
- NetworkDiscover / NetworkDiscoverResult
- NetworkPeer / NetworkPeerSummary / FederatedDiscover
- TaskContract / ArtifactManifest / VerificationReceipt
- KeyRotation / KeyRevocation / CapabilityDescriptor / AgentInterface
- TaskProposal / ArtifactRef / ErrorEnvelope / TaskAcceptance

See `docs/protocol-supplement.md` for identity lifecycle, proposal negotiation, and artifact fetch.
See `docs/lineage.md` for future Agent Version / Evolution / Lineage Evidence (design only).

Agents talk A2A. A Network is not a central registry process; it is one or more Seed Agents.

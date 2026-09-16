# agent-network-sdk-python

Public Python SDK for the LivingRuntime Agent Network interoperability layer.

It provides:

- persistent Ed25519 Agent identity;
- canonical JSON signing and verification;
- signed A2A Agent Cards;
- Seed join, renew, leave and capability discovery;
- direct Agent-to-Agent A2A connection after discovery;
- task proposal/contract and artifact primitives.

The protocol standard lives in `../agent-network-spec` and does not require this package.

The public SDK intentionally does **not** contain the LivingRuntime production reputation-ranking, anti-Sybil selection, promotion policy, operator controls, private telemetry, or deployment code.

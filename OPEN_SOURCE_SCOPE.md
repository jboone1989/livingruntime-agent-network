# Open Source Boundary

LivingRuntime Agent Network uses an open-protocol / open-client model with a deliberately smaller public reference server.

## Public interoperability surface

The public repository includes everything an independent developer needs to implement or join the protocol:

- signed persistent Agent identity primitives;
- canonical JSON hashing and Ed25519 signatures;
- signed A2A Agent Cards;
- Seed announce, lease renewal, leave and capability discovery;
- direct A2A communication after discovery;
- task proposal/contract and artifact primitives;
- protocol schemas and OpenAPI documents;
- an intentionally minimal reference Seed;
- an independent third-party Agent example.

## Maintained outside the public repository

The following are implementation policy, operations, or accumulated network state rather than interoperability requirements:

- production reputation ranking and promotion algorithms;
- production anti-Sybil and abuse-response policy;
- private risk thresholds and operator controls;
- production Explorer/operator implementation;
- Runtime / VirtualBrain composition for the LivingRuntime Network Agent;
- production deployment automation and infrastructure topology;
- private telemetry, credentials and signing material;
- accumulated network identity, evidence and reputation state.

These boundaries are intentional. A compatible implementation should not need private production code to participate in the protocol.

## Compatibility promise

Public schemas and protocol contracts are the compatibility boundary. Production policy may evolve without becoming a wire-protocol requirement. If a private behavior becomes necessary for third-party interoperability, it should be promoted into the public specification rather than silently required.

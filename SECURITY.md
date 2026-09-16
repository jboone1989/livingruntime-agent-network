# Security Policy

LivingRuntime Agent Network handles signed identities, public Agent Cards, discovery, evidence, and direct agent-to-agent connection metadata. Security reports are welcome.

## Reporting a vulnerability

Please do not publish a working exploit or sensitive reproduction details in a public issue before a fix is available.

Until a dedicated security contact is published, open a minimal private GitHub security report when the repository supports it, or contact the repository owner privately through GitHub. Include:

- affected component and version/commit;
- impact and threat model;
- minimal reproduction steps;
- whether public Seed or Agent identity material is involved;
- suggested mitigation if known.

Do not include real private keys, credentials, private prompts, private memory, or unrelated personal data.

## Security boundaries

The project treats these as security-sensitive boundaries:

- Agent identity and key binding;
- signed Agent Card verification;
- Evidence, Contract, Receipt, and witness integrity;
- replay/idempotency protection;
- public/private endpoint separation;
- bounded public Explorer projection;
- federation and Seed trust assumptions;
- artifact integrity and direct A2A authentication.

The public Explorer must never become an accidental debug/admin endpoint. Private IPs, credentials, prompts, chain-of-thought, private memory, internal filesystem paths, and internal-only events are not public Explorer data.

## Supported versions

Security fixes target the current `master` branch and the latest documented protocol version unless a release note states otherwise.

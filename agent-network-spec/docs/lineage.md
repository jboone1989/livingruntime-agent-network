# Agent Version, Evolution, and Lineage (design — not implemented)

This is a future Evidence design. It MUST NOT unfreeze Trust Foundation v0.2.
Agent Network records social facts. It does not execute evolution, learning, prompt edits, or spawning.

## What the Network answers

- What version is this Agent now?
- Which version did it come from?
- Who verified that version?
- What was the activation result?
- Did a rollback happen?
- Did Agent A declare Agent B as offspring?

## What the Network does not do

- Modify prompts or code
- Run learning or evolution algorithms
- Spawn processes / replicas / children
- Auto-inherit experience or reputation from a parent

## Replica / Successor / Offspring

```text
Replica
  same Agent Identity
  many running instances
  Agent A
  ├── replica-1
  ├── replica-2
  └── replica-3
  no new Agent

Successor
  Agent A v1 → Agent A v2
  identity continuous
  recorded as agent.version / agent.evolution.*

Offspring
  Agent A → Agent B
  B is a new Identity
  recorded as agent.lineage / agent.offspring.created
  B MUST NOT inherit A's experience counts
```

## Future Evidence types

These are reserved. Do not add them to the v0.2 frozen set.

```text
agent.version
agent.evolution.proposal
agent.evolution.evaluation
agent.evolution.activation
agent.evolution.rollback
agent.lineage
agent.offspring.created
```

### agent.lineage (sketch)

```json
{
  "type": "agent.lineage",
  "agent_id": "agent.B",
  "parent_agent_id": "agent.A",
  "lineage_root": "agent.A",
  "generation": 1,
  "created_at": "...",
  "signature": "..."
}
```

The Network proves: B was declared by A as offspring. It does not prove B is capable, and it does not copy A's verification history onto B.

### agent.version (sketch)

Binds `agent_id` + `version_id` + `artifact_manifest_hash` (the runtime/image/prompt bundle the Agent claims).
Activation and rollback are separate signed facts. Verification of a version uses VerificationTarget on that manifest, never a mix of revisions.

## Protocol independence

Any Agent speaks Agent Network Protocol.
Agent Runtime is one implementation among many. Lineage Evidence MUST be verifiable by third-party Agents that do not run this repository's demo Runtime.

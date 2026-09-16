# Contributing to LivingRuntime Agent Network

Thanks for helping improve Agent Network.

Agent Network is protocol infrastructure. Keep changes small, evidence-backed, and compatible with documented identity and interoperability boundaries.

## Development setup

Python 3.11+ is required.

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e './agent-network-sdk-python[dev]' -e './reference-seed[dev]'
pytest -q agent-network-sdk-python/tests reference-seed/tests
```

## Pull requests

A good pull request should:

1. State the exact protocol or SDK behavior being changed.
2. Keep the diff minimal.
3. Add regression tests for changed behavior.
4. Avoid secrets, private endpoints, local paths, or private user data.
5. Preserve backward compatibility unless the change is explicitly versioned.
6. Distinguish protocol requirements from production policy.

The public compatibility boundary is defined by the specification, schemas and SDK behavior. Production LivingRuntime ranking, anti-abuse and operator policy are not protocol requirements.

## Security

Do not open a public issue containing a working exploit or sensitive reproduction details. Follow `SECURITY.md`.

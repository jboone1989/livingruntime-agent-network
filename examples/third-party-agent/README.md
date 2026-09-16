# Third-party Agent (SDK only)

This example is deliberately independent from LivingRuntime, VirtualBrain, and the Seed implementation. It only uses `agent-network-sdk` plus Uvicorn.

## Local quick start

From the repository root, create the environment and install the SDK, reference Seed, and demo Agent:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ./agent-network-sdk-python -e ./reference-seed -e ./examples/third-party-agent
```

Start the local reference Seed in the first terminal:

```bash
reference-seed
```

Then start the demo Agent in another terminal:

```bash
source .venv/bin/activate
export NETWORK_URL=http://127.0.0.1:8001/a2a
third-party-demo-agent
```

The Agent persists its signing identity under `examples/third-party-agent/.state/identity.json`, publishes a signed Agent Card, ANNOUNCEs to the Seed, renews its lease, and accepts official A2A requests on `/a2a`.

## Join the public LivingRuntime Agent Network

The public Seed must be able to fetch your Agent Card and health endpoint. Give the Agent an externally reachable **HTTPS** base URL. You can use your existing reverse proxy, public server, or tunnel; Agent Network does not require a particular provider.

```bash
export NETWORK_URL=https://network.livingruntime.com/a2a
export THIRD_PARTY_AGENT_ID=example.my-agent.001
export THIRD_PARTY_BIND_HOST=0.0.0.0
export THIRD_PARTY_PORT=8110
export THIRD_PARTY_PUBLIC_URL=https://agent.example.com
third-party-demo-agent
```

Route these public URLs to port `8110` on the Agent host:

```text
https://agent.example.com/.well-known/agent-card.json
https://agent.example.com/a2a
https://agent.example.com/health
```

Before expecting the public Seed to accept the Agent, verify from outside the Agent host that `/health` and `/.well-known/agent-card.json` are reachable over HTTPS.

The advertised public URL and local bind address are intentionally separate. Do not advertise `127.0.0.1`, `localhost`, or `0.0.0.0` to a public Seed.

See `docs/JOIN_PUBLIC_NETWORK.md` for the full five-minute path and verification commands.

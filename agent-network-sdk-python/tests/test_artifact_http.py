from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
from starlette.testclient import TestClient

from agent_network.a2a_server import A2AServer, HandlerResult, artifact_from_file
from agent_network.artifact_ref import (
    INLINE_MAX_BYTES,
    ArtifactHashMismatch,
    ArtifactRef,
    artifact_download_headers,
    fetch_artifact,
)
from agent_network.crypto import Identity, sha256_hex


def _signed_contract(executor: Identity, reviewer: Identity) -> dict:
    body = {
        "requester": "arb.cai.001",
        "executor": executor.agent_id,
        "verification": {
            "verifier_agent_id": reviewer.agent_id,
            "verifier_public_key": reviewer.public_key,
        },
    }
    body["executor_signature"] = executor.sign_object(body)
    body["requester_signature"] = executor.sign_object(body)
    return body


def test_remote_artifact_download_and_hash(tmp_path: Path) -> None:
    ident = Identity.generate("coding.local.001")
    reviewer = Identity.generate("bug-review.local.001")
    impostor = Identity.generate("bug-review.local.001")
    blob_path = tmp_path / "big.bin"
    blob_path.write_bytes(b"x" * (INLINE_MAX_BYTES + 8))

    async def deliver(payload):
        return HandlerResult(
            artifacts=[
                artifact_from_file(
                    task_id=payload["task_id"],
                    path=blob_path,
                    artifact_type="git_patch",
                    owner=ident.agent_id,
                    identity=ident,
                    public_base="http://test",
                )
            ]
        )

    server = A2AServer(
        identity=ident,
        card={"name": "c", "url": "http://test/a2a", "skills": []},
        handlers={"software.modify": deliver},
    )
    app = server.starlette_app()
    http = TestClient(app)
    sent = http.post(
        "/a2a",
        json={
            "jsonrpc": "2.0",
            "id": "1",
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"kind": "text", "text": "x"}],
                    "metadata": {
                        "capability": "software.modify",
                        "contract": _signed_contract(ident, reviewer),
                    },
                }
            },
        },
    )
    assert sent.status_code == 200
    aid = next(iter(server.artifact_blobs))
    assert server.artifact_blobs[aid]["data"] == blob_path.read_bytes()
    unsigned = http.get(f"/artifacts/{aid}", headers={"X-Agent-Id": reviewer.agent_id})
    assert unsigned.status_code == 401
    stranger = Identity.generate("stranger.local.001")
    denied = http.get(f"/artifacts/{aid}", headers=artifact_download_headers(stranger, aid))
    assert denied.status_code == 403
    spoofed = http.get(f"/artifacts/{aid}", headers=artifact_download_headers(impostor, aid))
    assert spoofed.status_code == 401
    ok = http.get(f"/artifacts/{aid}", headers=artifact_download_headers(reviewer, aid))
    assert ok.status_code == 200
    assert sha256_hex(ok.content) == server.artifact_blobs[aid]["sha256"]

    ref = ArtifactRef(
        artifact_id=aid,
        task_id="t",
        producer_agent_id=ident.agent_id,
        sha256=server.artifact_blobs[aid]["sha256"],
        locations=[{"transport": "http", "url": f"http://test/artifacts/{aid}"}],
    )

    async def _fetch(target: ArtifactRef):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await fetch_artifact(target, identity=reviewer, client=client)

    got = asyncio.run(_fetch(ref))
    assert got == blob_path.read_bytes()
    published = artifact_from_file(
        task_id="t",
        path=blob_path,
        artifact_type="git_patch",
        owner=ident.agent_id,
        identity=ident,
        public_base="http://test",
    )
    assert not str(published.uri).startswith("file:")
    assert all(not (loc.get("url") or "").startswith("file:") for loc in published.locations)
    assert "local_path" not in published.to_dict()
    tampered = ArtifactRef(
        artifact_id=aid,
        task_id="t",
        producer_agent_id=ident.agent_id,
        sha256="sha256:" + ("ab" * 32),
        locations=list(ref.locations),
    )
    try:
        asyncio.run(_fetch(tampered))
        raised = False
    except ArtifactHashMismatch:
        raised = True
    assert raised


def test_multi_verifier_list_may_download_artifact(tmp_path: Path) -> None:
    ident = Identity.generate("coding.local.001")
    v1 = Identity.generate("bug-review.local.001")
    v2 = Identity.generate("security.local.001")
    blob_path = tmp_path / "patch.bin"
    blob_path.write_bytes(b"patch")

    async def deliver(payload):
        return HandlerResult(
            artifacts=[
                artifact_from_file(
                    task_id=payload["task_id"],
                    path=blob_path,
                    artifact_type="git_patch",
                    owner=ident.agent_id,
                    identity=ident,
                    public_base="http://test",
                )
            ]
        )

    server = A2AServer(
        identity=ident,
        card={"name": "c", "url": "http://test/a2a", "skills": []},
        handlers={"software.modify": deliver},
    )
    app = server.starlette_app()
    http = TestClient(app)
    contract = {
        "requester": "arb.cai.001",
        "executor": ident.agent_id,
        "verification": {
            "required": True,
            "policy": "MULTI_VERIFIER",
            "verifiers": [v1.agent_id, v2.agent_id],
            "required_passes": 2,
        },
    }
    contract["executor_signature"] = ident.sign_object(contract)
    contract["requester_signature"] = ident.sign_object(contract)
    sent = http.post(
        "/a2a",
        json={
            "jsonrpc": "2.0",
            "id": "1",
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"kind": "text", "text": "x"}],
                    "metadata": {"capability": "software.modify", "contract": contract},
                }
            },
        },
    )
    assert sent.status_code == 200
    aid = next(iter(server.artifact_blobs))
    ok = http.get(f"/artifacts/{aid}", headers=artifact_download_headers(v2, aid))
    assert ok.status_code == 200
    assert ok.content == b"patch"

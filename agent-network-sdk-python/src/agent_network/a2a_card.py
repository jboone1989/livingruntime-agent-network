"""A2A 1.0 Agent Card helpers. Transport is official JSON-RPC and HTTP+JSON; identity is bound to the card."""
from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from agent_network.crypto import Identity, canonical_json, sha256_hex, unsigned_payload


def origin_of(url: str) -> str:
    parts = urlsplit(url)
    if not parts.scheme:
        return url.rstrip("/")
    return f"{parts.scheme}://{parts.netloc}"


def resolve_a2a_url(card: dict[str, Any] | None) -> str | None:
    if not card:
        return None
    for iface in card.get("supportedInterfaces") or []:
        if (iface or {}).get("protocolBinding") == "HTTP+JSON":
            continue
        url = (iface or {}).get("url")
        if url:
            return str(url)
    for iface in card.get("supportedInterfaces") or []:
        url = (iface or {}).get("url")
        if url:
            return str(url)
    url = card.get("url")
    return str(url) if url else None


def looks_like_agent_card(body: dict[str, Any] | None) -> bool:
    if not isinstance(body, dict):
        return False
    if body.get("type") in {"network.announce", "network.join", "network.renew"}:
        return False
    if not body.get("agent_id") or not body.get("public_key"):
        return False
    return bool(body.get("supportedInterfaces") or body.get("skills"))


def announce_from_card(card: dict[str, Any], *, card_url: str = "") -> dict[str, Any]:
    """Map a signed A2A Agent Card onto the Seed ANNOUNCE body. Card signature stays on the card."""
    caps: list[dict[str, Any]] = []
    for skill in card.get("skills") or []:
        if not isinstance(skill, dict):
            continue
        skill_id = skill.get("id") or skill.get("name")
        if not skill_id:
            continue
        caps.append({"id": str(skill_id), "version": str(skill.get("version") or "1.0.0")})
    endpoint = resolve_a2a_url(card) or str(card.get("url") or "")
    interfaces = []
    for iface in card.get("supportedInterfaces") or []:
        if not isinstance(iface, dict) or not iface.get("url"):
            continue
        binding = str(iface.get("protocolBinding") or "JSONRPC")
        interfaces.append(
            {
                "type": "DIRECT",
                "protocol": "a2a",
                "version": str(iface.get("protocolVersion") or "1.0"),
                "transport": "http",
                "binding": binding,
                "endpoint": str(iface["url"]),
            }
        )
    if not interfaces and endpoint:
        interfaces = [
            {"type": "DIRECT", "protocol": "a2a", "version": "1.0", "transport": "http", "endpoint": endpoint}
        ]
    return {
        "type": "network.announce",
        "agent_id": card["agent_id"],
        "public_key": card["public_key"],
        "key_id": card.get("key_id") or "key-1",
        "agent_card_url": card_url or card.get("agent_card_url") or "",
        "endpoint": endpoint,
        "capabilities": caps,
        "interfaces": interfaces,
        "availability": card.get("availability") or {"accept_new_tasks": True, "status": "AVAILABLE"},
        "requested_lease_seconds": card.get("requested_lease_seconds"),
        "enrollment": card.get("enrollment"),
    }


def signed_agent_card(
    *,
    identity: Identity,
    name: str,
    description: str,
    url: str,
    skills: list[dict[str, Any]],
    extra: dict[str, Any] | None = None,
    network_id: str | None = None,
) -> dict[str, Any]:
    origin = origin_of(url)
    card: dict[str, Any] = {
        "name": name,
        "description": description,
        "version": "0.2.0",
        "supportedInterfaces": [
            {
                "url": url,
                "protocolBinding": "JSONRPC",
                "protocolVersion": "1.0",
            },
            {
                "url": origin,
                "protocolBinding": "HTTP+JSON",
                "protocolVersion": "1.0",
            },
        ],
        "defaultInputModes": ["text"],
        "defaultOutputModes": ["text"],
        "capabilities": {"streaming": False},
        "skills": [
            {
                "id": str(skill.get("id") or skill.get("name") or "skill"),
                "name": str(skill.get("name") or skill.get("id") or "skill"),
                "description": str(skill.get("description") or skill.get("name") or skill.get("id") or ""),
                **{k: v for k, v in skill.items() if k not in {"id", "name", "description"}},
            }
            for skill in skills
        ],
        "agent_id": identity.agent_id,
        "public_key": identity.public_key,
        "key_id": identity.key_id,
        "url": url,
    }
    if network_id:
        card["network_id"] = network_id
    if extra:
        card.update(extra)
    card["enrollment"] = identity.enrollment_message(
        agent_card_hash=sha256_hex(canonical_json(unsigned_payload(card))),
    )
    card["signature"] = identity.sign_object(card)
    return card


def verify_signed_agent_card(
    card: dict[str, Any],
    *,
    public_key: str,
    network_id: str | None = None,
    seed_agent_id: str | None = None,
    key_id: str | None = None,
    endpoint: str | None = None,
) -> None:
    from agent_network.crypto import verify_object
    from agent_network.errors import NetworkError

    if not verify_object(public_key, card, str(card.get("signature") or "")):
        raise NetworkError("INVALID_SIGNATURE", "agent card")
    if card.get("public_key") and card["public_key"] != public_key:
        raise NetworkError("IDENTITY_INVALID", "card public_key mismatch")
    if network_id and card.get("network_id") and card["network_id"] != network_id:
        raise NetworkError("IDENTITY_INVALID", "card network_id mismatch")
    if seed_agent_id and card.get("agent_id") and card["agent_id"] != seed_agent_id:
        raise NetworkError("IDENTITY_INVALID", "card agent_id mismatch")
    if key_id and card.get("key_id") and card["key_id"] != key_id:
        raise NetworkError("IDENTITY_INVALID", "card key_id mismatch")
    card_endpoint = resolve_a2a_url(card) or card.get("url")
    if endpoint and card_endpoint and str(card_endpoint).rstrip("/") != endpoint.rstrip("/"):
        raise NetworkError("IDENTITY_INVALID", "card endpoint mismatch")

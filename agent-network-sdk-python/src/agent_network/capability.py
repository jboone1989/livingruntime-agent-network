from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class CapabilityDescriptor:
    id: str
    version: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    side_effects: str = "NONE"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_value(cls, value: str | dict[str, Any]) -> CapabilityDescriptor:
        if isinstance(value, str):
            return cls(id=value, version="1.0.0")
        return cls(
            id=value["id"],
            version=str(value.get("version") or "1.0.0"),
            input_schema=dict(value.get("input_schema") or {}),
            output_schema=dict(value.get("output_schema") or {}),
            side_effects=str(value.get("side_effects") or "NONE"),
        )


def parse_version(text: str) -> tuple[int, int, int]:
    raw = text.strip().lstrip("vV")
    parts = raw.replace("x", "0").split(".")
    nums = []
    for part in parts[:3]:
        try:
            nums.append(int(part))
        except ValueError:
            nums.append(0)
    while len(nums) < 3:
        nums.append(0)
    return nums[0], nums[1], nums[2]


def version_matches(available: str, constraint: str | None) -> bool:
    if not constraint or constraint in {"*", "", "any"}:
        return True
    constraint = constraint.strip()
    if constraint.endswith(".x"):
        major = int(constraint.split(".", 1)[0])
        return parse_version(available)[0] == major
    if "," in constraint:
        return all(version_matches(available, part) for part in constraint.split(","))
    avail = parse_version(available)
    if constraint.startswith(">="):
        return avail >= parse_version(constraint[2:])
    if constraint.startswith("<="):
        return avail <= parse_version(constraint[2:])
    if constraint.startswith(">"):
        return avail > parse_version(constraint[1:])
    if constraint.startswith("<"):
        return avail < parse_version(constraint[1:])
    return avail == parse_version(constraint)


def schema_validate(schema: dict[str, Any] | None, payload: Any) -> None:
    if not schema:
        return
    expected = schema.get("type")
    if expected == "object":
        if not isinstance(payload, dict):
            raise ValueError("INVALID_REQUEST")
        for key in schema.get("required") or []:
            if key not in payload:
                raise ValueError("INVALID_REQUEST")
        props = schema.get("properties") or {}
        for key, spec in props.items():
            if key not in payload:
                continue
            want = (spec or {}).get("type")
            value = payload[key]
            if want == "string" and not isinstance(value, str):
                raise ValueError("INVALID_REQUEST")
            if want == "integer" and not isinstance(value, int):
                raise ValueError("INVALID_REQUEST")
            if want == "number" and not isinstance(value, (int, float)):
                raise ValueError("INVALID_REQUEST")
            if want == "object" and not isinstance(value, dict):
                raise ValueError("INVALID_REQUEST")
            if want == "array" and not isinstance(value, list):
                raise ValueError("INVALID_REQUEST")
        return
    if expected == "string" and not isinstance(payload, str):
        raise ValueError("INVALID_REQUEST")

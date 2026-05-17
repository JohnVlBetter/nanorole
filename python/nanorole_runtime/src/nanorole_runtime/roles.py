from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


REQUIRED_FIELDS = {
    "id",
    "name",
    "version",
    "world",
    "background",
    "persona",
    "goals",
    "opening",
}


class RoleValidationError(ValueError):
    """Raised when a role package does not match the v1 role format."""


class RoleNotFoundError(KeyError):
    """Raised when a role id cannot be resolved from the role directory."""


@dataclass(frozen=True)
class RolePackage:
    id: str
    name: str
    version: str
    world: str
    background: str
    persona: str
    goals: list[str]
    opening: str
    style: dict[str, Any] = field(default_factory=dict)
    safety_rules: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def load_role_by_id(roles_root: str | Path, role_id: str) -> RolePackage:
    root = Path(roles_root)
    if not root.exists():
        raise RoleNotFoundError(role_id)

    # Fast path for directories keyed by role id.
    candidate = root / role_id
    if candidate.is_dir():
        role = load_role_package(candidate)
        if role.id == role_id:
            return role

    # Fallback scan to support role ids that differ from directory names.
    for entry in sorted(root.iterdir(), key=lambda item: item.name):
        if not entry.is_dir():
            continue
        try:
            role = load_role_package(entry)
        except RoleValidationError:
            continue
        if role.id == role_id:
            return role

    raise RoleNotFoundError(role_id)


def load_role_package(role_dir: str | Path) -> RolePackage:
    path = Path(role_dir)
    character_path = path / "character.yaml"
    if not character_path.exists():
        raise RoleValidationError(f"role package missing {character_path}")

    data = yaml.safe_load(character_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise RoleValidationError("character.yaml must contain a YAML mapping")

    missing = sorted(REQUIRED_FIELDS - set(data))
    if missing:
        joined = ", ".join(missing)
        raise RoleValidationError(f"character.yaml missing required fields: {joined}")
    if "model" in data:
        raise RoleValidationError("model belongs in runtime config, not character.yaml")

    goals = _string_list(data["goals"], "goals")
    safety_rules = _string_list(data.get("safety_rules", []), "safety_rules")
    style = data.get("style") or {}
    metadata = data.get("metadata") or {}
    if not isinstance(style, dict):
        raise RoleValidationError("style must be a mapping when provided")
    if not isinstance(metadata, dict):
        raise RoleValidationError("metadata must be a mapping when provided")

    return RolePackage(
        id=_required_string(data, "id"),
        name=_required_string(data, "name"),
        version=_required_string(data, "version"),
        world=_required_string(data, "world"),
        background=_required_string(data, "background"),
        persona=_required_string(data, "persona"),
        goals=goals,
        opening=_required_string(data, "opening"),
        style=style,
        safety_rules=safety_rules,
        metadata=metadata,
    )


def _required_string(data: dict[str, Any], field_name: str) -> str:
    value = data[field_name]
    if not isinstance(value, str) or not value.strip():
        raise RoleValidationError(f"{field_name} must be a non-empty string")
    return value


def _string_list(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise RoleValidationError(f"{field_name} must be a list of non-empty strings")
    return value

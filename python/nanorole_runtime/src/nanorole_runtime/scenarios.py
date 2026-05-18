from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


REQUIRED_FIELDS = {
    "id",
    "name",
    "version",
    "description",
    "mode",
    "roles",
    "world",
    "initial_scene",
    "initial_state",
    "public_facts",
    "hidden_facts",
    "clues",
}

VALID_MODES = {"roleplay", "mystery"}


class ScenarioValidationError(ValueError):
    """Raised when a scenario package does not match the v1 scenario format."""


class ScenarioNotFoundError(KeyError):
    """Raised when a scenario id cannot be resolved from the scenarios directory."""


@dataclass(frozen=True)
class ScenarioSummary:
    id: str
    name: str
    version: str
    description: str
    mode: str
    role_ids: list[str]


@dataclass(frozen=True)
class ScenarioPackage:
    id: str
    name: str
    version: str
    description: str
    mode: str
    roles: list[str]
    world: str
    initial_scene: str
    initial_state: dict[str, Any]
    public_facts: list[dict[str, Any]]
    hidden_facts: list[dict[str, Any]]
    clues: list[dict[str, Any]]

    def summary(self) -> ScenarioSummary:
        return ScenarioSummary(
            id=self.id,
            name=self.name,
            version=self.version,
            description=self.description,
            mode=self.mode,
            role_ids=list(self.roles),
        )


def list_scenarios(scenarios_root: str | Path) -> list[ScenarioSummary]:
    root = Path(scenarios_root)
    if not root.exists():
        return []

    summaries: list[ScenarioSummary] = []
    for entry in sorted(root.iterdir(), key=lambda item: item.name):
        if not entry.is_dir():
            continue
        try:
            summaries.append(load_scenario_package(entry).summary())
        except ScenarioValidationError:
            continue
    return sorted(summaries, key=lambda summary: summary.id)


def load_scenario_by_id(scenarios_root: str | Path, scenario_id: str) -> ScenarioPackage:
    root = Path(scenarios_root)
    if not root.exists():
        raise ScenarioNotFoundError(scenario_id)

    candidate = root / scenario_id
    if candidate.is_dir():
        scenario = load_scenario_package(candidate)
        if scenario.id == scenario_id:
            return scenario

    for entry in sorted(root.iterdir(), key=lambda item: item.name):
        if not entry.is_dir():
            continue
        try:
            scenario = load_scenario_package(entry)
        except ScenarioValidationError:
            continue
        if scenario.id == scenario_id:
            return scenario

    raise ScenarioNotFoundError(scenario_id)


def load_scenario_package(scenario_dir: str | Path) -> ScenarioPackage:
    path = Path(scenario_dir)
    scenario_path = path / "scenario.yaml"
    if not scenario_path.exists():
        raise ScenarioValidationError(f"scenario package missing {scenario_path}")

    data = yaml.safe_load(scenario_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ScenarioValidationError("scenario.yaml must contain a YAML mapping")

    missing = sorted(REQUIRED_FIELDS - set(data))
    if missing:
        joined = ", ".join(missing)
        raise ScenarioValidationError(f"scenario.yaml missing required fields: {joined}")

    mode = _required_string(data, "mode")
    if mode not in VALID_MODES:
        raise ScenarioValidationError("mode must be one of: mystery, roleplay")

    initial_state = data["initial_state"]
    if not isinstance(initial_state, dict):
        raise ScenarioValidationError("initial_state must be a mapping")

    return ScenarioPackage(
        id=_required_string(data, "id"),
        name=_required_string(data, "name"),
        version=_required_string(data, "version"),
        description=_required_string(data, "description"),
        mode=mode,
        roles=_string_list(data["roles"], "roles"),
        world=_required_string(data, "world"),
        initial_scene=_required_string(data, "initial_scene"),
        initial_state=dict(initial_state),
        public_facts=_mapping_list(data["public_facts"], "public_facts"),
        hidden_facts=_mapping_list(data["hidden_facts"], "hidden_facts"),
        clues=_mapping_list(data["clues"], "clues"),
    )


def _required_string(data: dict[str, Any], field_name: str) -> str:
    value = data[field_name]
    if not isinstance(value, str) or not value.strip():
        raise ScenarioValidationError(f"{field_name} must be a non-empty string")
    return value


def _string_list(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ScenarioValidationError(f"{field_name} must be a list of non-empty strings")
    return list(value)


def _mapping_list(value: Any, field_name: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ScenarioValidationError(f"{field_name} must be a list of mappings")
    return [dict(item) for item in value]

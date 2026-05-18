from pathlib import Path

import pytest

from nanorole_runtime.scenarios import (
    ScenarioValidationError,
    list_scenarios,
    load_scenario_by_id,
)


def write_scenario(root: Path, scenario_id: str = "forgotten-observatory", *, omit: str | None = None) -> Path:
    data = {
        "id": scenario_id,
        "name": "Forgotten Observatory",
        "version": "1.0.0",
        "description": "A stalled observatory clock hides a missing archive.",
        "mode": "mystery",
        "roles": ["clockwork-sage", "neko-maid"],
        "world": "A brass city where public clocks regulate memory archives.",
        "initial_scene": "The observatory clock has stopped...",
        "initial_state": {"phase": "opening", "clock": "stopped"},
        "public_facts": [
            {"id": "public-1", "content": "The public clock stopped at midnight."},
        ],
        "hidden_facts": [
            {
                "id": "hidden-1",
                "content": "The clock was stopped from inside the archive room.",
                "visibility": ["clockwork-sage"],
            },
        ],
        "clues": [
            {"id": "clue-1", "content": "A bent brass key rests under the dial.", "status": "hidden"},
        ],
    }
    if omit is not None:
        data.pop(omit)
    scenario_dir = root / scenario_id
    scenario_dir.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for key, value in data.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                if isinstance(item, dict):
                    lines.append("  -")
                    for item_key, item_value in item.items():
                        if isinstance(item_value, list):
                            lines.append(f"    {item_key}:")
                            lines.extend(f"      - {entry!r}" for entry in item_value)
                        else:
                            lines.append(f"    {item_key}: {item_value!r}")
                else:
                    lines.append(f"  - {item!r}")
        elif isinstance(value, dict):
            lines.append(f"{key}:")
            lines.extend(f"  {item_key}: {item_value!r}" for item_key, item_value in value.items())
        else:
            lines.append(f"{key}: {value!r}")
    (scenario_dir / "scenario.yaml").write_text("\n".join(lines), encoding="utf-8")
    return scenario_dir


def test_load_scenario_package_from_yaml(tmp_path: Path) -> None:
    scenarios_root = tmp_path / "examples" / "scenarios"
    write_scenario(scenarios_root)

    scenario = load_scenario_by_id(scenarios_root, "forgotten-observatory")

    assert scenario.id == "forgotten-observatory"
    assert scenario.name == "Forgotten Observatory"
    assert scenario.mode == "mystery"
    assert scenario.roles == ["clockwork-sage", "neko-maid"]
    assert scenario.initial_state["phase"] == "opening"
    assert scenario.public_facts[0]["id"] == "public-1"
    assert scenario.hidden_facts[0]["visibility"] == ["clockwork-sage"]
    assert scenario.clues[0]["status"] == "hidden"


def test_list_scenarios_returns_ordered_valid_summaries(tmp_path: Path) -> None:
    scenarios_root = tmp_path / "examples" / "scenarios"
    write_scenario(scenarios_root, "zeta-case")
    write_scenario(scenarios_root, "alpha-case")
    (scenarios_root / "broken" / "scenario.yaml").parent.mkdir(parents=True)
    (scenarios_root / "broken" / "scenario.yaml").write_text("id: broken\n", encoding="utf-8")

    summaries = list_scenarios(scenarios_root)

    assert [summary.id for summary in summaries] == ["alpha-case", "zeta-case"]
    assert summaries[0].name == "Forgotten Observatory"
    assert summaries[0].role_ids == ["clockwork-sage", "neko-maid"]


def test_scenario_validation_reports_missing_required_field(tmp_path: Path) -> None:
    scenarios_root = tmp_path / "examples" / "scenarios"
    write_scenario(scenarios_root, omit="initial_scene")

    with pytest.raises(ScenarioValidationError, match="scenario.yaml missing required fields: initial_scene"):
        load_scenario_by_id(scenarios_root, "forgotten-observatory")

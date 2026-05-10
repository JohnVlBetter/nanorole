from pathlib import Path

import pytest

from nanorole_runtime.roles import RoleValidationError, load_role_package


def write_role(root: Path, **overrides: object) -> Path:
    role_dir = root / "role"
    role_dir.mkdir()
    data = {
        "id": "clockwork-sage",
        "name": "Clockwork Sage",
        "version": "1.0.0",
        "world": "A city of brass towers.",
        "background": "The sage repairs memory machines.",
        "persona": "Measured, curious, precise.",
        "goals": ["Help the user uncover forgotten causes."],
        "opening": "The gears quiet as you enter.",
    }
    data.update(overrides)
    lines = []
    for key, value in data.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            lines.extend(f"  - {item}" for item in value)
        elif isinstance(value, dict):
            lines.append(f"{key}:")
            lines.extend(f"  {item_key}: {item_value}" for item_key, item_value in value.items())
        else:
            lines.append(f"{key}: {value!r}")
    (role_dir / "character.yaml").write_text("\n".join(lines), encoding="utf-8")
    return role_dir


def test_load_role_package_reads_required_and_optional_fields(tmp_path: Path) -> None:
    role_dir = write_role(
        tmp_path,
        style={"temperature": 0.7},
        safety_rules=["Stay in character."],
        metadata={"author": "demo"},
    )

    role = load_role_package(role_dir)

    assert role.id == "clockwork-sage"
    assert role.name == "Clockwork Sage"
    assert role.style == {"temperature": 0.7}
    assert role.safety_rules == ["Stay in character."]
    assert role.metadata == {"author": "demo"}


def test_load_role_package_rejects_missing_required_field(tmp_path: Path) -> None:
    role_dir = write_role(tmp_path)
    (role_dir / "character.yaml").write_text("id: only-id\n", encoding="utf-8")

    with pytest.raises(RoleValidationError) as error:
        load_role_package(role_dir)

    assert "missing required fields" in str(error.value)
    assert "opening" in str(error.value)


def test_load_role_package_rejects_model_field_because_model_is_runtime_config(tmp_path: Path) -> None:
    role_dir = write_role(tmp_path, model="gpt-4.1-mini")

    with pytest.raises(RoleValidationError) as error:
        load_role_package(role_dir)

    assert "model belongs in runtime config" in str(error.value)

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml
from dotenv import dotenv_values


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4.1-mini"


@dataclass(frozen=True)
class ServerConfig:
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT


@dataclass(frozen=True)
class ModelConfig:
    provider: str = "openai"
    base_url: str = DEFAULT_BASE_URL
    name: str = DEFAULT_MODEL
    api_key: str | None = None
    reasoning_effort: str | None = None
    extra_body: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LoggingConfig:
    level: str = "INFO"
    trace_requests: bool = False


@dataclass(frozen=True)
class PathsConfig:
    logs_dir: Path
    sessions_dir: Path
    roles_dir: Path
    database_path: Path


@dataclass(frozen=True)
class AppConfig:
    server: ServerConfig
    model: ModelConfig
    logging: LoggingConfig
    paths: PathsConfig
    repo_root: Path


def load_config(
    *,
    repo_root: str | Path | None = None,
    config_path: str | Path | None = None,
    env_path: str | Path | None = None,
    overrides: Mapping[str, Any] | None = None,
) -> AppConfig:
    root = _find_repo_root(Path(repo_root or os.environ.get("NANOROLE_PROJECT_ROOT") or Path.cwd()).resolve())
    config_file = Path(config_path) if config_path else root / "nanorole.config.yaml"
    env_file = Path(env_path) if env_path else root / ".env"

    data: dict[str, Any] = {
        "server": {"host": DEFAULT_HOST, "port": DEFAULT_PORT},
        "model": {"provider": "openai", "base_url": DEFAULT_BASE_URL, "name": DEFAULT_MODEL},
        "logging": {"level": "INFO", "trace_requests": False},
        "paths": {
            "logs_dir": ".nanorole/logs",
            "sessions_dir": ".nanorole/sessions",
            "roles_dir": "examples/roles",
            "database_path": ".nanorole/nanorole.sqlite3",
        },
    }

    if config_file.exists():
        file_data = yaml.safe_load(config_file.read_text(encoding="utf-8")) or {}
        if not isinstance(file_data, dict):
            raise ValueError(f"{config_file} must contain a YAML mapping")
        _deep_update(data, file_data)

    env_values = {key: value for key, value in dotenv_values(env_file).items() if value is not None} if env_file.exists() else {}
    merged_env = {**env_values, **os.environ}
    provider = str(data.get("model", {}).get("provider", "openai")).lower()
    if provider == "deepseek" and merged_env.get("DEEPSEEK_API_KEY"):
        data.setdefault("model", {})["api_key"] = merged_env["DEEPSEEK_API_KEY"]
    elif merged_env.get("OPENAI_API_KEY"):
        data.setdefault("model", {})["api_key"] = merged_env["OPENAI_API_KEY"]
    elif merged_env.get("DEEPSEEK_API_KEY"):
        data.setdefault("model", {})["api_key"] = merged_env["DEEPSEEK_API_KEY"]
    if merged_env.get("OPENAI_BASE_URL"):
        data.setdefault("model", {})["base_url"] = merged_env["OPENAI_BASE_URL"]
    if merged_env.get("NANOROLE_MODEL"):
        data.setdefault("model", {})["name"] = merged_env["NANOROLE_MODEL"]
    if merged_env.get("NANOROLE_TRACE_REQUESTS"):
        data.setdefault("logging", {})["trace_requests"] = _parse_bool(merged_env["NANOROLE_TRACE_REQUESTS"])

    if overrides:
        _deep_update(data, dict(overrides))

    return AppConfig(
        server=ServerConfig(
            host=str(data["server"].get("host", DEFAULT_HOST)),
            port=int(data["server"].get("port", DEFAULT_PORT)),
        ),
        model=ModelConfig(
            provider=str(data["model"].get("provider", "openai")),
            base_url=str(data["model"].get("base_url", DEFAULT_BASE_URL)),
            name=str(data["model"].get("name", DEFAULT_MODEL)),
            api_key=data["model"].get("api_key"),
            reasoning_effort=data["model"].get("reasoning_effort"),
            extra_body=dict(data["model"].get("extra_body") or {}),
        ),
        logging=LoggingConfig(
            level=str(data["logging"].get("level", "INFO")),
            trace_requests=bool(data["logging"].get("trace_requests", False)),
        ),
        paths=PathsConfig(
            logs_dir=_resolve_path(root, data["paths"].get("logs_dir", ".nanorole/logs")),
            sessions_dir=_resolve_path(root, data["paths"].get("sessions_dir", ".nanorole/sessions")),
            roles_dir=_resolve_path(root, data["paths"].get("roles_dir", "examples/roles")),
            database_path=_resolve_path(root, data["paths"].get("database_path", ".nanorole/nanorole.sqlite3")),
        ),
        repo_root=root,
    )


def redact_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            if _is_secret_key(str(key)):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = redact_secrets(item)
        return redacted
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    return value


def _deep_update(target: dict[str, Any], source: Mapping[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(value, Mapping) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = value


def _resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def _find_repo_root(start: Path) -> Path:
    if (start / "nanorole.config.yaml").exists():
        return start
    for parent in start.parents:
        if (parent / "nanorole.config.yaml").exists():
            return parent
    return start


def _is_secret_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return normalized in {"authorization", "api_key"} or normalized.endswith("_api_key") or "secret" in normalized


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}

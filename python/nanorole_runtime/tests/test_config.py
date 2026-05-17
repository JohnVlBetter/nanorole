from pathlib import Path

from nanorole_runtime.config import load_config, redact_secrets


def test_load_config_merges_file_env_and_overrides_in_precedence_order(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "nanorole.config.yaml"
    config_path.write_text(
        """
server:
  host: 0.0.0.0
  port: 7000
model:
  provider: openai
  base_url: https://from-config.example/v1
  name: from-config
logging:
  level: DEBUG
  trace_requests: false
paths:
  logs_dir: custom/logs
  sessions_dir: custom/sessions
""",
        encoding="utf-8",
    )
    env_path = tmp_path / ".env"
    env_path.write_text(
        """
OPENAI_API_KEY=env-file-key
OPENAI_BASE_URL=https://from-env-file.example/v1
NANOROLE_MODEL=from-env-file
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("NANOROLE_MODEL", "from-process-env")

    config = load_config(
        repo_root=tmp_path,
        config_path=config_path,
        env_path=env_path,
        overrides={"server": {"port": 8123}, "logging": {"trace_requests": True}},
    )

    assert config.server.host == "0.0.0.0"
    assert config.server.port == 8123
    assert config.model.base_url == "https://from-env-file.example/v1"
    assert config.model.name == "from-process-env"
    assert config.model.api_key == "env-file-key"
    assert config.logging.trace_requests is True
    assert config.paths.logs_dir == tmp_path / "custom" / "logs"
    assert config.paths.sessions_dir == tmp_path / "custom" / "sessions"


def test_redact_secrets_masks_api_keys_and_authorization_headers() -> None:
    redacted = redact_secrets(
        {
            "api_key": "sk-test",
            "Authorization": "Bearer sk-test",
            "nested": {"OPENAI_API_KEY": "sk-nested", "DEEPSEEK_API_KEY": "sk-deepseek", "safe": "value"},
        }
    )

    assert redacted == {
        "api_key": "[REDACTED]",
        "Authorization": "[REDACTED]",
        "nested": {"OPENAI_API_KEY": "[REDACTED]", "DEEPSEEK_API_KEY": "[REDACTED]", "safe": "value"},
    }


def test_load_config_uses_project_root_environment_when_repo_root_is_omitted(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (tmp_path / "nanorole.config.yaml").write_text("server:\n  port: 9123\n", encoding="utf-8")
    monkeypatch.setenv("NANOROLE_PROJECT_ROOT", str(tmp_path))

    config = load_config()

    assert config.repo_root == tmp_path.resolve()
    assert config.server.port == 9123


def test_load_config_reads_trace_requests_from_environment(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NANOROLE_TRACE_REQUESTS", "true")

    config = load_config(repo_root=tmp_path)

    assert config.logging.trace_requests is True


def test_load_config_discovers_repo_root_from_nested_runtime_directory(tmp_path: Path, monkeypatch) -> None:
    runtime_dir = tmp_path / "python" / "nanorole_runtime"
    runtime_dir.mkdir(parents=True)
    (tmp_path / "nanorole.config.yaml").write_text(
        "\n".join(
            [
                "model:",
                "  provider: deepseek",
                "  name: deepseek-v4-pro",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text("DEEPSEEK_API_KEY=test-key\n", encoding="utf-8")
    monkeypatch.chdir(runtime_dir)
    monkeypatch.delenv("NANOROLE_PROJECT_ROOT", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    config = load_config()

    assert config.repo_root == tmp_path
    assert config.model.provider == "deepseek"
    assert config.model.api_key == "test-key"


def test_load_config_reads_deepseek_api_key_and_request_options(tmp_path: Path) -> None:
    config_path = tmp_path / "nanorole.config.yaml"
    config_path.write_text(
        """
model:
  provider: deepseek
  base_url: https://api.deepseek.com
  name: deepseek-v4-pro
  reasoning_effort: high
  extra_body:
    thinking:
      type: enabled
""",
        encoding="utf-8",
    )
    env_path = tmp_path / ".env"
    env_path.write_text("DEEPSEEK_API_KEY=deepseek-file-key\n", encoding="utf-8")

    config = load_config(repo_root=tmp_path, config_path=config_path, env_path=env_path)

    assert config.model.provider == "deepseek"
    assert config.model.base_url == "https://api.deepseek.com"
    assert config.model.name == "deepseek-v4-pro"
    assert config.model.api_key == "deepseek-file-key"
    assert config.model.reasoning_effort == "high"
    assert config.model.extra_body == {"thinking": {"type": "enabled"}}

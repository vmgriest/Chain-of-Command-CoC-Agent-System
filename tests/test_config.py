"""Config schema and loader tests.  (M1)"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError


def test_example_config_parses(config) -> None:
    """company_config.example.json must always validate. It is the onboarding
    document — if it breaks, every new company's first boot breaks."""
    assert config.company.name == "Acme Robotics"
    assert config.personas.front_desk.name == "Penny"


def test_missing_required_section_fails(example_config_dict: dict) -> None:
    from backend.config.schema import CompanyConfig

    raw = dict(example_config_dict)
    raw.pop("_comment", None)
    del raw["personas"]
    with pytest.raises(ValidationError, match="personas"):
        CompanyConfig.model_validate(raw)


def test_unknown_key_is_rejected(example_config_dict: dict) -> None:
    from backend.config.schema import CompanyConfig

    raw = dict(example_config_dict)
    raw.pop("_comment", None)
    raw["persona"] = raw.pop("personas")  # typo
    with pytest.raises(ValidationError):
        CompanyConfig.model_validate(raw)


def test_comment_key_is_stripped(tmp_path, example_config_dict: dict) -> None:
    from backend.config.loader import load_config

    config_path = tmp_path / "company_config.json"
    config_path.write_text(json.dumps(example_config_dict), encoding="utf-8")
    loaded = load_config(config_path)
    assert loaded.company.name == "Acme Robotics"


def test_stdio_requires_command(example_config_dict: dict) -> None:
    from backend.config.schema import CompanyConfig

    raw = dict(example_config_dict)
    raw.pop("_comment", None)
    raw["mcp_servers"]["internal"][0].pop("command")
    with pytest.raises(ValidationError):
        CompanyConfig.model_validate(raw)


def test_http_requires_url(example_config_dict: dict) -> None:
    from backend.config.schema import CompanyConfig

    raw = dict(example_config_dict)
    raw.pop("_comment", None)
    del raw["mcp_servers"]["external"][1]["url"]
    with pytest.raises(ValidationError):
        CompanyConfig.model_validate(raw)


def test_unknown_tier_in_tiers_array_fails(example_config_dict: dict) -> None:
    from backend.config.schema import CompanyConfig

    raw = dict(example_config_dict)
    raw.pop("_comment", None)
    raw["mcp_servers"]["internal"][0]["tiers"] = ["director"]
    with pytest.raises(ValidationError):
        CompanyConfig.model_validate(raw)


def test_disallowed_stdio_binary_rejected(example_config_dict: dict) -> None:
    """The check that makes `"command": "bash"` fail at startup."""
    from backend.config.schema import CompanyConfig

    raw = dict(example_config_dict)
    raw.pop("_comment", None)
    raw["mcp_servers"]["internal"][0]["command"] = "bash"
    with pytest.raises(ValidationError, match="not allowlisted"):
        CompanyConfig.model_validate(raw)


def test_front_desk_cannot_receive_mcp_tools(example_config_dict: dict) -> None:
    from backend.config.schema import CompanyConfig

    raw = dict(example_config_dict)
    raw.pop("_comment", None)
    raw["mcp_servers"]["internal"][0]["tiers"].append("front_desk")
    with pytest.raises(ValidationError, match="front_desk"):
        CompanyConfig.model_validate(raw)


def test_missing_config_file_error_is_actionable(tmp_path) -> None:
    from backend.config.loader import ConfigError, load_config

    missing = tmp_path / "does_not_exist.json"
    with pytest.raises(ConfigError, match="company_config.example.json"):
        load_config(missing)


def test_human_admin_requires_a_channel(example_config_dict: dict) -> None:
    from backend.config.schema import CompanyConfig

    raw = dict(example_config_dict)
    raw.pop("_comment", None)
    raw["escalation"]["human_admin"] = {"email": None, "push_topic": None, "scheduling_link": None}
    with pytest.raises(ValidationError):
        CompanyConfig.model_validate(raw)


def test_config_is_cached(tmp_path, example_config_dict: dict, monkeypatch) -> None:
    from backend.config import loader as loader_module

    config_path = tmp_path / "company_config.json"
    config_path.write_text(json.dumps(example_config_dict), encoding="utf-8")
    monkeypatch.setenv("COMPANY_CONFIG_PATH", str(config_path))
    loader_module.get_config.cache_clear()

    first = loader_module.get_config()
    second = loader_module.get_config()
    assert first is second

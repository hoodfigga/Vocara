"""Tests for config loading, validation, and atomic writes."""

import importlib
import json
import os
import sys

import pytest


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    """Loads a fresh config module pointed at a temporary directory."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))
    import config as config_module

    module = importlib.reload(config_module)
    module.CONFIG_DIR = str(tmp_path / "vocara")
    module.CONFIG_FILE = os.path.join(module.CONFIG_DIR, "config.json")
    module.DICT_FILE = os.path.join(module.CONFIG_DIR, "dictionary.json")
    return module


def test_load_config_creates_defaults(cfg):
    loaded = cfg.load_config()
    assert loaded == cfg.DEFAULT_CONFIG
    assert os.path.exists(cfg.CONFIG_FILE)


def test_load_config_survives_corrupt_json(cfg):
    os.makedirs(cfg.CONFIG_DIR, exist_ok=True)
    with open(cfg.CONFIG_FILE, "w") as f:
        f.write("{not json at all")
    assert cfg.load_config() == cfg.DEFAULT_CONFIG


def test_validate_rejects_bad_enum_and_types(cfg):
    result = cfg.validate_config(
        {
            "activation_mode": "telepathy",  # invalid -> default
            "model_size": "large-v3",  # valid   -> kept
            "play_beeps": "yes",  # wrong type -> default
            "shortcut": "ctrl+a",  # wrong type -> default
            "vad_energy_threshold": -5,  # out of range -> default
            "hud_position": [10, 20],  # valid   -> kept
            "totally_unknown_key": 1,  # dropped
        }
    )
    assert result["activation_mode"] == "hold"
    assert result["model_size"] == "large-v3"
    assert result["play_beeps"] is True
    assert result["shortcut"] == ["mouse.Button.x2"]
    assert result["vad_energy_threshold"] == 0.015
    assert result["hud_position"] == [10, 20]
    assert "totally_unknown_key" not in result


def test_validate_accepts_non_dict(cfg):
    assert cfg.validate_config(["not", "a", "dict"]) == cfg.DEFAULT_CONFIG
    assert cfg.validate_config(None) == cfg.DEFAULT_CONFIG


def test_save_config_roundtrip_is_atomic(cfg):
    data = cfg.DEFAULT_CONFIG.copy()
    data["model_size"] = "turbo"
    cfg.save_config(data)

    # No temp files left behind
    leftovers = [f for f in os.listdir(cfg.CONFIG_DIR) if f.endswith(".tmp")]
    assert leftovers == []

    with open(cfg.CONFIG_FILE) as f:
        assert json.load(f)["model_size"] == "turbo"
    assert cfg.load_config()["model_size"] == "turbo"


def test_dictionary_roundtrip_and_bad_payload(cfg):
    assert "Vocara" in cfg.load_dictionary()  # seeds defaults

    cfg.save_dictionary(["Kubernetes", "gRPC"])
    assert cfg.load_dictionary() == ["Kubernetes", "gRPC"]

    with open(cfg.DICT_FILE, "w") as f:
        json.dump({"not": "a list"}, f)
    assert cfg.load_dictionary() == []


def test_launch_command_handles_frozen(cfg, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert cfg._launch_command() == [sys.executable]

    monkeypatch.delattr(sys, "frozen", raising=False)
    cmd = cfg._launch_command()
    assert len(cmd) == 2 and cmd[1].endswith("main.py")

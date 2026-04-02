"""Tests for LLM config file loader."""

import textwrap
from pathlib import Path

from devforge.llm.config_loader import load_llm_config, _parse_yaml_simple


def test_load_from_file(tmp_path: Path):
    config_file = tmp_path / "llm.yaml"
    config_file.write_text(textwrap.dedent("""\
        allow_live: true
        provider: google
        model: gemini-2.5-flash
        tasks:
          product_design:
            model: gemini-2.5-pro
          acceptance_evaluation:
            model: gemini-2.5-pro
            provider: google
          retry_decision:
            model: gemini-2.5-flash
    """))
    prefs = load_llm_config(config_path=config_file)
    assert prefs["allow_live"] is True
    assert prefs["provider"] == "google"
    assert prefs["model"] == "gemini-2.5-flash"
    assert prefs["product_design_model"] == "gemini-2.5-pro"
    assert prefs["acceptance_evaluation_model"] == "gemini-2.5-pro"
    assert prefs["acceptance_evaluation_provider"] == "google"
    assert prefs["retry_decision_model"] == "gemini-2.5-flash"


def test_load_missing_file_returns_empty():
    prefs = load_llm_config(config_path="/nonexistent/llm.yaml")
    assert prefs == {}


def test_load_auto_discover(tmp_path: Path):
    config_file = tmp_path / "llm.yaml"
    config_file.write_text("provider: google\nmodel: gemini-2.5-flash\n")
    prefs = load_llm_config(search_dir=tmp_path)
    assert prefs["provider"] == "google"


def test_parse_yaml_simple():
    text = textwrap.dedent("""\
        allow_live: true
        provider: openrouter
        model: claude-sonnet-4
        tasks:
          concept_collection:
            model: gemini-2.5-flash
            provider: google
    """)
    result = _parse_yaml_simple(text)
    assert result["allow_live"] is True
    assert result["provider"] == "openrouter"
    assert result["tasks"]["concept_collection"]["model"] == "gemini-2.5-flash"
    assert result["tasks"]["concept_collection"]["provider"] == "google"


def test_mixed_providers(tmp_path: Path):
    config_file = tmp_path / "llm.yaml"
    config_file.write_text(textwrap.dedent("""\
        allow_live: true
        provider: google
        model: gemini-2.5-flash
        tasks:
          product_design:
            provider: openrouter
            model: anthropic/claude-sonnet-4
    """))
    prefs = load_llm_config(config_path=config_file)
    assert prefs["provider"] == "google"
    assert prefs["product_design_provider"] == "openrouter"
    assert prefs["product_design_model"] == "anthropic/claude-sonnet-4"

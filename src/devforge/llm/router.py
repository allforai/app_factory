"""Project-aware LLM routing helpers."""

from __future__ import annotations

import os
from typing import Any

from .base import LLMClient
from .factory import build_llm_client
from .mock import MockLLMClient


def build_task_llm_client(
    *,
    task: str,
    preferences: dict[str, Any] | None = None,
) -> LLMClient:
    """Build a task-specific LLM client from project preferences.

    Offline-safe by default: unless live routing is explicitly enabled and an API key
    is available, this returns a mock client carrying the routed provider/model identity.
    """

    preferences = preferences or {}
    provider = _provider_for_task(task, preferences)
    model = _model_for_task(task, preferences) or "mock-structured-v1"
    allow_live = bool(preferences.get("allow_live", False))
    api_key = _api_key_for_provider(provider, preferences)

    if allow_live and provider != "mock" and api_key:
        return build_llm_client(provider, model=model, api_key=api_key)
    return MockLLMClient(provider_name=provider, model_name=model)


def _model_for_task(task: str, preferences: dict[str, Any]) -> str | None:
    # Check task-specific key: e.g. "product_design_model" or legacy "concept_model"
    task_model_key = f"{task}_model"
    if preferences.get(task_model_key):
        return str(preferences[task_model_key])
    legacy_keys = {
        "concept_collection": "concept_model",
        "planning_and_shaping": "planning_model",
        "retry_decision": "retry_model",
    }
    legacy_key = legacy_keys.get(task)
    if legacy_key and preferences.get(legacy_key):
        return str(preferences[legacy_key])
    if preferences.get("model"):
        return str(preferences["model"])
    return None


def _provider_for_task(task: str, preferences: dict[str, Any]) -> str:
    task_provider_key = f"{task}_provider"
    if preferences.get(task_provider_key):
        return str(preferences[task_provider_key])
    legacy_keys = {
        "concept_collection": "concept_provider",
        "planning_and_shaping": "planning_provider",
        "retry_decision": "retry_provider",
    }
    legacy_key = legacy_keys.get(task)
    if legacy_key and preferences.get(legacy_key):
        return str(preferences[legacy_key])
    return str(preferences.get("provider", "mock"))


def _api_key_for_provider(provider: str, preferences: dict[str, Any]) -> str | None:
    if preferences.get("api_key"):
        return str(preferences["api_key"])
    env_var = {
        "openrouter": "OPENROUTER_API_KEY",
        "google": "GOOGLE_API_KEY",
    }.get(provider)
    if env_var is None:
        return None
    return os.getenv(env_var)

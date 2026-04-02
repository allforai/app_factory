"""Provider configuration models for live LLM clients."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True)
class LLMProviderConfig:
    """One provider configuration."""

    provider: str
    model: str
    api_key: str | None = None
    base_url: str | None = None


def openrouter_config(model: str, *, api_key: str | None = None) -> LLMProviderConfig:
    return LLMProviderConfig(
        provider="openrouter",
        model=model,
        api_key=api_key or os.getenv("OPENROUTER_API_KEY"),
        base_url="https://openrouter.ai/api/v1",
    )


def google_config(model: str, *, api_key: str | None = None) -> LLMProviderConfig:
    return LLMProviderConfig(
        provider="google",
        model=model,
        api_key=api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"),
        base_url="https://generativelanguage.googleapis.com/v1beta",
    )

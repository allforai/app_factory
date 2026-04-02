"""LLM client factory helpers."""

from __future__ import annotations

from devforge.llm.base import LLMClient

from .config import LLMProviderConfig
from .google import GoogleGenAIClient
from .http import HTTPTransport
from .httpx_transport import HttpxTransport
from .mock import MockLLMClient
from .openrouter import OpenRouterClient


def _default_live_transport() -> HttpxTransport:
    return HttpxTransport(timeout_seconds=60.0)


def build_llm_client(
    provider: str,
    *,
    model: str,
    api_key: str | None = None,
    transport: HTTPTransport | None = None,
) -> LLMClient:
    """Build one provider-specific LLM client.

    When no transport is provided and the provider is not mock,
    uses HttpxTransport for real HTTP calls.
    """

    if provider == "mock":
        return MockLLMClient(model_name=model)
    live_transport = transport or _default_live_transport()
    if provider == "google":
        return GoogleGenAIClient(model_name=model, api_key=api_key, transport=live_transport)
    if provider == "openrouter":
        return OpenRouterClient(model_name=model, api_key=api_key, transport=live_transport)
    raise ValueError(f"Unsupported llm provider: {provider}")


def build_llm_client_from_config(
    config: LLMProviderConfig,
    *,
    transport: HTTPTransport | None = None,
) -> LLMClient:
    """Build one provider-specific client from config."""

    return build_llm_client(
        config.provider,
        model=config.model,
        api_key=config.api_key,
        transport=transport,
    )

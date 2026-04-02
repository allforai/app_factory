"""Provider-agnostic LLM client interfaces."""

from __future__ import annotations

from typing import Protocol

from .models import StructuredGenerationRequest, StructuredGenerationResponse


class LLMClient(Protocol):
    """Minimal structured-output LLM client."""

    provider_name: str
    model_name: str

    def generate_structured(self, request: StructuredGenerationRequest) -> StructuredGenerationResponse:
        """Generate a structured response for a given request."""

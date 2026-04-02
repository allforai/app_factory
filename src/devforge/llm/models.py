"""Provider-agnostic LLM request/response models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class StructuredGenerationRequest:
    """One structured generation request."""

    task: str
    schema_name: str
    instructions: str
    input_payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class StructuredGenerationResponse:
    """Normalized structured response from an LLM provider."""

    output: dict[str, Any]
    provider: str
    model: str
    raw_text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

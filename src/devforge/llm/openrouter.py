"""OpenRouter-backed structured LLM client."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

from .http import HTTPTransport, StubHTTPTransport, TransportRequest
from .models import StructuredGenerationRequest, StructuredGenerationResponse


@dataclass(slots=True)
class OpenRouterClient:
    """Provider adapter for OpenRouter chat-completions style structured generation."""

    model_name: str
    api_key: str | None = None
    app_name: str = "devforge"
    site_url: str | None = None
    base_url: str = "https://openrouter.ai/api/v1"
    provider_name: str = "openrouter"
    transport: HTTPTransport = field(default_factory=lambda: StubHTTPTransport(response_json={}))
    extra_headers: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.api_key is None:
            self.api_key = os.getenv("OPENROUTER_API_KEY")

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}" if self.api_key else "",
            "Content-Type": "application/json",
            "HTTP-Referer": self.site_url or "",
            "X-Title": self.app_name,
        }
        headers.update(self.extra_headers)
        return headers

    def _payload(self, request: StructuredGenerationRequest) -> dict[str, Any]:
        return {
            "model": self.model_name,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Return only valid JSON for the requested schema. "
                        f"Schema: {request.schema_name}. "
                        f"Task: {request.task}."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "instructions": request.instructions,
                            "input_payload": request.input_payload,
                            "metadata": request.metadata,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            "response_format": {"type": "json_object"},
        }

    def generate_structured(self, request: StructuredGenerationRequest) -> StructuredGenerationResponse:
        payload = self._payload(request)
        response = self.transport.send(
            TransportRequest(
                method="POST",
                url=f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json_body=payload,
            )
        )
        response_payload = response.json_body
        raw_text = (
            response_payload.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "{}")
        )
        output = json.loads(raw_text)
        return StructuredGenerationResponse(
            output=output,
            provider=self.provider_name,
            model=self.model_name,
            raw_text=raw_text,
            metadata={"request_task": request.task, "transport": "openrouter"},
        )

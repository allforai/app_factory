"""Google Gemini-backed structured LLM client."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

from .http import HTTPTransport, StubHTTPTransport, TransportRequest
from .models import StructuredGenerationRequest, StructuredGenerationResponse


@dataclass(slots=True)
class GoogleGenAIClient:
    """Provider adapter for Gemini generateContent style structured generation."""

    model_name: str
    api_key: str | None = None
    provider_name: str = "google"
    base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    transport: HTTPTransport = field(default_factory=lambda: StubHTTPTransport(response_json={}))

    def __post_init__(self) -> None:
        if self.api_key is None:
            self.api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")

    def _headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json"}

    def _payload(self, request: StructuredGenerationRequest) -> dict[str, Any]:
        return {
            "systemInstruction": {
                "parts": [
                    {
                        "text": (
                            "Return only valid JSON for the requested schema. "
                            f"Schema: {request.schema_name}. Task: {request.task}."
                        )
                    }
                ]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": json.dumps(
                                {
                                    "instructions": request.instructions,
                                    "input_payload": request.input_payload,
                                    "metadata": request.metadata,
                                },
                                ensure_ascii=False,
                            )
                        }
                    ],
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
            },
        }

    def generate_structured(self, request: StructuredGenerationRequest) -> StructuredGenerationResponse:
        payload = self._payload(request)
        headers = self._headers()
        if self.api_key:
            headers["x-goog-api-key"] = self.api_key
        response = self.transport.send(
            TransportRequest(
                method="POST",
                url=f"{self.base_url}/models/{self.model_name}:generateContent",
                headers=headers,
                json_body=payload,
            )
        )
        response_payload = response.json_body
        raw_text = (
            response_payload.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "{}")
        )
        output = json.loads(raw_text)
        return StructuredGenerationResponse(
            output=output,
            provider=self.provider_name,
            model=self.model_name,
            raw_text=raw_text,
            metadata={"request_task": request.task, "transport": "google"},
        )

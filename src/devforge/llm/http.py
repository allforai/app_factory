"""Shared HTTP transport abstractions for provider clients."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True)
class TransportRequest:
    """Normalized outbound HTTP request."""

    method: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    json_body: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TransportResponse:
    """Normalized inbound HTTP response."""

    status_code: int
    json_body: dict[str, Any] = field(default_factory=dict)
    text: str = ""
    headers: dict[str, str] = field(default_factory=dict)


class HTTPTransport(Protocol):
    """Shared HTTP transport interface for provider adapters."""

    def send(self, request: TransportRequest) -> TransportResponse:
        """Send one HTTP request and return a normalized response."""


@dataclass(slots=True)
class StubHTTPTransport:
    """Local stub transport with injectable response payloads for tests."""

    response_json: dict[str, Any]
    status_code: int = 200

    def send(self, request: TransportRequest) -> TransportResponse:
        return TransportResponse(
            status_code=self.status_code,
            json_body=self.response_json,
            text=str(self.response_json),
            headers={},
        )

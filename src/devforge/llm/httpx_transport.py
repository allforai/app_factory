"""httpx-backed HTTP transport."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .http import HTTPTransport, TransportRequest, TransportResponse


ClientFactory = Callable[[], Any]


@dataclass(slots=True)
class HttpxTransport(HTTPTransport):
    """Shared HTTP transport backed by httpx with lazy import."""

    timeout_seconds: float = 30.0
    client_factory: ClientFactory | None = None

    def _make_client(self) -> Any:
        if self.client_factory is not None:
            return self.client_factory()
        try:
            import httpx  # type: ignore
        except ImportError as exc:
            raise RuntimeError("httpx is required for live HTTP transport") from exc
        return httpx.Client(timeout=self.timeout_seconds)

    def send(self, request: TransportRequest) -> TransportResponse:
        client = self._make_client()
        try:
            response = client.request(
                method=request.method,
                url=request.url,
                headers=request.headers,
                json=request.json_body,
            )
            try:
                json_body = response.json()
            except Exception:
                json_body = {}
            return TransportResponse(
                status_code=response.status_code,
                json_body=json_body,
                text=getattr(response, "text", ""),
                headers=dict(getattr(response, "headers", {})),
            )
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()

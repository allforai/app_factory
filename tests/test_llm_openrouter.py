from devforge.llm import OpenRouterClient, StructuredGenerationRequest, build_llm_client
from devforge.llm.http import HTTPTransport, StubHTTPTransport, TransportRequest, TransportResponse


def test_openrouter_client_builds_chat_completion_payload() -> None:
    client = OpenRouterClient(model_name="openai/gpt-5-mini", api_key="test-key")
    request = StructuredGenerationRequest(
        task="retry_decision",
        schema_name="RetryDecision",
        instructions="Return JSON only",
        input_payload={"hello": "world"},
        metadata={"k": "v"},
    )

    payload = client._payload(request)

    assert payload["model"] == "openai/gpt-5-mini"
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["messages"][0]["role"] == "system"
    assert "\"hello\": \"world\"" in payload["messages"][1]["content"]


def test_openrouter_client_generates_structured_output_via_injected_transport() -> None:
    class CaptureTransport:
        def send(self, request: TransportRequest) -> TransportResponse:
            assert request.json_body["model"] == "openai/gpt-5-mini"
            assert request.headers["Authorization"] == "Bearer test-key"
            return TransportResponse(
                status_code=200,
                json_body={
                    "choices": [
                        {
                            "message": {
                                "content": "{\"action\":\"replan\",\"reason\":\"context_changed\",\"confidence\":0.9,\"notes\":[\"ok\"]}"
                            }
                        }
                    ]
                },
            )

    client = OpenRouterClient(
        model_name="openai/gpt-5-mini",
        api_key="test-key",
        site_url="https://example.com",
        transport=CaptureTransport(),
    )
    response = client.generate_structured(
        StructuredGenerationRequest(
            task="retry_decision",
            schema_name="RetryDecision",
            instructions="Return JSON only",
            input_payload={"foo": "bar"},
        )
    )

    assert response.provider == "openrouter"
    assert response.model == "openai/gpt-5-mini"
    assert response.output["action"] == "replan"
    assert response.metadata["transport"] == "openrouter"


def test_build_llm_client_returns_openrouter_client() -> None:
    client = build_llm_client("openrouter", model="openai/gpt-5-mini", api_key="test-key")

    assert isinstance(client, OpenRouterClient)


def test_stub_http_transport_returns_response_shape() -> None:
    transport = StubHTTPTransport(response_json={"ok": True})
    response = transport.send(TransportRequest(method="POST", url="https://example.com"))

    assert response.status_code == 200
    assert response.json_body == {"ok": True}

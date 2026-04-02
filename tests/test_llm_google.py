from devforge.llm import GoogleGenAIClient, StructuredGenerationRequest, build_llm_client
from devforge.llm.http import TransportRequest, TransportResponse


def test_google_client_builds_generate_content_payload() -> None:
    client = GoogleGenAIClient(model_name="gemini-2.5-pro", api_key="test-key")
    request = StructuredGenerationRequest(
        task="retry_decision",
        schema_name="RetryDecision",
        instructions="Return JSON only",
        input_payload={"hello": "world"},
        metadata={"k": "v"},
    )

    payload = client._payload(request)

    assert payload["generationConfig"]["responseMimeType"] == "application/json"
    assert payload["contents"][0]["role"] == "user"
    assert "\"hello\": \"world\"" in payload["contents"][0]["parts"][0]["text"]


def test_google_client_generates_structured_output_via_injected_transport() -> None:
    class CaptureTransport:
        def send(self, request: TransportRequest) -> TransportResponse:
            assert request.headers["x-goog-api-key"] == "test-key"
            assert request.json_body["generationConfig"]["responseMimeType"] == "application/json"
            return TransportResponse(
                status_code=200,
                json_body={
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "text": "{\"action\":\"block\",\"reason\":\"seam_not_stable\",\"confidence\":0.8,\"notes\":[\"ok\"]}"
                                    }
                                ]
                            }
                        }
                    ]
                },
            )

    client = GoogleGenAIClient(
        model_name="gemini-2.5-pro",
        api_key="test-key",
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

    assert response.provider == "google"
    assert response.model == "gemini-2.5-pro"
    assert response.output["action"] == "block"
    assert response.metadata["transport"] == "google"


def test_build_llm_client_returns_google_client() -> None:
    client = build_llm_client("google", model="gemini-2.5-pro", api_key="test-key")

    assert isinstance(client, GoogleGenAIClient)

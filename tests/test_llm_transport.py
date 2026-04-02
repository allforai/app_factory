from devforge.llm import HttpxTransport, TransportRequest, build_llm_client_from_config, google_config, openrouter_config


def test_httpx_transport_uses_client_factory() -> None:
    class FakeResponse:
        status_code = 200
        text = '{"ok": true}'
        headers = {"x-test": "1"}

        def json(self):
            return {"ok": True}

    class FakeClient:
        def request(self, *, method, url, headers, json):
            assert method == "POST"
            assert url == "https://example.com"
            assert headers["Authorization"] == "Bearer test"
            assert json == {"hello": "world"}
            return FakeResponse()

        def close(self):
            return None

    transport = HttpxTransport(client_factory=lambda: FakeClient())
    response = transport.send(
        TransportRequest(
            method="POST",
            url="https://example.com",
            headers={"Authorization": "Bearer test"},
            json_body={"hello": "world"},
        )
    )

    assert response.status_code == 200
    assert response.json_body == {"ok": True}
    assert response.headers == {"x-test": "1"}


def test_provider_config_helpers_and_factory_work_together() -> None:
    config = openrouter_config("openai/gpt-5-mini", api_key="test-key")
    client = build_llm_client_from_config(config)

    assert client.provider_name == "openrouter"
    assert client.model_name == "openai/gpt-5-mini"

    google = google_config("gemini-2.5-pro", api_key="google-key")
    google_client = build_llm_client_from_config(google)

    assert google_client.provider_name == "google"
    assert google_client.model_name == "gemini-2.5-pro"

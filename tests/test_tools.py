"""Tests for tools module — unit tests (no real API calls)."""

from app_factory.tools.brave_search import BraveSearchClient, SearchResult
from app_factory.tools.fal_image import FalImageClient, FalImageResult
from app_factory.tools.image_gen import ImageGenClient, ImageResult
from app_factory.tools.xv_validator import XVValidator, XVResult, _DEFAULT_XV_ROUTES


def test_brave_search_no_key_returns_empty():
    client = BraveSearchClient(api_key=None)
    client.api_key = None  # force no key
    results = client.search("test query")
    assert results == []


def test_brave_search_result_model():
    result = SearchResult(title="Test", url="https://example.com", snippet="test snippet")
    assert result.title == "Test"
    assert result.url == "https://example.com"


def test_xv_validator_no_keys_returns_empty():
    validator = XVValidator(api_keys={})
    # With no env keys set and empty api_keys, should gracefully return empty
    result = validator.validate("test-artifact", "some content", domains=["architecture_review"])
    assert isinstance(result, XVResult)
    assert result.artifact_ref == "test-artifact"


def test_xv_default_routes_have_latest_models():
    assert "gpt-5.4" in _DEFAULT_XV_ROUTES["architecture_review"][1]
    assert "deepseek" in _DEFAULT_XV_ROUTES["data_model_review"][1]
    assert "gemini" in _DEFAULT_XV_ROUTES["ui_review"][1]
    assert "claude" in _DEFAULT_XV_ROUTES["code_review"][1]


def test_image_gen_no_key_returns_error():
    client = ImageGenClient(api_key=None)
    client.api_key = None
    result = client.generate("a cute cat")
    assert isinstance(result, ImageResult)
    assert not result.success
    assert "no API key" in result.error


def test_image_result_model():
    result = ImageResult(prompt="test", image_data=b"fake", mime_type="image/png", model="gemini")
    assert result.success is True
    assert result.mime_type == "image/png"


def test_fal_no_key_returns_error():
    client = FalImageClient(api_key=None)
    client.api_key = None
    result = client.generate("a UI mockup")
    assert isinstance(result, FalImageResult)
    assert not result.success
    assert "no FAL_KEY" in result.error


def test_fal_result_model():
    result = FalImageResult(prompt="test", image_url="https://fal.ai/img/123.png", model="flux")
    assert result.success is True
    assert result.image_url.startswith("https://")

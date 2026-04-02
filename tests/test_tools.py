"""Tests for tools module — unit tests (no real API calls)."""

from devforge.tools.brave_search import BraveSearchClient, SearchResult
from devforge.tools.fal_image import FalImageClient, FalImageResult
from devforge.tools.image_gen import ImageGenClient, ImageResult
from devforge.tools.stitch_ui import StitchClient, StitchProject, StitchScreen
from devforge.tools.xv_validator import XVValidator, XVResult, _DEFAULT_XV_ROUTES


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


def test_stitch_not_available_without_credentials():
    client = StitchClient(config_dir="/nonexistent/path")
    assert client.is_available() is False


def test_stitch_create_project():
    client = StitchClient()
    project = client.create_project("Test App")
    assert project.title == "Test App"
    # Without credentials, project_id is empty
    if not client.is_available():
        assert project.project_id == ""


def test_stitch_build_prompts_from_design():
    client = StitchClient()
    design = {
        "product_name": "二手交易平台",
        "user_flows": [
            {"role": "buyer", "steps": ["首页", "搜索", "商品详情", "购物车", "结算"]},
            {"role": "admin", "steps": ["管理首页", "订单审核"]},
        ],
        "interaction_matrix": [
            {"role": "buyer", "principle": "极致效率、零学习成本"},
            {"role": "admin", "principle": "信息密度高、批量操作"},
        ],
    }
    prompts = client.build_prompts_from_design(design, max_screens=8)
    assert len(prompts) == 7  # 5 buyer + 2 admin
    assert prompts[0]["screen_name"] == "首页"
    assert "buyer" in prompts[0]["prompt"]
    assert "极致效率" in prompts[0]["prompt"]
    # Admin screens should have admin principle
    admin_prompt = next(p for p in prompts if p["screen_name"] == "管理首页")
    assert "信息密度" in admin_prompt["prompt"]


def test_stitch_anchor_screen_workflow():
    client = StitchClient()
    project = StitchProject(project_id="test-proj", title="Test")
    anchor = client.generate_anchor_screen(project, "Design a homepage", screen_id="S001")
    assert anchor.screen_id == "S001"
    assert project.anchor_screen_id == "S001"
    assert len(project.screens) == 1

    # Subsequent screen
    screen2 = client.generate_screen(project, "Design a search page", screen_id="S002", screen_name="search")
    assert screen2.screen_id == "S002"
    assert len(project.screens) == 2

    # Consistency check
    result = client.check_consistency(project)
    assert result["passed"] is True
    assert result["screens_checked"] == 2

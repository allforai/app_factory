"""Live tool tests — requires API keys in .env.

Run: uv run python -m pytest tests/test_tools_live.py -v -s
"""

from __future__ import annotations

import os

import pytest

skip_no_brave = pytest.mark.skipif(not os.getenv("BRAVE_API_KEY"), reason="BRAVE_API_KEY not set")
skip_no_openrouter = pytest.mark.skipif(not os.getenv("OPENROUTER_API_KEY"), reason="OPENROUTER_API_KEY not set")
skip_no_gemini = pytest.mark.skipif(
    not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")), reason="GEMINI_API_KEY not set"
)


@skip_no_brave
def test_live_brave_search():
    from devforge.tools.brave_search import BraveSearchClient

    client = BraveSearchClient()
    results = client.search("二手交易平台 竞品分析", count=5)
    print(f"\n=== Brave Search: {len(results)} results ===")
    for r in results[:3]:
        print(f"  {r.title}: {r.url}")
    assert len(results) > 0


@skip_no_brave
def test_live_brave_research_topic():
    from devforge.tools.brave_search import BraveSearchClient

    client = BraveSearchClient()
    results = client.research_topic("roguelike game design", count_per_query=3)
    print(f"\n=== Research: {len(results)} results ===")
    assert len(results) > 0


@skip_no_openrouter
def test_live_xv_single_domain():
    from devforge.tools.xv_validator import XVValidator

    validator = XVValidator()
    result = validator.validate(
        artifact_ref="test-api-design",
        artifact_content="""
        POST /api/orders
        Body: { user_id: string, items: [{product_id, quantity}], total: number }
        Response: { order_id: string, status: "created" }
        No authentication required.
        """,
        domains=["architecture_review"],
    )
    print(f"\n=== XV Result: {len(result.findings)} findings, consensus={result.consensus} ===")
    for f in result.findings:
        print(f"  [{f.severity}] {f.description}")
    assert len(result.models_used) > 0

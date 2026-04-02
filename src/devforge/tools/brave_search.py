"""Brave Search API integration for market research and trend analysis."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SearchResult:
    """One search result."""

    title: str
    url: str
    snippet: str
    source_level: str = ""  # P1-P4 per product-design-theory


@dataclass(slots=True)
class BraveSearchClient:
    """Brave Search API client for concept research and competitive analysis."""

    api_key: str | None = None
    base_url: str = "https://api.search.brave.com/res/v1"

    def __post_init__(self) -> None:
        if self.api_key is None:
            self.api_key = os.getenv("BRAVE_API_KEY")

    def search(
        self,
        query: str,
        *,
        count: int = 10,
        freshness: str | None = None,
    ) -> list[SearchResult]:
        """Execute a web search and return structured results.

        Args:
            query: Search query string
            count: Max results (default 10)
            freshness: Recency filter — "pd" (past day), "pw" (past week),
                       "pm" (past month), "py" (past year), or None
        """
        if not self.api_key:
            return []

        try:
            import httpx
        except ImportError:
            return []

        params: dict[str, Any] = {"q": query, "count": count}
        if freshness:
            params["freshness"] = freshness

        response = httpx.get(
            f"{self.base_url}/web/search",
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": self.api_key,
            },
            params=params,
            timeout=15.0,
        )

        if response.status_code != 200:
            return []

        data = response.json()
        results: list[SearchResult] = []
        for item in data.get("web", {}).get("results", []):
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("description", ""),
            ))
        return results

    def research_topic(
        self,
        topic: str,
        *,
        queries: list[str] | None = None,
        count_per_query: int = 5,
    ) -> list[SearchResult]:
        """Multi-query research on a topic. Returns deduplicated results."""
        all_queries = queries or [
            topic,
            f"{topic} best practices 2025 2026",
            f"{topic} competitive landscape",
        ]
        seen_urls: set[str] = set()
        all_results: list[SearchResult] = []
        for q in all_queries:
            for result in self.search(q, count=count_per_query, freshness="py"):
                if result.url not in seen_urls:
                    seen_urls.add(result.url)
                    all_results.append(result)
        return all_results

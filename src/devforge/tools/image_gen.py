"""Image generation via Google Gemini for UI mockups and diagrams."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ImageResult:
    """Result of image generation."""

    prompt: str
    image_data: bytes = b""
    mime_type: str = "image/png"
    model: str = ""
    error: str = ""

    @property
    def success(self) -> bool:
        return len(self.image_data) > 0 and not self.error


@dataclass(slots=True)
class ImageGenClient:
    """Image generation client using Gemini's image generation capability."""

    api_key: str | None = None
    model: str = "gemini-2.5-flash-image"
    base_url: str = "https://generativelanguage.googleapis.com/v1beta"

    def __post_init__(self) -> None:
        if self.api_key is None:
            self.api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

    def generate(self, prompt: str) -> ImageResult:
        """Generate an image from a text prompt."""
        if not self.api_key:
            return ImageResult(prompt=prompt, error="no API key")

        try:
            import httpx
        except ImportError:
            return ImageResult(prompt=prompt, error="httpx not installed")

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
        }

        response = httpx.post(
            f"{self.base_url}/models/{self.model}:generateContent",
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
            },
            json=payload,
            timeout=60.0,
        )

        if response.status_code != 200:
            return ImageResult(prompt=prompt, model=self.model, error=f"HTTP {response.status_code}")

        data = response.json()
        parts = (
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [])
        )

        for part in parts:
            if "inlineData" in part:
                import base64
                image_data = base64.b64decode(part["inlineData"].get("data", ""))
                mime = part["inlineData"].get("mimeType", "image/png")
                return ImageResult(
                    prompt=prompt,
                    image_data=image_data,
                    mime_type=mime,
                    model=self.model,
                )

        return ImageResult(prompt=prompt, model=self.model, error="no image in response")

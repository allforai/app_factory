"""fal.ai image generation — Flux, SDXL, and other models for UI mockups."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class FalImageResult:
    """Result from fal.ai image generation."""

    prompt: str
    image_url: str = ""
    image_urls: list[str] = field(default_factory=list)
    model: str = ""
    seed: int = 0
    error: str = ""

    @property
    def success(self) -> bool:
        return bool(self.image_url or self.image_urls) and not self.error


@dataclass(slots=True)
class FalImageClient:
    """fal.ai client for high-quality image generation.

    Supports Flux, SDXL, and other fal.ai hosted models.
    """

    api_key: str | None = None
    base_url: str = "https://queue.fal.run"
    default_model: str = "fal-ai/flux/schnell"

    def __post_init__(self) -> None:
        if self.api_key is None:
            self.api_key = os.getenv("FAL_KEY")

    def generate(
        self,
        prompt: str,
        *,
        model: str | None = None,
        image_size: str = "landscape_16_9",
        num_images: int = 1,
        seed: int | None = None,
    ) -> FalImageResult:
        """Generate images via fal.ai queue API.

        Args:
            prompt: Text description of desired image
            model: fal.ai model endpoint (default: flux/schnell)
            image_size: "square_hd", "landscape_4_3", "landscape_16_9", "portrait_4_3", etc.
            num_images: Number of images to generate
            seed: Optional seed for reproducibility
        """
        if not self.api_key:
            return FalImageResult(prompt=prompt, error="no FAL_KEY")

        try:
            import httpx
        except ImportError:
            return FalImageResult(prompt=prompt, error="httpx not installed")

        endpoint = model or self.default_model
        headers = {
            "Authorization": f"Key {self.api_key}",
            "Content-Type": "application/json",
        }

        payload: dict[str, Any] = {
            "prompt": prompt,
            "image_size": image_size,
            "num_images": num_images,
        }
        if seed is not None:
            payload["seed"] = seed

        # Submit to queue
        try:
            resp = httpx.post(
                f"{self.base_url}/{endpoint}",
                headers=headers,
                json=payload,
                timeout=10.0,
            )
        except Exception as e:
            return FalImageResult(prompt=prompt, model=endpoint, error=str(e))

        if resp.status_code != 200:
            return FalImageResult(prompt=prompt, model=endpoint, error=f"HTTP {resp.status_code}: {resp.text[:200]}")

        data = resp.json()

        # Queue mode: poll for result
        if "request_id" in data:
            return self._poll_result(data, endpoint, headers, prompt)

        # Sync mode: result already available
        return self._parse_result(data, endpoint, prompt)

    def _poll_result(
        self,
        queue_data: dict[str, Any],
        endpoint: str,
        headers: dict[str, str],
        prompt: str,
    ) -> FalImageResult:
        """Poll queue until result is ready."""
        import httpx

        request_id = queue_data["request_id"]
        status_url = queue_data.get("status_url") or f"https://queue.fal.run/{endpoint}/requests/{request_id}/status"
        result_url = queue_data.get("response_url") or f"https://queue.fal.run/{endpoint}/requests/{request_id}"

        for _ in range(60):  # max 60 seconds
            time.sleep(1)
            try:
                status_resp = httpx.get(status_url, headers=headers, timeout=10.0)
                status = status_resp.json().get("status", "")
                if status == "COMPLETED":
                    result_resp = httpx.get(result_url, headers=headers, timeout=10.0)
                    return self._parse_result(result_resp.json(), endpoint, prompt)
                if status in ("FAILED", "CANCELLED"):
                    return FalImageResult(prompt=prompt, model=endpoint, error=f"Queue {status}")
            except Exception:
                continue

        return FalImageResult(prompt=prompt, model=endpoint, error="Queue timeout")

    def _parse_result(
        self,
        data: dict[str, Any],
        endpoint: str,
        prompt: str,
    ) -> FalImageResult:
        """Parse fal.ai response into FalImageResult."""
        images = data.get("images", [])
        urls = [img.get("url", "") for img in images if img.get("url")]

        return FalImageResult(
            prompt=prompt,
            image_url=urls[0] if urls else "",
            image_urls=urls,
            model=endpoint,
            seed=data.get("seed", 0),
        )

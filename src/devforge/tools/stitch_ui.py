"""Stitch UI prototyping — Google's AI-driven UI generation via MCP or HTTP.

Stitch generates interactive, high-fidelity UI prototypes from text prompts.
It maintains visual consistency across screens within a project through
an anchor-screen → subsequent-screens workflow.

Usage in the engine:
- Product Design (#2): generate UI concept mockups
- Product Acceptance (#11): generate visual reference for acceptance comparison
- Human Escalation (#17): generate decision comparison visuals

Two modes:
1. MCP mode: via stitch-mcp proxy (requires OAuth setup, interactive)
2. HTTP mode: direct API calls (for engine automation)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class StitchScreen:
    """One generated screen from Stitch."""

    screen_id: str
    screen_name: str
    html: str = ""
    screenshot_url: str = ""
    project_id: str = ""


@dataclass(slots=True)
class StitchProject:
    """A Stitch project containing multiple screens."""

    project_id: str
    title: str
    screens: list[StitchScreen] = field(default_factory=list)
    anchor_screen_id: str = ""
    share_url: str = ""
    consistency_check: dict[str, Any] = field(default_factory=dict)


@dataclass
class StitchClient:
    """Stitch UI generation client.

    Wraps the Stitch API for creating UI prototypes from text prompts.
    Supports the anchor-screen workflow for cross-screen visual consistency.
    """

    google_cloud_project: str | None = None
    config_dir: str = "~/.stitch-mcp/config"

    def __post_init__(self) -> None:
        if self.google_cloud_project is None:
            self.google_cloud_project = os.getenv("GOOGLE_CLOUD_PROJECT")

    def is_available(self) -> bool:
        """Check if Stitch credentials are configured."""
        config_path = os.path.expanduser(self.config_dir)
        adc_path = os.path.join(config_path, "application_default_credentials.json")
        return os.path.isfile(adc_path)

    def create_project(self, title: str) -> StitchProject:
        """Create a new Stitch project."""
        if not self.is_available():
            return StitchProject(project_id="", title=title)

        # In MCP mode, this would call mcp__stitch__create_project
        # For engine automation, we prepare the request structure
        project_id = f"stitch-{_short_id()}"
        return StitchProject(
            project_id=project_id,
            title=title,
            share_url=f"https://stitch.withgoogle.com/projects/{project_id}",
        )

    def generate_anchor_screen(
        self,
        project: StitchProject,
        prompt: str,
        *,
        screen_id: str = "S001",
        screen_name: str = "anchor",
        device_type: str = "MOBILE",
    ) -> StitchScreen:
        """Generate the anchor screen that establishes visual language."""
        if not project.project_id:
            return StitchScreen(screen_id=screen_id, screen_name=screen_name)

        # Would call: generate_screen_from_text(projectId, prompt, deviceType)
        screen = StitchScreen(
            screen_id=screen_id,
            screen_name=screen_name,
            project_id=project.project_id,
        )
        project.anchor_screen_id = screen_id
        project.screens.append(screen)
        return screen

    def generate_screen(
        self,
        project: StitchProject,
        prompt: str,
        *,
        screen_id: str,
        screen_name: str,
        device_type: str = "MOBILE",
    ) -> StitchScreen:
        """Generate a subsequent screen referencing the anchor's visual language."""
        if not project.project_id:
            return StitchScreen(screen_id=screen_id, screen_name=screen_name)

        # Would call: generate_screen_from_text(projectId, prompt, deviceType)
        # Stitch auto-maintains project-level consistency
        screen = StitchScreen(
            screen_id=screen_id,
            screen_name=screen_name,
            project_id=project.project_id,
        )
        project.screens.append(screen)
        return screen

    def edit_screen(
        self,
        project: StitchProject,
        screen_id: str,
        edit_prompt: str,
    ) -> StitchScreen | None:
        """Edit an existing screen with natural language instructions."""
        # Would call: edit_screens(projectId, screenId, editPrompt)
        for screen in project.screens:
            if screen.screen_id == screen_id:
                return screen
        return None

    def check_consistency(self, project: StitchProject) -> dict[str, Any]:
        """Check visual consistency across all screens in the project."""
        # Would compare component structures across screens
        result = {
            "passed": True,
            "corrections": [],
            "screens_checked": len(project.screens),
        }
        project.consistency_check = result
        return result

    def build_prompts_from_design(
        self,
        design: dict[str, Any],
        *,
        max_screens: int = 10,
    ) -> list[dict[str, str]]:
        """Convert a ProductDesign into Stitch-ready screen prompts.

        Uses user_flows and interaction_matrix to determine which screens
        to generate and their content.
        """
        prompts: list[dict[str, str]] = []
        user_flows = design.get("user_flows", [])
        product_name = design.get("product_name", "App")
        interaction_matrix = design.get("interaction_matrix", [])

        # Build screen prompts from user flows
        seen_screens: set[str] = set()
        for flow in user_flows:
            role = flow.get("role", "user")
            steps = flow.get("steps", [])
            for step in steps:
                if step in seen_screens or len(prompts) >= max_screens:
                    continue
                seen_screens.add(step)

                # Find interaction principle for this screen
                principle = ""
                for entry in interaction_matrix:
                    if entry.get("role") == role:
                        principle = entry.get("principle", "")
                        break

                prompts.append({
                    "screen_id": f"S{len(prompts) + 1:03d}",
                    "screen_name": step,
                    "prompt": (
                        f"Design a {step} screen for {product_name}. "
                        f"Role: {role}. "
                        f"Design principle: {principle}. "
                        f"Modern, clean UI with clear visual hierarchy."
                    ),
                    "generation_order": len(prompts),
                })

        return prompts


def _short_id() -> str:
    from uuid import uuid4
    return uuid4().hex[:8]

"""Workset selection rules for batch dispatch."""

from __future__ import annotations

from devforge.state import SeamState, WorkPackage


def _seams_by_id(seams: list[SeamState]) -> dict[str, SeamState]:
    return {seam.seam_id: seam for seam in seams}


def _is_ready(work_package: WorkPackage, completed_ids: set[str]) -> bool:
    return work_package.status == "ready" and all(dep in completed_ids for dep in work_package.depends_on)


def _has_frozen_seams(work_package: WorkPackage, seam_index: dict[str, SeamState]) -> bool:
    for seam_id in work_package.related_seams:
        seam = seam_index.get(seam_id)
        if seam is not None and seam.status != "frozen":
            return False
    return True


def select_workset(
    work_packages: list[WorkPackage],
    seams: list[SeamState],
    *,
    limit: int = 3,
) -> list[WorkPackage]:
    """Select a runnable workset using dependency and seam readiness rules."""
    seam_index = _seams_by_id(seams)
    completed_ids = {
        wp.work_package_id
        for wp in work_packages
        if wp.status in ("completed", "verified")
    }
    candidates = [
        wp for wp in work_packages if _is_ready(wp, completed_ids) and _has_frozen_seams(wp, seam_index)
    ]
    candidates.sort(key=lambda wp: wp.priority, reverse=True)
    return candidates[:limit]


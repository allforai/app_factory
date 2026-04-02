"""Role registry exports."""

from .registry import ROLE_REGISTRY, get_role_spec
from .specs import RoleSpec

__all__ = ["ROLE_REGISTRY", "RoleSpec", "get_role_spec"]


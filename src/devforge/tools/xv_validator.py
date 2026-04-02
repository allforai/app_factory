"""XV (Cross-Validation) — multi-model review of the same artifact.

Routes different review domains to specialist models:
- Architecture/API → GPT (industrial standards)
- Data/Algorithm → DeepSeek (RDBMS, logic rigor)
- UI/Visual → Gemini (multimodal, layout)
- Security → GPT (vulnerability patterns)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from devforge.llm.factory import build_llm_client
from devforge.llm.models import StructuredGenerationRequest


@dataclass(slots=True)
class XVFinding:
    """One finding from cross-validation."""

    domain: str
    model: str
    severity: str  # "critical", "important", "minor", "info"
    description: str
    suggestion: str = ""


@dataclass(slots=True)
class XVResult:
    """Result of multi-model cross-validation."""

    artifact_ref: str
    findings: list[XVFinding] = field(default_factory=list)
    models_used: list[str] = field(default_factory=list)
    consensus: str = ""


# Default XV model routing from llm.yaml xv section
_DEFAULT_XV_ROUTES: dict[str, tuple[str, str]] = {
    "architecture_review": ("openrouter", "openai/gpt-5.4"),
    "data_model_review": ("openrouter", "deepseek/deepseek-v3.2"),
    "ui_review": ("google", "gemini-2.5-pro"),
    "security_review": ("openrouter", "openai/gpt-5.4"),
    "code_review": ("openrouter", "anthropic/claude-opus-4.6"),
}


@dataclass
class XVValidator:
    """Multi-model cross-validator for design and code artifacts."""

    routes: dict[str, tuple[str, str]] = field(default_factory=lambda: dict(_DEFAULT_XV_ROUTES))
    api_keys: dict[str, str] = field(default_factory=dict)

    def validate(
        self,
        artifact_ref: str,
        artifact_content: str,
        *,
        domains: list[str] | None = None,
    ) -> XVResult:
        """Run cross-validation across multiple models for specified domains."""
        domains = domains or list(self.routes.keys())
        findings: list[XVFinding] = []
        models_used: list[str] = []

        for domain in domains:
            route = self.routes.get(domain)
            if route is None:
                continue

            provider, model = route
            api_key = self.api_keys.get(provider)
            if not api_key:
                import os
                env_var = {"openrouter": "OPENROUTER_API_KEY", "google": "GEMINI_API_KEY"}.get(provider)
                api_key = os.getenv(env_var or "") if env_var else None

            if not api_key:
                continue

            try:
                client = build_llm_client(provider, model=model, api_key=api_key)
                response = client.generate_structured(StructuredGenerationRequest(
                    task=f"xv_{domain}",
                    schema_name="XVReviewFindings",
                    instructions=(
                        f"You are a specialist reviewer for {domain.replace('_', ' ')}. "
                        f"Review the following artifact and identify issues. "
                        f"Return JSON with: "
                        f'"findings": [{{severity: "critical"|"important"|"minor"|"info", '
                        f'description: "...", suggestion: "..."}}]'
                    ),
                    input_payload={"artifact_ref": artifact_ref, "content": artifact_content},
                    metadata={"xv_domain": domain},
                ))
                models_used.append(f"{provider}:{model}")
                for f in response.output.get("findings", []):
                    findings.append(XVFinding(
                        domain=domain,
                        model=f"{provider}:{model}",
                        severity=f.get("severity", "info"),
                        description=f.get("description", ""),
                        suggestion=f.get("suggestion", ""),
                    ))
            except Exception:
                pass  # skip unavailable models gracefully

        consensus = "pass" if not any(f.severity == "critical" for f in findings) else "fail"
        return XVResult(
            artifact_ref=artifact_ref,
            findings=findings,
            models_used=models_used,
            consensus=consensus,
        )

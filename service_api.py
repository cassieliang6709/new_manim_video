from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from generator import SceneComplexity, SceneDescription
from input_processing import detect_input_type, normalize_content
from preferences import load_preferences, update_preferences
from style_catalog import apply_style_prompt, get_style, list_styles
from template_library import get_template, list_templates, search_templates
from export_tools import export_video


@dataclass
class GenerationRequest:
    prompt: str
    style: str | None = None
    quality: str | None = None
    output_format: str | None = None
    complexity: SceneComplexity = SceneComplexity.MODERATE


def build_orchestrator(
    *,
    working_dir: Path,
    model_name: str = "gemini-2.5-pro",
    temperature: float = 0.2,
    top_p: float = 0.95,
    use_local_manim: bool = False,
) -> Any:
    from auditor import LLMJudgeAuditor, SecurityAuditor
    from executor import LocalExecutor, SandboxExecutor
    from orchestrator import WorkflowOrchestrator

    executor = LocalExecutor() if use_local_manim else SandboxExecutor()
    return WorkflowOrchestrator(
        auditors=[SecurityAuditor(), LLMJudgeAuditor()],
        executor=executor,
        working_dir=working_dir,
        max_retries=3,
        model_name=model_name,
        temperature=temperature,
        top_p=top_p,
    )


def build_scene_description(request: GenerationRequest) -> SceneDescription:
    preferences = load_preferences()
    style_name = request.style or preferences["style"]["preset"]
    narrative = apply_style_prompt(request.prompt, style_name)
    extra_context = {
        "style": get_style(style_name).display_name,
        "quality": request.quality or preferences["output"]["default_quality"],
        "output_format": request.output_format or preferences["output"]["default_format"],
    }
    return SceneDescription(
        title="GeneratedScene",
        narrative=narrative,
        complexity=request.complexity,
        extra_context=extra_context,
    )


def generate_animation(
    request: GenerationRequest,
    *,
    orchestrator: Any,
) -> Any:
    description = build_scene_description(request)
    return orchestrator.run(description)


def get_capabilities() -> dict[str, Any]:
    return {
        "styles": list_styles(),
        "preferences": load_preferences(),
        "templates": list_templates(),
    }


__all__ = [
    "GenerationRequest",
    "build_orchestrator",
    "build_scene_description",
    "detect_input_type",
    "export_video",
    "generate_animation",
    "get_capabilities",
    "get_style",
    "get_template",
    "list_styles",
    "list_templates",
    "load_preferences",
    "normalize_content",
    "search_templates",
    "update_preferences",
]

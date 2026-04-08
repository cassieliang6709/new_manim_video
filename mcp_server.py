from __future__ import annotations

import json
import os
from pathlib import Path

from service_api import (
    GenerationRequest,
    build_orchestrator,
    generate_animation,
    get_template,
    list_styles,
    list_templates,
    load_preferences,
    search_templates,
    update_preferences,
)

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover
    raise RuntimeError(
        "mcp is not installed. Install it separately if you want to run the MCP server."
    ) from exc


OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "./manim_output"))
MODEL_NAME = os.environ.get("MODEL_NAME", "gemini-2.5-pro")

mcp = FastMCP(
    "visocode",
    instructions=(
        "Generate, template, and configure Manim teaching animations. "
        "All generation requests run through the audited Visocode orchestrator."
    ),
)


@mcp.tool()
def generate_animation_tool(prompt: str, style: str | None = None) -> str:
    orchestrator = build_orchestrator(working_dir=OUTPUT_DIR, model_name=MODEL_NAME)
    result = generate_animation(
        GenerationRequest(prompt=prompt, style=style),
        orchestrator=orchestrator,
    )
    payload = {
        "status": result.status.value,
        "attempts": result.total_attempts,
        "output_files": [str(item) for item in result.output_files],
        "is_fallback": result.is_fallback,
        "error_message": (result.final_state or {}).get("error_message", ""),
    }
    return json.dumps(payload, ensure_ascii=False)


@mcp.tool()
def list_templates_tool(category: str | None = None, difficulty: int | None = None) -> str:
    return json.dumps(list_templates(category=category, difficulty=difficulty), ensure_ascii=False)


@mcp.tool()
def get_template_tool(template_id: str) -> str:
    return json.dumps(get_template(template_id), ensure_ascii=False)


@mcp.tool()
def search_templates_tool(keyword: str) -> str:
    return json.dumps(search_templates(keyword), ensure_ascii=False)


@mcp.tool()
def list_styles_tool() -> str:
    return json.dumps(list_styles(), ensure_ascii=False)


@mcp.tool()
def get_preferences_tool() -> str:
    return json.dumps(load_preferences(), ensure_ascii=False)


@mcp.tool()
def set_preferences_tool(preferences_json: str) -> str:
    updates = json.loads(preferences_json)
    return json.dumps(update_preferences(updates), ensure_ascii=False)


def run() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    run()

"""
run.py

CLI for Visocode's reusable service layer.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)

from generator import SceneComplexity
from service_api import (
    GenerationRequest,
    build_orchestrator,
    export_video,
    generate_animation,
    get_template,
    list_styles,
    list_templates,
    load_preferences,
    search_templates,
    update_preferences,
)


def _cmd_generate(args: argparse.Namespace) -> int:
    orchestrator = build_orchestrator(
        working_dir=Path(args.output_dir),
        model_name=args.model,
        temperature=args.temperature,
        top_p=args.top_p,
        use_local_manim=args.local,
    )
    request = GenerationRequest(
        prompt=args.prompt,
        style=args.style,
        quality=args.quality,
        output_format=args.format,
        complexity=SceneComplexity.MODERATE,
    )
    result = generate_animation(request, orchestrator=orchestrator)

    print("\n" + "=" * 60)
    if result.status.value == "success":
        print("success")
        if result.output_files:
            print(f"video_path: {result.output_files[0]}")
        print(f"attempts: {result.total_attempts}")
        if args.format != "mp4" and result.output_files:
            export_result = export_video(str(result.output_files[0]), fmt=args.format)
            if export_result.get("success"):
                print(f"exported_path: {export_result['file_path']}")
            else:
                print(f"export_error: {export_result['error']}")
    else:
        print(f"status: {result.status.value}")
        print(f"attempts: {result.total_attempts}")
        if result.final_state and result.final_state.get("error_message"):
            print(f"error: {result.final_state['error_message']}")
    print("=" * 60 + "\n")
    return 0 if result.status.value == "success" else 1


def _cmd_list_templates(args: argparse.Namespace) -> int:
    items = list_templates(category=args.category, difficulty=args.difficulty)
    print(json.dumps(items, ensure_ascii=False, indent=2))
    return 0


def _cmd_show_template(args: argparse.Namespace) -> int:
    print(json.dumps(get_template(args.template_id), ensure_ascii=False, indent=2))
    return 0


def _cmd_search_templates(args: argparse.Namespace) -> int:
    print(json.dumps(search_templates(args.keyword), ensure_ascii=False, indent=2))
    return 0


def _cmd_list_styles(args: argparse.Namespace) -> int:
    print(json.dumps(list_styles(), ensure_ascii=False, indent=2))
    return 0


def _cmd_prefs_get(args: argparse.Namespace) -> int:
    print(json.dumps(load_preferences(), ensure_ascii=False, indent=2))
    return 0


def _cmd_prefs_set(args: argparse.Namespace) -> int:
    updates = json.loads(args.updates)
    print(json.dumps(update_preferences(updates), ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Visocode CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate_parser = subparsers.add_parser("generate", help="Generate a video from a natural-language prompt")
    generate_parser.add_argument("prompt")
    generate_parser.add_argument("--style", default=None, help="Style preset name")
    generate_parser.add_argument("--model", default="gemini-2.5-pro")
    generate_parser.add_argument("--temperature", type=float, default=0.2)
    generate_parser.add_argument("--top-p", type=float, default=0.95)
    generate_parser.add_argument("--quality", default="medium")
    generate_parser.add_argument("--format", default="mp4", choices=["mp4", "gif", "webm"])
    generate_parser.add_argument("--output-dir", default="/tmp/manim_output")
    generate_parser.add_argument("--local", action="store_true")
    generate_parser.set_defaults(func=_cmd_generate)

    templates_parser = subparsers.add_parser("list-templates", help="List curated templates")
    templates_parser.add_argument("--category", default=None)
    templates_parser.add_argument("--difficulty", type=int, default=None)
    templates_parser.set_defaults(func=_cmd_list_templates)

    template_parser = subparsers.add_parser("show-template", help="Show a template's metadata and code")
    template_parser.add_argument("template_id")
    template_parser.set_defaults(func=_cmd_show_template)

    search_parser = subparsers.add_parser("search-templates", help="Search templates by keyword")
    search_parser.add_argument("keyword")
    search_parser.set_defaults(func=_cmd_search_templates)

    styles_parser = subparsers.add_parser("list-styles", help="List style presets")
    styles_parser.set_defaults(func=_cmd_list_styles)

    prefs_parser = subparsers.add_parser("prefs", help="Read or update saved preferences")
    prefs_subparsers = prefs_parser.add_subparsers(dest="prefs_command", required=True)

    prefs_get_parser = prefs_subparsers.add_parser("get")
    prefs_get_parser.set_defaults(func=_cmd_prefs_get)

    prefs_set_parser = prefs_subparsers.add_parser("set")
    prefs_set_parser.add_argument("updates", help='JSON string, e.g. {"style":{"preset":"classic_blackboard"}}')
    prefs_set_parser.set_defaults(func=_cmd_prefs_set)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_PREFERENCES_PATH = Path(
    os.environ.get("MANIM_PREFS_PATH", PROJECT_ROOT / "manim_prefs.json")
)

DEFAULT_PREFERENCES: dict[str, Any] = {
    "style": {"preset": "minimalist_dark"},
    "audience": {"level": 3, "language": "en"},
    "output": {"default_quality": "medium", "default_format": "mp4"},
    "animation": {"speed_multiplier": 1.0, "font_scale": 1.0},
    "branding": {"watermark": "", "intro_text": "", "outro_text": ""},
}


def _deep_merge(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_preferences(path: Path | None = None) -> dict[str, Any]:
    prefs_path = path or DEFAULT_PREFERENCES_PATH
    if not prefs_path.exists():
        return deepcopy(DEFAULT_PREFERENCES)
    try:
        with open(prefs_path, encoding="utf-8") as fh:
            stored = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return deepcopy(DEFAULT_PREFERENCES)
    return _deep_merge(DEFAULT_PREFERENCES, stored if isinstance(stored, dict) else {})


def save_preferences(preferences: dict[str, Any], path: Path | None = None) -> Path:
    prefs_path = path or DEFAULT_PREFERENCES_PATH
    prefs_path.parent.mkdir(parents=True, exist_ok=True)
    with open(prefs_path, "w", encoding="utf-8") as fh:
        json.dump(preferences, fh, ensure_ascii=False, indent=2)
    return prefs_path


def update_preferences(updates: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    preferences = _deep_merge(load_preferences(path), updates)
    save_preferences(preferences, path)
    return preferences

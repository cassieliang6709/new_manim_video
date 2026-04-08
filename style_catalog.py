from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StylePreset:
    name: str
    display_name: str
    background_color: str
    text_color: str
    primary_color: str
    secondary_color: str
    accent_color: str
    description: str
    suitable_for: str
    prompt_directive: str


PRESETS: dict[str, StylePreset] = {
    "minimalist_dark": StylePreset(
        name="minimalist_dark",
        display_name="Minimalist Dark",
        background_color="#000000",
        text_color="#FFFFFF",
        primary_color="#FFFFFF",
        secondary_color="#888888",
        accent_color="#D9D9D9",
        description="Clean black-and-white visual language with restrained motion.",
        suitable_for="General explanation, proofs, clean technical demos",
        prompt_directive=(
            "\n\nVISUAL STYLE DIRECTIVE — Minimalist Dark:\n"
            "- Background: pure black (#000000).\n"
            "- Text / main elements: white (#FFFFFF).\n"
            "- Accent: muted gray (#888888) for secondary elements.\n"
            "- Animations: FadeIn / FadeOut, slow and deliberate (wait >= 1 s).\n"
            "- Absolutely no decorative geometry — let the content speak.\n"
            "- Prefer Write() for text and Create() for shapes.\n"
        ),
    ),
    "classic_blackboard": StylePreset(
        name="classic_blackboard",
        display_name="Classic Blackboard",
        background_color="#1A4A2E",
        text_color="#F5F5DC",
        primary_color="#FFFFFF",
        secondary_color="#FFE4B5",
        accent_color="#87CEEB",
        description="Chalkboard aesthetic with soft classroom colors.",
        suitable_for="Teaching, school math, step-by-step walkthroughs",
        prompt_directive=(
            "\n\nVISUAL STYLE DIRECTIVE — Classic Blackboard:\n"
            "- Background: dark green (#1a4a2e) to evoke a chalkboard.\n"
            "- Text: cream-white (#F5F5DC) as chalk strokes.\n"
            "- Use Write() for all text, DrawBorderThenFill() for shapes.\n"
            "- Colours: soft yellow, chalk pink, and light blue — like colored chalk.\n"
            "- Use Text() for equations (no LaTeX/MathTex); animate them as if handwritten.\n"
            "- Pacing: moderate (wait ~0.8 s between steps).\n"
        ),
    ),
    "futuristic_tech": StylePreset(
        name="futuristic_tech",
        display_name="Futuristic Tech",
        background_color="#050A1A",
        text_color="#D8F3FF",
        primary_color="#00FFFF",
        secondary_color="#7B2FBE",
        accent_color="#FF006E",
        description="Fast, high-contrast neon style for CS and data visuals.",
        suitable_for="Algorithms, data structures, modern explainers",
        prompt_directive=(
            "\n\nVISUAL STYLE DIRECTIVE — Futuristic Tech:\n"
            "- Background: very dark navy (#050A1A).\n"
            "- Primary accent: electric cyan (#00FFFF).\n"
            "- Secondary accents: purple (#7B2FBE) and hot pink (#FF006E).\n"
            "- Animations: GrowFromCenter(), Create() — fast and energetic.\n"
            "- Shorten wait() calls (0.3 – 0.5 s) for a rapid, dynamic feel.\n"
            "- Math elements should look like holographic read-outs.\n"
        ),
    ),
}


def get_style(name: str | None) -> StylePreset:
    if name and name in PRESETS:
        return PRESETS[name]
    return PRESETS["minimalist_dark"]


def list_styles() -> list[dict[str, str]]:
    return [
        {
            "name": preset.name,
            "display_name": preset.display_name,
            "description": preset.description,
            "suitable_for": preset.suitable_for,
            "background_color": preset.background_color,
        }
        for preset in PRESETS.values()
    ]


def apply_style_prompt(prompt: str, style_name: str | None) -> str:
    return prompt.strip() + get_style(style_name).prompt_directive

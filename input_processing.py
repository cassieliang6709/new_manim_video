from __future__ import annotations

import re
from typing import Any


def detect_input_type(content: str) -> dict[str, Any]:
    text = content.strip()
    has_latex = bool(re.search(r"\\(frac|sqrt|sum|int|sin|cos|tan|log|ln)", text))
    has_math_symbols = bool(re.search(r"[∫∑√∞≤≥≠≈π]", text))
    has_chinese = any("\u4e00" <= ch <= "\u9fff" for ch in text)
    lowered = text.lower()

    if any(token in lowered for token in ["change", "modify", "faster", "slower", "color", "style"]):
        return {"type": "modification", "language": "zh" if has_chinese else "en", "confidence": 0.8}
    if has_latex:
        return {"type": "latex_formula", "language": "mixed" if has_chinese else "en", "confidence": 0.9}
    if has_math_symbols or any(token in text for token in ["证明", "求", "解", "="]):
        return {"type": "math_problem", "language": "zh" if has_chinese else "en", "confidence": 0.8}
    if any(token in lowered for token in ["animate", "visualize", "show", "demonstrate", "动画", "可视化"]):
        return {"type": "animation_request", "language": "zh" if has_chinese else "en", "confidence": 0.8}
    return {"type": "concept_description", "language": "zh" if has_chinese else "en", "confidence": 0.5}


def normalize_content(raw_text: str) -> dict[str, Any]:
    detected = detect_input_type(raw_text)
    inline = re.findall(r"\$([^$]+)\$", raw_text)
    display = re.findall(r"\$\$([^$]+)\$\$", raw_text)
    formulas = list(dict.fromkeys(display + inline))
    text_clean = re.sub(r"\$\$[^$]+\$\$", "", raw_text)
    text_clean = re.sub(r"\$[^$]+\$", "", text_clean)
    segments = [segment.strip() for segment in text_clean.splitlines() if segment.strip()]
    return {
        "type": detected["type"],
        "language": detected["language"],
        "formulas": formulas,
        "text_segments": segments,
        "raw": raw_text,
    }

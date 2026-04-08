from __future__ import annotations

import re
from pathlib import Path


TEMPLATES_DIR = Path(__file__).resolve().parent / "animation_templates"
_REGISTRY: dict[str, dict] = {}


def _scan_templates() -> None:
    global _REGISTRY
    if _REGISTRY:
        return
    for category_dir in sorted(TEMPLATES_DIR.iterdir()):
        if not category_dir.is_dir():
            continue
        for path in sorted(category_dir.glob("*.py")):
            content = path.read_text(encoding="utf-8")
            title = path.stem.replace("_", " ").title()
            description = ""
            keywords: list[str] = []
            difficulty = 3
            doc_match = re.search(r'"""(.*?)"""', content, re.DOTALL)
            if doc_match:
                lines = [line.strip() for line in doc_match.group(1).strip().splitlines() if line.strip()]
                if lines:
                    title = lines[0]
                for line in lines[1:]:
                    if line.startswith("Keywords:"):
                        keywords = [item.strip() for item in line.split(":", 1)[1].split(",") if item.strip()]
                    elif line.startswith("Difficulty:"):
                        try:
                            difficulty = int(line.split(":", 1)[1].strip())
                        except ValueError:
                            pass
                    elif not description:
                        description = line
            template_id = f"{category_dir.name}/{path.stem}"
            _REGISTRY[template_id] = {
                "id": template_id,
                "category": category_dir.name,
                "title": title,
                "description": description,
                "keywords": keywords,
                "difficulty": difficulty,
                "file_path": str(path),
            }


def list_templates(category: str | None = None, difficulty: int | None = None) -> list[dict]:
    _scan_templates()
    results = list(_REGISTRY.values())
    if category:
        results = [item for item in results if item["category"] == category]
    if difficulty is not None:
        results = [item for item in results if item["difficulty"] <= difficulty]
    return results


def get_template(template_id: str) -> dict:
    _scan_templates()
    meta = _REGISTRY.get(template_id)
    if not meta:
        return {"error": f"Template '{template_id}' not found", "available": sorted(_REGISTRY)}
    code = Path(meta["file_path"]).read_text(encoding="utf-8")
    return {**meta, "code": code}


def search_templates(keyword: str) -> list[dict]:
    _scan_templates()
    needle = keyword.lower()
    return [
        item for item in _REGISTRY.values()
        if needle in f"{item['title']} {item['description']} {' '.join(item['keywords'])}".lower()
    ]

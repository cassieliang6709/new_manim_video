from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from generator import SceneComplexity
from preferences import load_preferences, update_preferences
from service_api import GenerationRequest, build_scene_description
from style_catalog import get_style, list_styles
from template_library import get_template, list_templates, search_templates


class TestStyleCatalog(unittest.TestCase):
    def test_list_styles_contains_expected_presets(self) -> None:
        names = {item["name"] for item in list_styles()}
        self.assertIn("minimalist_dark", names)
        self.assertIn("classic_blackboard", names)
        self.assertIn("futuristic_tech", names)

    def test_get_style_falls_back_to_default(self) -> None:
        self.assertEqual(get_style("missing-style").name, "minimalist_dark")


class TestTemplateLibrary(unittest.TestCase):
    def test_list_templates_returns_curated_assets(self) -> None:
        items = list_templates()
        self.assertGreaterEqual(len(items), 6)

    def test_get_template_returns_code(self) -> None:
        item = get_template("geometry/pythagorean")
        self.assertIn("code", item)
        self.assertIn("PythagoreanTemplate", item["code"])

    def test_search_templates_matches_keywords(self) -> None:
        items = search_templates("bubble")
        ids = {item["id"] for item in items}
        self.assertIn("cs/bubble_sort", ids)


class TestPreferences(unittest.TestCase):
    def test_update_preferences_deep_merges_nested_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "prefs.json"
            updated = update_preferences(
                {"style": {"preset": "classic_blackboard"}, "output": {"default_format": "gif"}},
                path=path,
            )
            self.assertEqual(updated["style"]["preset"], "classic_blackboard")
            self.assertEqual(updated["output"]["default_format"], "gif")
            loaded = load_preferences(path)
            self.assertEqual(loaded["style"]["preset"], "classic_blackboard")


class TestSceneDescriptionBuilder(unittest.TestCase):
    def test_build_scene_description_injects_style_metadata(self) -> None:
        description = build_scene_description(
            GenerationRequest(
                prompt="Visualize bubble sort",
                style="futuristic_tech",
                quality="high",
                output_format="gif",
                complexity=SceneComplexity.COMPLEX,
            )
        )
        self.assertIn("Futuristic Tech", description.narrative)
        self.assertEqual(description.extra_context["quality"], "high")
        self.assertEqual(description.extra_context["output_format"], "gif")
        self.assertEqual(description.complexity, SceneComplexity.COMPLEX)


if __name__ == "__main__":
    unittest.main(verbosity=2)

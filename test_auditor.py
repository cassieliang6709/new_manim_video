"""
test_auditor.py

Unit tests for SecurityAuditor.  Verifies that the AST-based scanner catches
dangerous constructs and correctly passes clean Manim code.

Run with:
    python -m pytest test_auditor.py -v
or:
    python -m unittest test_auditor -v
"""

import unittest

from auditor import AuditResult, SecurityAuditor


class TestSecurityAuditorScan(unittest.TestCase):
    """Tests for the low-level _scan() method (returns plain dict)."""

    def setUp(self) -> None:
        self.auditor = SecurityAuditor()

    # ------------------------------------------------------------------
    # Malicious patterns that MUST be blocked
    # ------------------------------------------------------------------

    def test_os_system_call_is_blocked(self) -> None:
        """os.system('rm -rf /') must be detected as unsafe."""
        code = "os.system('rm -rf /')"
        result = self.auditor._scan(code)
        self.assertFalse(result["is_safe"])
        self.assertIn("os.system", result["reason"])

    def test_import_os_is_blocked(self) -> None:
        """A bare `import os` must be caught."""
        code = "import os"
        result = self.auditor._scan(code)
        self.assertFalse(result["is_safe"])
        self.assertIn("os", result["reason"])

    def test_import_os_path_is_blocked(self) -> None:
        """`import os.path` must be caught via top-level module check."""
        code = "import os.path"
        result = self.auditor._scan(code)
        self.assertFalse(result["is_safe"])

    def test_from_os_import_is_blocked(self) -> None:
        """`from os import getcwd` must be caught."""
        code = "from os import getcwd"
        result = self.auditor._scan(code)
        self.assertFalse(result["is_safe"])

    def test_import_sys_is_blocked(self) -> None:
        """import sys must be caught."""
        code = "import sys"
        result = self.auditor._scan(code)
        self.assertFalse(result["is_safe"])

    def test_import_subprocess_is_blocked(self) -> None:
        """import subprocess must be caught."""
        code = "import subprocess"
        result = self.auditor._scan(code)
        self.assertFalse(result["is_safe"])

    def test_from_subprocess_import_is_blocked(self) -> None:
        """`from subprocess import call` must be caught."""
        code = "from subprocess import call"
        result = self.auditor._scan(code)
        self.assertFalse(result["is_safe"])

    def test_import_pathlib_is_blocked(self) -> None:
        """import pathlib must be caught."""
        code = "from pathlib import Path"
        result = self.auditor._scan(code)
        self.assertFalse(result["is_safe"])

    def test_eval_call_is_blocked(self) -> None:
        """`eval()` is a blocked built-in."""
        code = 'result = eval("1 + 1")'
        result = self.auditor._scan(code)
        self.assertFalse(result["is_safe"])
        self.assertIn("eval", result["reason"])

    def test_exec_call_is_blocked(self) -> None:
        """`exec()` is a blocked built-in."""
        code = 'exec("import os")'
        result = self.auditor._scan(code)
        self.assertFalse(result["is_safe"])
        self.assertIn("exec", result["reason"])

    def test_open_call_is_blocked(self) -> None:
        """`open()` is a blocked built-in."""
        code = "f = open('/etc/passwd', 'r')"
        result = self.auditor._scan(code)
        self.assertFalse(result["is_safe"])
        self.assertIn("open", result["reason"])

    def test_dunder_import_is_blocked(self) -> None:
        """`__import__()` must be caught."""
        code = "__import__('os').system('id')"
        result = self.auditor._scan(code)
        self.assertFalse(result["is_safe"])

    def test_subprocess_popen_is_blocked(self) -> None:
        """`subprocess.Popen(...)` must be caught via attribute-call check."""
        code = "subprocess.Popen(['ls', '-la'])"
        result = self.auditor._scan(code)
        self.assertFalse(result["is_safe"])
        self.assertIn("subprocess.Popen", result["reason"])

    def test_multiple_violations_all_reported(self) -> None:
        """When code has several violations, all must appear in the reason."""
        code = "import os\nimport sys\neval('1')"
        result = self.auditor._scan(code)
        self.assertFalse(result["is_safe"])
        # All three violations should appear in the combined reason string
        self.assertIn("os", result["reason"])
        self.assertIn("sys", result["reason"])
        self.assertIn("eval", result["reason"])

    def test_syntax_error_is_reported(self) -> None:
        """Unparseable code must be reported as unsafe."""
        code = "def broken(:"
        result = self.auditor._scan(code)
        self.assertFalse(result["is_safe"])
        self.assertIn("SyntaxError", result["reason"])

    # ------------------------------------------------------------------
    # Safe patterns that MUST pass
    # ------------------------------------------------------------------

    def test_clean_manim_code_passes(self) -> None:
        """Standard Manim scene code with no dangerous calls must pass."""
        code = """
from manim import Scene, Circle, BLUE

class MyScene(Scene):
    def construct(self):
        circle = Circle(color=BLUE)
        self.play(circle.animate.scale(2))
        self.wait(1)
"""
        result = self.auditor._scan(code)
        self.assertTrue(result["is_safe"])
        self.assertNotIn("reason", result)

    def test_pure_math_code_passes(self) -> None:
        """Code using only math operations must pass."""
        code = "result = (2 ** 10) + 3.14 * 42"
        result = self.auditor._scan(code)
        self.assertTrue(result["is_safe"])

    def test_safe_imports_pass(self) -> None:
        """Imports from non-blocked modules (manim, math, typing) must pass."""
        code = "from manim import *\nimport math\nfrom typing import Optional"
        result = self.auditor._scan(code)
        self.assertTrue(result["is_safe"])


class TestSecurityAuditorPublicAPI(unittest.TestCase):
    """Tests for the public audit() method → AuditResult integration."""

    def setUp(self) -> None:
        self.auditor = SecurityAuditor()

    def test_audit_returns_audit_result(self) -> None:
        """audit() must always return an AuditResult instance."""
        result = self.auditor.audit("x = 1")
        self.assertIsInstance(result, AuditResult)

    def test_audit_passed_false_on_violation(self) -> None:
        """audit() must set passed=False for malicious code."""
        result = self.auditor.audit("os.system('rm -rf /')")
        self.assertFalse(result.passed)
        self.assertTrue(len(result.issues) > 0)

    def test_audit_passed_true_on_clean_code(self) -> None:
        """audit() must set passed=True for safe code."""
        result = self.auditor.audit("x = 2 + 2")
        self.assertTrue(result.passed)
        self.assertEqual(result.issues, [])

    def test_audit_metadata_contains_scan_dict(self) -> None:
        """The raw scan dict must be stored in metadata['scan']."""
        result = self.auditor.audit("import os")
        self.assertIn("scan", result.metadata)
        scan = result.metadata["scan"]
        self.assertIn("is_safe", scan)
        self.assertFalse(scan["is_safe"])

    def test_describe_returns_string(self) -> None:
        """describe() must return a non-empty string."""
        desc = self.auditor.describe()
        self.assertIsInstance(desc, str)
        self.assertTrue(len(desc) > 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""
auditor.py

Defines the base CodeAuditor abstract class and the SecurityAuditor subclass
for validating and auditing generated Manim code before execution.
"""

import ast
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AuditResult:
    """Represents the outcome of a code audit pass.

    Attributes:
        passed: Whether the audit passed without blocking issues.
        issues: A list of human-readable issue descriptions found during audit.
        metadata: Optional extra data produced by the auditor (e.g. AST stats).
    """

    passed: bool
    issues: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class CodeAuditor(ABC):
    """Abstract base class for all code auditors.

    Subclasses implement domain-specific checks (security, style, correctness,
    etc.) against a string of Python source code.
    """

    @abstractmethod
    def audit(self, source_code: str) -> AuditResult:
        """Analyse *source_code* and return an :class:`AuditResult`.

        Args:
            source_code: The raw Python source code to inspect.

        Returns:
            An :class:`AuditResult` describing any issues found.
        """
        raise NotImplementedError

    @abstractmethod
    def describe(self) -> str:
        """Return a short human-readable description of what this auditor checks.

        Returns:
            A one-line description string.
        """
        raise NotImplementedError


class SecurityAuditor(CodeAuditor):
    """Audits generated code for dangerous constructs before sandbox execution.

    Checks include (but are not limited to):
    - Blocked built-ins (``exec``, ``eval``, ``__import__``, etc.)
    - Filesystem write operations outside allowed paths
    - Network access attempts
    - Use of ``subprocess`` or ``os.system``
    """

    #: Built-in names that are unconditionally disallowed.
    BLOCKED_BUILTINS: frozenset[str] = frozenset(
        {
            "exec",
            "eval",
            "__import__",
            "compile",
            "open",
            "input",
        }
    )

    #: Disallowed module names (top-level imports).
    BLOCKED_MODULES: frozenset[str] = frozenset(
        {
            "subprocess",
            "socket",
            "urllib",
            "requests",
            "httpx",
            "os",
            "sys",
            "shutil",
            "pathlib",
        }
    )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def audit(self, source_code: str) -> AuditResult:
        """Scan *source_code* for security violations using the AST.

        Delegates to :meth:`_scan`, which returns a plain ``dict`` with keys
        ``is_safe`` (``bool``) and, when unsafe, ``reason`` (``str``).  The
        result is then wrapped in an :class:`AuditResult` so this class
        satisfies the :class:`CodeAuditor` contract.

        Args:
            source_code: The raw Python source code to inspect.

        Returns:
            An :class:`AuditResult` with ``passed=False`` if any violation is
            detected, otherwise ``passed=True``.  The raw scan dict is
            preserved in :attr:`~AuditResult.metadata` under the key
            ``"scan"``.
        """
        scan: dict[str, Any] = self._scan(source_code)
        if not scan["is_safe"]:
            return AuditResult(
                passed=False,
                issues=[scan["reason"]],
                metadata={"scan": scan},
            )
        return AuditResult(passed=True, metadata={"scan": scan})

    def describe(self) -> str:
        """Return a description of this auditor's purpose.

        Returns:
            A one-line description string.
        """
        return (
            "SecurityAuditor: blocks dangerous built-ins, disallowed imports, "
            "and network/filesystem access."
        )

    # ------------------------------------------------------------------
    # Core scanning logic
    # ------------------------------------------------------------------

    def _scan(self, source_code: str) -> dict[str, Any]:
        """Parse *source_code* and traverse its AST for security violations.

        This is the primary implementation method.  It returns a plain
        ``dict`` so the logic can be tested independently of
        :class:`AuditResult`.

        Args:
            source_code: Raw Python source to inspect.

        Returns:
            ``{'is_safe': True}`` when no violations are found, or
            ``{'is_safe': False, 'reason': '<description>'}`` otherwise.
            When multiple violations exist, *reason* lists all of them
            separated by ``"; "``.
        """
        try:
            tree = ast.parse(source_code)
        except SyntaxError as exc:
            return {"is_safe": False, "reason": f"SyntaxError while parsing: {exc}"}

        visitor = _SecurityVisitor(
            blocked_modules=self.BLOCKED_MODULES,
            blocked_builtins=self.BLOCKED_BUILTINS,
        )
        visitor.visit(tree)

        if visitor.violations:
            return {"is_safe": False, "reason": "; ".join(visitor.violations)}

        return {"is_safe": True}


# ---------------------------------------------------------------------------
# Internal AST visitor — not part of the public API
# ---------------------------------------------------------------------------

class _SecurityVisitor(ast.NodeVisitor):
    """Private AST visitor that collects security violations.

    The visitor is intentionally separate from :class:`SecurityAuditor` so that
    the traversal logic can be unit-tested in isolation and later swapped out
    without touching the auditor's public interface.

    Args:
        blocked_modules: Top-level module names whose import is forbidden.
        blocked_builtins: Built-in names that must not be called directly.
    """

    def __init__(
        self,
        blocked_modules: frozenset[str],
        blocked_builtins: frozenset[str],
    ) -> None:
        self.blocked_modules = blocked_modules
        self.blocked_builtins = blocked_builtins
        self.violations: list[str] = []

    # ------------------------------------------------------------------
    # Import detection
    # ------------------------------------------------------------------

    def visit_Import(self, node: ast.Import) -> None:
        """Detect ``import <module>`` statements for blocked modules.

        Checks the *top-level* component of the module name so that aliases
        like ``import os.path`` are caught alongside plain ``import os``.

        Args:
            node: The :class:`ast.Import` node being visited.
        """
        for alias in node.names:
            top_level = alias.name.split(".")[0]
            if top_level in self.blocked_modules:
                display = alias.asname or alias.name
                self.violations.append(
                    f"Blocked import '{alias.name}' (aliased as '{display}') "
                    f"at line {node.lineno}"
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Detect ``from <module> import ...`` statements for blocked modules.

        Args:
            node: The :class:`ast.ImportFrom` node being visited.
        """
        if node.module:
            top_level = node.module.split(".")[0]
            if top_level in self.blocked_modules:
                imported_names = ", ".join(a.name for a in node.names)
                self.violations.append(
                    f"Blocked 'from {node.module} import {imported_names}' "
                    f"at line {node.lineno}"
                )
        self.generic_visit(node)

    # ------------------------------------------------------------------
    # Call detection
    # ------------------------------------------------------------------

    def visit_Call(self, node: ast.Call) -> None:
        """Detect dangerous function calls.

        Two categories are handled:

        1. **Bare built-in calls** — e.g. ``eval(...)``, ``exec(...)``,
           ``open(...)`` — identified via an :class:`ast.Name` function node.
        2. **Module-attribute calls** — e.g. ``os.system(...)``,
           ``subprocess.run(...)`` — identified via an :class:`ast.Attribute`
           function node whose *value* is an :class:`ast.Name` matching a
           blocked module.

        Args:
            node: The :class:`ast.Call` node being visited.
        """
        func = node.func

        # Case 1: bare name call — eval(), exec(), open(), __import__(), …
        if isinstance(func, ast.Name) and func.id in self.blocked_builtins:
            self.violations.append(
                f"Blocked built-in call '{func.id}()' at line {node.lineno}"
            )

        # Case 2: attribute call on a blocked module — os.system(), subprocess.Popen(), …
        elif (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id in self.blocked_modules
        ):
            self.violations.append(
                f"Blocked call '{func.value.id}.{func.attr}()' "
                f"at line {node.lineno}"
            )

        self.generic_visit(node)

"""
generator.py

Provides the ManimCodeGenerator class, which translates a high-level scene
description into runnable Manim Python source code via an LLM backend.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SceneComplexity(Enum):
    """Hint to the generator about the expected visual complexity of the scene."""

    SIMPLE = "simple"       # basic shapes / text
    MODERATE = "moderate"   # animations, transforms
    COMPLEX = "complex"     # multiple coordinated sequences, custom mobjects


@dataclass
class SceneDescription:
    """Structured specification of the Manim scene to generate.

    Attributes:
        title: Short title used as the Python class name (CamelCase recommended).
        narrative: Free-text description of what the scene should show.
        complexity: Expected visual complexity; influences generation prompts.
        duration_hint: Approximate desired duration in seconds (best-effort).
        extra_context: Optional key-value pairs forwarded verbatim to the LLM
            (e.g. colour palette, font preferences, voiceover text).
    """

    title: str
    narrative: str
    complexity: SceneComplexity = SceneComplexity.MODERATE
    duration_hint: float = 10.0
    extra_context: dict[str, Any] = field(default_factory=dict)


@dataclass
class GeneratedCode:
    """Container for the artefacts produced by the generator.

    Attributes:
        source_code: The complete, runnable Manim Python script as a string.
        scene_class_name: Name of the ``Scene`` subclass inside *source_code*.
        model_used: Identifier of the LLM model that produced the code.
        prompt_tokens: Number of tokens consumed in the prompt (if available).
        completion_tokens: Number of tokens in the LLM completion (if available).
        raw_response: The unprocessed LLM response for debugging.
    """

    source_code: str
    scene_class_name: str
    model_used: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    raw_response: str = ""


class BaseCodeGenerator(ABC):
    """Abstract interface for all LLM-backed code generators."""

    @abstractmethod
    def generate(self, description: SceneDescription) -> GeneratedCode:
        """Generate Manim source code from a :class:`SceneDescription`.

        Args:
            description: Structured specification of the desired scene.

        Returns:
            A :class:`GeneratedCode` instance containing the source and metadata.
        """
        raise NotImplementedError

    @abstractmethod
    def refine(
        self,
        previous: GeneratedCode,
        feedback: str,
    ) -> GeneratedCode:
        """Refine a previously generated script based on textual feedback.

        Args:
            previous: The :class:`GeneratedCode` produced in the prior attempt.
            feedback: Human- or machine-readable description of what to fix or
                improve (e.g. auditor error messages, visual critique).

        Returns:
            A new :class:`GeneratedCode` instance with the applied changes.
        """
        raise NotImplementedError


class ManimCodeGenerator(BaseCodeGenerator):
    """Generates Manim scene scripts using a configurable LLM backend.

    The generator constructs a structured prompt from a :class:`SceneDescription`,
    calls the LLM, extracts the Python code block from the response, and returns
    a :class:`GeneratedCode` instance.

    Args:
        model: LLM model identifier to use (e.g. ``"claude-opus-4-6"``).
        max_tokens: Maximum completion tokens requested from the LLM.
        temperature: Sampling temperature for generation (0.0 = deterministic).
        system_prompt: Optional override for the system-level instruction sent
            to the LLM before any user message.
    """

    DEFAULT_MODEL: str = "claude-sonnet-4-6"
    DEFAULT_MAX_TOKENS: int = 4096
    DEFAULT_TEMPERATURE: float = 0.2

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
        system_prompt: str | None = None,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.system_prompt = system_prompt or ""

    # ------------------------------------------------------------------
    # BaseCodeGenerator interface
    # ------------------------------------------------------------------

    def generate(self, description: SceneDescription) -> GeneratedCode:
        """Generate a Manim script from *description*.

        Steps (to be implemented):
        1. Build a structured prompt from *description* fields.
        2. Call the LLM client with the prompt.
        3. Extract the Python code block from the raw response.
        4. Parse the scene class name from the extracted code.
        5. Return a populated :class:`GeneratedCode`.

        Args:
            description: Structured specification of the desired scene.

        Returns:
            A :class:`GeneratedCode` instance containing the generated source.
        """
        raise NotImplementedError

    def refine(
        self,
        previous: GeneratedCode,
        feedback: str,
    ) -> GeneratedCode:
        """Produce an improved version of *previous* based on *feedback*.

        Args:
            previous: The code that needs improvement.
            feedback: Description of the issues to address.

        Returns:
            A revised :class:`GeneratedCode` instance.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Private helpers (stubs)
    # ------------------------------------------------------------------

    def _default_system_prompt(self) -> str:
        """Return the default system prompt used for all generation calls.

        Returns:
            A multi-line string with role, constraints, and output format rules.
        """
        raise NotImplementedError

    def _build_user_prompt(self, description: SceneDescription) -> str:
        """Construct the user-turn prompt from a :class:`SceneDescription`.

        Args:
            description: The scene specification to serialise.

        Returns:
            A formatted prompt string.
        """
        raise NotImplementedError

    def _extract_code_block(self, raw_response: str) -> str:
        """Parse and return the Python code block from an LLM response.

        Handles both fenced (`` ```python ... ``` ``) and bare code in the
        response body.

        Args:
            raw_response: The raw string returned by the LLM API.

        Returns:
            The extracted Python source code as a plain string.

        Raises:
            ValueError: If no code block can be identified in *raw_response*.
        """
        raise NotImplementedError

    def _parse_scene_class_name(self, source_code: str) -> str:
        """Extract the ``Scene`` subclass name from *source_code*.

        Args:
            source_code: A Manim Python script string.

        Returns:
            The name of the first ``Scene`` subclass found.

        Raises:
            ValueError: If no ``Scene`` subclass is found in *source_code*.
        """
        raise NotImplementedError

"""Common contracts implemented by diagram rendering backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .models import DiagramLanguage, OutputFormat, ValidationResult


@dataclass(frozen=True)
class RenderedDiagram:
    """Renderer output together with its HTTP media type."""

    content: bytes
    media_type: str


class DiagramRenderer(ABC):
    """Interface that every language-specific renderer must implement."""

    language: DiagramLanguage
    supported_formats: frozenset[OutputFormat]

    @abstractmethod
    def render(
        self,
        source: str,
        output_format: OutputFormat,
        options: Mapping[str, Any] | None = None,
    ) -> RenderedDiagram:
        """Render source to the requested format."""

    @abstractmethod
    def validate(
        self,
        source: str,
        options: Mapping[str, Any] | None = None,
    ) -> ValidationResult:
        """Validate source without returning rendered output."""

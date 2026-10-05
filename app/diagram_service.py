"""Language-agnostic renderer registry and dispatch service."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .errors import DiagramValidationError
from .mermaid_service import MermaidRenderer
from .models import (
    DiagramLanguage,
    OutputFormat,
    ValidationIssue,
    ValidationResult,
)
from .plantuml_service import PlantUMLRenderer
from .renderer import DiagramRenderer, RenderedDiagram
from .security import validate_source


class DiagramRenderingService:
    """Routes requests to renderers registered by source language."""

    def __init__(self, renderers: Iterable[DiagramRenderer]) -> None:
        self._renderers: dict[DiagramLanguage, DiagramRenderer] = {}
        for renderer in renderers:
            if renderer.language in self._renderers:
                raise ValueError(
                    f"A renderer is already registered for {renderer.language.value}"
                )
            self._renderers[renderer.language] = renderer

    @property
    def supported_languages(self) -> tuple[DiagramLanguage, ...]:
        return tuple(self._renderers)

    def render(
        self,
        language: DiagramLanguage,
        source: str,
        output_format: OutputFormat,
        options: Mapping[str, Any] | None = None,
    ) -> RenderedDiagram:
        validate_source(source, options)
        renderer = self._renderer_for(language)
        if output_format not in renderer.supported_formats:
            result = ValidationResult(
                ok=False,
                errors=[
                    ValidationIssue(
                        message=(
                            f"Output format '{output_format.value}' is not supported "
                            f"for language '{language.value}'."
                        )
                    )
                ],
            )
            raise DiagramValidationError(result, language=language)
        return renderer.render(source, output_format, options)

    def validate(
        self,
        language: DiagramLanguage,
        source: str,
        options: Mapping[str, Any] | None = None,
    ) -> ValidationResult:
        validate_source(source, options)
        return self._renderer_for(language).validate(source, options)

    def _renderer_for(self, language: DiagramLanguage) -> DiagramRenderer:
        renderer = self._renderers.get(language)
        if renderer is None:
            result = ValidationResult(
                ok=False,
                errors=[
                    ValidationIssue(
                        message=f"Diagram language '{language.value}' is not supported."
                    )
                ],
            )
            raise DiagramValidationError(result, language=language)
        return renderer


diagram_service = DiagramRenderingService([PlantUMLRenderer(), MermaidRenderer()])

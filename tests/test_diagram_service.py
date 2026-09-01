import unittest
from collections.abc import Mapping
from typing import Any

from app.diagram_service import DiagramRenderingService
from app.errors import DiagramValidationError
from app.models import DiagramLanguage, OutputFormat, ValidationResult
from app.renderer import DiagramRenderer, RenderedDiagram


class StubRenderer(DiagramRenderer):
    language = DiagramLanguage.MERMAID
    supported_formats = frozenset({OutputFormat.SVG})

    def __init__(self) -> None:
        self.render_calls: list[tuple[str, OutputFormat]] = []
        self.validate_calls: list[str] = []

    def render(
        self,
        source: str,
        output_format: OutputFormat,
        options: Mapping[str, Any] | None = None,
    ) -> RenderedDiagram:
        self.render_calls.append((source, output_format))
        return RenderedDiagram(b"<svg />", "image/svg+xml")

    def validate(
        self,
        source: str,
        options: Mapping[str, Any] | None = None,
    ) -> ValidationResult:
        self.validate_calls.append(source)
        return ValidationResult(ok=True)


class TestDiagramRenderingService(unittest.TestCase):
    def setUp(self) -> None:
        self.renderer = StubRenderer()
        self.service = DiagramRenderingService([self.renderer])

    def test_routes_render_by_language(self) -> None:
        rendered = self.service.render(
            DiagramLanguage.MERMAID,
            "flowchart LR\nA --> B",
            OutputFormat.SVG,
        )

        self.assertEqual(rendered.content, b"<svg />")
        self.assertEqual(
            self.renderer.render_calls,
            [("flowchart LR\nA --> B", OutputFormat.SVG)],
        )

    def test_routes_validation_by_language(self) -> None:
        result = self.service.validate(DiagramLanguage.MERMAID, "flowchart LR")

        self.assertTrue(result.ok)
        self.assertEqual(self.renderer.validate_calls, ["flowchart LR"])

    def test_rejects_unsupported_renderer_format(self) -> None:
        with self.assertRaises(DiagramValidationError) as context:
            self.service.render(
                DiagramLanguage.MERMAID,
                "flowchart LR",
                OutputFormat.ASCII,
            )

        self.assertFalse(context.exception.result.ok)
        self.assertIn(
            "not supported",
            context.exception.result.errors[0].message,
        )
        self.assertEqual(self.renderer.render_calls, [])

    def test_rejects_duplicate_language_registration(self) -> None:
        with self.assertRaises(ValueError):
            DiagramRenderingService([StubRenderer(), StubRenderer()])


if __name__ == "__main__":
    unittest.main()

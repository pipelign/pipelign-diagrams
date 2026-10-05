import subprocess
import unittest
from unittest.mock import patch

from app.models import ValidationResult
from app.plantuml_service import (
    PlantUMLConfig,
    PlantUMLInternalError,
    PlantUMLValidationError,
    render_ascii,
    render_png,
    render_svg,
    validate_diagram,
)


class TestPlantUMLConfig(unittest.TestCase):
    def test_from_env_defaults(self) -> None:
        config = PlantUMLConfig.from_env()
        self.assertEqual(config.jar_path, "/app/plantuml/plantuml.jar")
        self.assertGreater(config.timeout_seconds, 0)


class TestRenderFunctions(unittest.TestCase):
    sample_source = "@startuml\nAlice -> Bob: Hi\n@enduml"

    @patch("app.plantuml_service.os.path.exists", return_value=True)
    @patch("app.plantuml_service.run_engine")
    def test_render_svg_success(
        self,
        mock_run: unittest.mock.MagicMock,
        mock_exists: unittest.mock.MagicMock,
    ) -> None:
        completed = subprocess.CompletedProcess(
            args=["java"],
            returncode=0,
            stdout=b"<svg></svg>",
            stderr=b"",
        )
        mock_run.return_value = completed

        svg = render_svg(self.sample_source)
        self.assertEqual(svg, "<svg></svg>")
        mock_exists.assert_called_once()
        mock_run.assert_called_once()

    @patch("app.plantuml_service.os.path.exists", return_value=True)
    @patch("app.plantuml_service.run_engine")
    def test_render_png_validation_error_raises(
        self,
        mock_run: unittest.mock.MagicMock,
        mock_exists: unittest.mock.MagicMock,
    ) -> None:
        stderr_text = "ERROR\n5\nSyntax Error?\n"
        completed = subprocess.CompletedProcess(
            args=["java"],
            returncode=1,
            stdout=b"",
            stderr=stderr_text.encode(),
        )
        mock_run.return_value = completed

        with self.assertRaises(PlantUMLValidationError) as ctx:
            render_png(self.sample_source)

        mock_exists.assert_called_once()
        mock_run.assert_called_once()
        self.assertFalse(ctx.exception.result.ok)
        self.assertGreater(len(ctx.exception.result.errors), 0)

    @patch("app.plantuml_service.os.path.exists", return_value=False)
    def test_render_ascii_missing_jar_raises_internal(
        self,
        mock_exists: unittest.mock.MagicMock,
    ) -> None:
        with self.assertRaises(PlantUMLInternalError) as ctx:
            render_ascii(self.sample_source)

        mock_exists.assert_called_once()
        self.assertIn("PlantUML JAR not found", str(ctx.exception))
        self.assertIn("jarPath", ctx.exception.details)


class TestValidateDiagram(unittest.TestCase):
    @patch("app.plantuml_service.os.path.exists", return_value=True)
    @patch("app.plantuml_service.run_engine")
    def test_validate_diagram_ok(
        self,
        mock_run: unittest.mock.MagicMock,
        mock_exists: unittest.mock.MagicMock,
    ) -> None:
        completed = subprocess.CompletedProcess(
            args=["java"],
            returncode=0,
            stdout=b"",
            stderr=b"",
        )
        mock_run.return_value = completed

        result = validate_diagram("@startuml\nAlice -> Bob: Hi\n@enduml")

        mock_exists.assert_called_once()
        mock_run.assert_called_once()
        self.assertIsInstance(result, ValidationResult)
        self.assertTrue(result.ok)
        self.assertEqual(result.errors, [])

    @patch("app.plantuml_service.os.path.exists", return_value=True)
    @patch("app.plantuml_service.run_engine")
    def test_validate_diagram_invalid_returns_result(
        self,
        mock_run: unittest.mock.MagicMock,
        mock_exists: unittest.mock.MagicMock,
    ) -> None:
        stderr_text = "ERROR\n10\nSyntax Error?\n"
        completed = subprocess.CompletedProcess(
            args=["java"],
            returncode=1,
            stdout=b"",
            stderr=stderr_text.encode(),
        )
        mock_run.return_value = completed

        result = validate_diagram("@startuml\nAlice -> Bob: Hi\n@enduml")

        mock_exists.assert_called_once()
        mock_run.assert_called_once()
        self.assertIsInstance(result, ValidationResult)
        self.assertFalse(result.ok)
        self.assertEqual(len(result.errors), 1)
        self.assertEqual(result.errors[0].line, 11)
        self.assertEqual(result.errors[0].message, "PlantUML syntax error.")


if __name__ == "__main__":
    unittest.main()

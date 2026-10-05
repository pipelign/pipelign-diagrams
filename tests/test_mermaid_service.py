import os
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from app.mermaid_service import (
    MermaidConfig,
    MermaidInternalError,
    MermaidValidationError,
    _parse_validation_output,
    render_png,
    render_svg,
    validate_diagram,
)


class TestMermaidConfig(unittest.TestCase):
    def test_from_env_defaults(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            config = MermaidConfig.from_env()

        self.assertEqual(config.command, "mmdc")
        self.assertGreater(config.timeout_seconds, 0)

    def test_from_env_overrides(self) -> None:
        with patch.dict(
            os.environ,
            {
                "MERMAID_CMD": "/opt/mermaid/mmdc",
                "MERMAID_TIMEOUT_SECONDS": "7.5",
                "MERMAID_PUPPETEER_CONFIG_PATH": "/tmp/puppeteer.json",
            },
            clear=True,
        ):
            config = MermaidConfig.from_env()

        self.assertEqual(config.command, "/opt/mermaid/mmdc")
        self.assertEqual(config.timeout_seconds, 7.5)
        self.assertEqual(config.puppeteer_config_path, "/tmp/puppeteer.json")


class TestMermaidValidationParsing(unittest.TestCase):
    def test_parse_error_is_sanitized_and_includes_line(self) -> None:
        stderr = (
            "Error: Parse error on line 3:\n"
            "...private diagram source...\n"
            "    at Parser.parseError (/internal/path/parser.js:42:1)"
        )

        result = _parse_validation_output(stderr)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertFalse(result.ok)
        self.assertEqual(result.errors[0].line, 3)
        self.assertEqual(result.errors[0].message, "Parse error in Mermaid diagram.")
        self.assertNotIn("private", result.errors[0].message)

    def test_unknown_diagram_error_has_useful_message(self) -> None:
        result = _parse_validation_output(
            "UnknownDiagramError: No diagram type detected matching configuration"
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn("diagram type", result.errors[0].message)

    def test_unrecognized_failure_is_not_treated_as_user_input(self) -> None:
        self.assertIsNone(_parse_validation_output("Browser failed to launch"))


class TestMermaidRenderFunctions(unittest.TestCase):
    source = "flowchart LR\nA --> B"
    config = MermaidConfig(
        command="mmdc",
        timeout_seconds=3,
        puppeteer_config_path="/tmp/puppeteer.json",
    )

    @patch("app.mermaid_service.run_engine")
    def test_render_svg_success(self, mock_run: unittest.mock.MagicMock) -> None:
        def run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            output_path = Path(command[command.index("--output") + 1])
            output_path.write_text("<svg></svg>", encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

        mock_run.side_effect = run

        result = render_svg(self.source, config=self.config)

        self.assertEqual(result, "<svg></svg>")
        command = mock_run.call_args.args[0]
        self.assertIn("--puppeteerConfigFile", command)
        self.assertIn("/tmp/puppeteer.json", command)

    @patch("app.mermaid_service.run_engine")
    def test_render_png_success(self, mock_run: unittest.mock.MagicMock) -> None:
        def run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            output_path = Path(command[command.index("--output") + 1])
            output_path.write_bytes(b"\x89PNG\r\n")
            return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

        mock_run.side_effect = run

        result = render_png(self.source, config=self.config)

        self.assertTrue(result.startswith(b"\x89PNG"))

    @patch("app.mermaid_service.run_engine")
    def test_render_invalid_source_raises_validation_error(
        self,
        mock_run: unittest.mock.MagicMock,
    ) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            ["mmdc"],
            1,
            stdout=b"",
            stderr=b"Error: Parse error on line 2:\nExpecting a node",
        )

        with self.assertRaises(MermaidValidationError) as context:
            render_svg(self.source, config=self.config)

        self.assertEqual(context.exception.result.errors[0].line, 2)

    @patch("app.mermaid_service.run_engine")
    def test_render_renderer_failure_raises_internal_error(
        self,
        mock_run: unittest.mock.MagicMock,
    ) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            ["mmdc"],
            1,
            stdout=b"",
            stderr=b"Browser failed to launch from /private/path",
        )

        with self.assertRaises(MermaidInternalError) as context:
            render_svg(self.source, config=self.config)

        self.assertNotIn("private", context.exception.public_message)
        self.assertNotIn("Browser failed", context.exception.public_message)

    @patch("app.mermaid_service.run_engine")
    def test_validate_returns_invalid_result(
        self,
        mock_run: unittest.mock.MagicMock,
    ) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            ["mmdc"],
            1,
            stdout=b"",
            stderr=b"UnknownDiagramError: No diagram type detected",
        )

        result = validate_diagram(self.source, config=self.config)

        self.assertFalse(result.ok)
        self.assertEqual(len(result.errors), 1)

    @patch("app.mermaid_service.run_engine")
    def test_empty_source_does_not_start_subprocess(
        self,
        mock_run: unittest.mock.MagicMock,
    ) -> None:
        with self.assertRaises(MermaidValidationError):
            render_svg("  \n", config=self.config)

        mock_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()

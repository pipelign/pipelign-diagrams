import os
import shutil
import unittest
from pathlib import Path

from app.mermaid_service import (
    MermaidConfig,
    render_png,
    render_svg,
    validate_diagram,
)


class MermaidIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        config = MermaidConfig.from_env()
        command_available = shutil.which(config.command) is not None
        if os.path.sep in config.command:
            command_available = Path(config.command).is_file()
        if not command_available:
            raise unittest.SkipTest(
                f"Mermaid CLI not found at {config.command}, skipping integration tests."
            )
        cls.config = config

    def setUp(self) -> None:
        self.source = "flowchart LR\nA[Client] --> B[API]"

    def test_render_png_integration(self) -> None:
        output = render_png(self.source, config=self.config)
        self.assertTrue(output.startswith(b"\x89PNG"))

    def test_render_svg_integration(self) -> None:
        output = render_svg(self.source, config=self.config)
        self.assertIn("<svg", output)

    def test_validate_integration(self) -> None:
        result = validate_diagram(self.source, config=self.config)
        self.assertTrue(result.ok)


if __name__ == "__main__":
    unittest.main()

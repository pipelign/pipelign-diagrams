import os
import unittest

from app.plantuml_service import (
    PlantUMLConfig,
    render_ascii,
    render_png,
    render_svg,
    validate_diagram,
)


class PlantUMLIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        """
        Skip these tests automatically if the PlantUML JAR is not available.
        This lets you run unit tests locally without Java, while the
        Dockerised environment will execute them for real.
        """
        config = PlantUMLConfig.from_env()
        if not os.path.exists(config.jar_path):
            raise unittest.SkipTest(
                f"PlantUML JAR not found at {config.jar_path}, "
                "skipping integration tests that require Java.",
            )
        cls.config = config

    def setUp(self) -> None:
        self.source = "@startuml\nAlice -> Bob: Hi\n@enduml"

    def test_render_png_integration(self) -> None:
        png_bytes = render_png(self.source, config=self.config)
        # Basic sanity checks that we got a PNG back.
        self.assertIsInstance(png_bytes, (bytes, bytearray))
        self.assertGreater(len(png_bytes), 0)
        self.assertTrue(png_bytes.startswith(b"\x89PNG"))

    def test_render_svg_integration(self) -> None:
        svg_text = render_svg(self.source, config=self.config)
        self.assertIsInstance(svg_text, str)
        self.assertGreater(len(svg_text.strip()), 0)
        self.assertIn("<svg", svg_text)

    def test_render_graphviz_dependent_diagram(self) -> None:
        source = """@startuml
left to right direction
component "API Gateway" as API
database "Orders" as DB
queue "Domain Events" as Events
API --> DB
API --> Events
@enduml"""

        svg_text = render_svg(source, config=self.config)

        self.assertIn("<svg", svg_text)
        self.assertIn("API Gateway", svg_text)
        self.assertNotIn("Dot executable", svg_text)
        self.assertNotIn("Cannot find Graphviz", svg_text)

    def test_render_ascii_integration(self) -> None:
        ascii_text = render_ascii(self.source, config=self.config)
        self.assertIsInstance(ascii_text, str)
        self.assertGreater(len(ascii_text.strip()), 0)

    def test_validate_diagram_integration(self) -> None:
        result = validate_diagram(self.source, config=self.config)
        self.assertTrue(result.ok)
        self.assertEqual(result.errors, [])


if __name__ == "__main__":
    unittest.main()

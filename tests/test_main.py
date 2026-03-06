import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.models import ValidationIssue, ValidationResult


class TestHealthEndpoint(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_health_ok(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})


class TestRenderEndpoints(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self.sample_source = "@startuml\nAlice -> Bob: Hi\n@enduml"

    def test_render_png_success(self) -> None:
        with patch("app.main.render_png", return_value=b"PNGDATA") as mock_render:
            response = self.client.post(
                "/render/png",
                json={"source": self.sample_source},
            )

        mock_render.assert_called_once_with(self.sample_source)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "image/png")
        self.assertEqual(response.content, b"PNGDATA")

    def test_render_svg_success(self) -> None:
        with patch("app.main.render_svg", return_value="<svg></svg>") as mock_render:
            response = self.client.post(
                "/render/svg",
                json={"source": self.sample_source},
            )

        mock_render.assert_called_once_with(self.sample_source)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            response.headers["content-type"].startswith("image/svg+xml"),
        )
        self.assertEqual(response.text, "<svg></svg>")

    def test_render_ascii_success(self) -> None:
        with patch("app.main.render_ascii", return_value="ASCII") as mock_render:
            response = self.client.post(
                "/render/ascii",
                json={"source": self.sample_source},
            )

        mock_render.assert_called_once_with(self.sample_source)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "text/plain; charset=utf-8")
        self.assertEqual(response.text, "ASCII")


class TestValidateEndpoint(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self.sample_source = "@startuml\nAlice -> Bob: Hi\n@enduml"

    def test_validate_ok(self) -> None:
        result = ValidationResult(ok=True, errors=[], warnings=[])

        with patch("app.main.validate_diagram", return_value=result) as mock_validate:
            response = self.client.post(
                "/validate",
                json={"source": self.sample_source},
            )

        mock_validate.assert_called_once_with(self.sample_source)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"ok": True, "errors": [], "warnings": []},
        )

    def test_validate_invalid_diagram(self) -> None:
        issue = ValidationIssue(message="Syntax Error?", line=5)
        result = ValidationResult(ok=False, errors=[issue], warnings=[])

        with patch("app.main.validate_diagram", return_value=result) as mock_validate:
            response = self.client.post(
                "/validate",
                json={"source": self.sample_source},
            )

        mock_validate.assert_called_once_with(self.sample_source)
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(len(payload["errors"]), 1)
        self.assertEqual(payload["errors"][0]["message"], "Syntax Error?")


class TestBasicStructureValidation(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_validate_rejects_empty_body(self) -> None:
        # This has @startuml and @enduml but no non-empty content between.
        response = self.client.post(
            "/validate",
            json={"source": "@startuml\n@enduml"},
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertGreaterEqual(len(payload["errors"]), 1)
        self.assertIn("@startuml", payload["errors"][0]["message"])


if __name__ == "__main__":
    unittest.main()


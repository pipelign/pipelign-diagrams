import os
import unittest
from unittest.mock import patch

import httpx
from app.errors import RendererInternalError
from app.main import app
from app.models import (
    DiagramLanguage,
    OutputFormat,
    ValidationIssue,
    ValidationResult,
)
from app.renderer import RenderedDiagram


class ApiTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        token_patch = patch.dict(os.environ, {"DIAGRAM_API_TOKEN": "test-token-" * 4})
        token_patch.start()
        self.addCleanup(token_patch.stop)
        manifest_patch = patch(
            "app.main.get_manifest", return_value={"manifest_sha256": "a" * 64}
        )
        manifest_patch.start()
        self.addCleanup(manifest_patch.stop)
        transport = httpx.ASGITransport(app=app)
        self.client = httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
            headers={"Authorization": "Bearer " + "test-token-" * 4},
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()


class TestHealthEndpoint(ApiTestCase):
    async def test_playground_ui(self) -> None:
        response = await self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/html"))
        self.assertIn("pipelign-diagrams playground", response.text)
        self.assertIn('value="plantuml"', response.text)
        self.assertIn('value="mermaid"', response.text)
        self.assertIn('data-format="svg"', response.text)
        self.assertIn('data-format="png"', response.text)
        self.assertIn('id="validate-button"', response.text)

    async def test_health_ok(self) -> None:
        response = await self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})


class TestRenderEndpoints(ApiTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.plantuml_source = "@startuml\nAlice -> Bob: Hi\n@enduml"
        self.mermaid_source = "flowchart LR\nA --> B"

    async def test_render_png_defaults_to_plantuml(self) -> None:
        rendered = RenderedDiagram(b"PNGDATA", "image/png")
        with patch(
            "app.main.diagram_service.render",
            return_value=rendered,
        ) as mock_render:
            response = await self.client.post(
                "/render/png",
                json={"source": self.plantuml_source},
            )

        mock_render.assert_called_once_with(
            DiagramLanguage.PLANTUML,
            self.plantuml_source,
            OutputFormat.PNG,
            None,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "image/png")
        self.assertEqual(response.content, b"PNGDATA")

    async def test_render_svg_routes_mermaid(self) -> None:
        rendered = RenderedDiagram(
            b"<svg></svg>",
            "image/svg+xml; charset=utf-8",
        )
        with patch(
            "app.main.diagram_service.render",
            return_value=rendered,
        ) as mock_render:
            response = await self.client.post(
                "/render/svg",
                json={"language": "mermaid", "source": self.mermaid_source},
            )

        mock_render.assert_called_once_with(
            DiagramLanguage.MERMAID,
            self.mermaid_source,
            OutputFormat.SVG,
            None,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("image/svg+xml"))
        self.assertEqual(response.text, "<svg></svg>")

    async def test_render_ascii_preserves_plantuml_endpoint(self) -> None:
        rendered = RenderedDiagram(b"ASCII", "text/plain; charset=utf-8")
        with patch(
            "app.main.diagram_service.render",
            return_value=rendered,
        ) as mock_render:
            response = await self.client.post(
                "/render/ascii",
                json={"source": self.plantuml_source},
            )

        mock_render.assert_called_once_with(
            DiagramLanguage.PLANTUML,
            self.plantuml_source,
            OutputFormat.ASCII,
            None,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "text/plain; charset=utf-8")
        self.assertEqual(response.text, "ASCII")

    async def test_render_ascii_rejects_mermaid(self) -> None:
        response = await self.client.post(
            "/render/ascii",
            json={"language": "mermaid", "source": self.mermaid_source},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.headers["x-diagram-error"], "validation_failed")
        self.assertIn("not supported", response.json()["errors"][0]["message"])

    async def test_internal_error_does_not_expose_details(self) -> None:
        error = RendererInternalError(
            "command failed at /private/path",
            language=DiagramLanguage.MERMAID,
            details={"stderr": "implementation detail"},
        )
        with patch("app.main.diagram_service.render", side_effect=error):
            response = await self.client.post(
                "/render/svg",
                json={"language": "mermaid", "source": self.mermaid_source},
            )

        self.assertEqual(response.status_code, 500)
        payload = response.json()
        self.assertEqual(payload["message"], "The diagram could not be rendered.")
        self.assertIsNone(payload["details"])
        self.assertNotIn("private", response.text)
        self.assertNotIn("implementation detail", response.text)


class TestValidateEndpoint(ApiTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.sample_source = "flowchart LR\nA --> B"

    async def test_validate_ok(self) -> None:
        result = ValidationResult(ok=True)

        with patch(
            "app.main.diagram_service.validate",
            return_value=result,
        ) as mock_validate:
            response = await self.client.post(
                "/validate",
                json={"language": "mermaid", "source": self.sample_source},
            )

        mock_validate.assert_called_once_with(
            DiagramLanguage.MERMAID,
            self.sample_source,
            None,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "errors": [], "warnings": []})

    async def test_validate_invalid_diagram(self) -> None:
        issue = ValidationIssue(message="Parse error in Mermaid diagram.", line=2)
        result = ValidationResult(ok=False, errors=[issue])

        with patch("app.main.diagram_service.validate", return_value=result):
            response = await self.client.post(
                "/validate",
                json={"language": "mermaid", "source": self.sample_source},
            )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["errors"][0]["line"], 2)
        self.assertEqual(response.headers["x-diagram-error"], "validation_failed")

    async def test_unknown_language_is_rejected_by_request_validation(self) -> None:
        response = await self.client.post(
            "/validate",
            json={"language": "dot", "source": "digraph { a -> b }"},
        )

        self.assertEqual(response.status_code, 422)


class TestBasicStructureValidation(ApiTestCase):
    async def test_validate_rejects_empty_plantuml_body(self) -> None:
        response = await self.client.post(
            "/validate",
            json={"source": "@startuml\n@enduml"},
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertIn("@startuml", payload["errors"][0]["message"])
        self.assertEqual(response.headers["x-plantuml-error"], "validation_failed")


if __name__ == "__main__":
    unittest.main()

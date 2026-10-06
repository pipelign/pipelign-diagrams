import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.limits import MAX_REQUEST_BYTES, MAX_SOURCE_BYTES, RenderPolicyError
from app.process_runner import run_engine
from app.security import render_slot, validate_source

from tests.test_main import ApiTestCase


class TestMachineBoundary(ApiTestCase):
    async def test_requires_auth_for_everything_except_liveness(self):
        self.client.headers.pop("Authorization")
        self.assertEqual((await self.client.get("/health")).status_code, 200)
        for path in (
            "/ready",
            "/",
            "/docs",
            "/openapi.json",
            "/validate",
            "/render/svg",
        ):
            with self.subTest(path=path):
                response = await self.client.get(path)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.headers["cache-control"], "private, no-store")
                self.assertIn("sandbox", response.headers["content-security-policy"])

    async def test_rotation_accepts_current_and_previous_rejects_wrong_and_duplicate(
        self,
    ):
        previous = "previous-token-" * 3
        with patch.dict(os.environ, {"DIAGRAM_API_TOKEN_PREVIOUS": previous}):
            for token, status in (
                (previous, 200),
                ("test-token-" * 4, 200),
                ("wrong", 401),
            ):
                response = await self.client.get(
                    "/openapi.json", headers={"Authorization": "Bearer " + token}
                )
                self.assertEqual(response.status_code, status)
            response = await self.client.get(
                "/ready",
                headers=[
                    ("Authorization", "Bearer " + previous),
                    ("Authorization", "Bearer " + previous),
                ],
            )
            self.assertEqual(response.status_code, 401)

    async def test_missing_or_malformed_configuration_fails_closed(self):
        for token in ("", "short", "x" * 32 + " ", "é" * 32):
            with patch.dict(os.environ, {"DIAGRAM_API_TOKEN": token}):
                response = await self.client.get("/ready")
                self.assertEqual(response.status_code, 503)
                self.assertEqual(
                    response.json()["errorType"], "authentication_unconfigured"
                )

    async def test_schema_failure_does_not_echo_submitted_input(self):
        response = await self.client.post(
            "/render/svg",
            json={"source": "PRIVATE_SOURCE_MARKER", "language": "invalid"},
        )
        self.assertEqual(response.status_code, 422)
        self.assertNotIn("PRIVATE_SOURCE_MARKER", response.text)

    async def test_body_cap_runs_before_json_or_engine(self):
        response = await self.client.post(
            "/render/svg", content=b"x" * (MAX_REQUEST_BYTES + 1)
        )
        self.assertEqual(response.status_code, 413)

    async def test_busy_renderer_is_bounded_and_retryable(self):
        with render_slot():
            response = await self.client.post(
                "/render/svg", json={"source": "@startuml\nA -> B\n@enduml"}
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.headers["retry-after"], "1")

    async def test_readiness_checks_both_engines_once_and_does_not_hide_failure(self):
        import app.main as main
        from app.errors import RendererInternalError

        with (
            patch.object(main, "_engines_ready", False),
            patch.object(
                main.diagram_service,
                "render",
                side_effect=RendererInternalError("private"),
            ),
        ):
            response = await self.client.get("/ready")
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()["errorType"], "engine_unavailable")
            self.assertFalse(main._engines_ready)
        with (
            patch.object(main, "_engines_ready", False),
            patch.object(main.diagram_service, "render") as render,
        ):
            self.assertEqual((await self.client.get("/ready")).status_code, 200)
            self.assertEqual((await self.client.get("/ready")).status_code, 200)
            self.assertEqual(render.call_count, 2)


class TestSourcePolicy(unittest.TestCase):
    def test_forbidden_inputs(self):
        for source in (
            "!include /etc/passwd",
            "!includeurl https://example.com",
            "!theme cerulean",
            '%getenv("SECRET")',
            '%load_json("/etc/passwd")',
            "[[target]]",
            '<img src="file:///etc/passwd">',
            "click A callback",
            '%%{init: {securityLevel: "loose"}}%%',
            "---\nconfig: x",
            "\ufeff \v\ufeff\n---\nconfig: {securityLevel: loose}\n---\nflowchart LR\nA --> B",
        ):
            with self.subTest(source=source), self.assertRaises(RenderPolicyError):
                validate_source(source, None)

    def test_title_only_frontmatter(self):
        for title in ("Request flow", 'API: "quoted" response', "Café → API"):
            source = (
                "---\ntitle: "
                + json.dumps(title, ensure_ascii=False)
                + "\n---\nflowchart LR\nA --> B"
            )
            with self.subTest(title=title):
                validate_source(source, None)
                validate_source("\ufeff  " + source.replace("\n", "\r\n"), None)

    def test_title_metadata_cannot_override_configuration(self):
        for metadata in (
            'title: "Flow"\nconfig: {securityLevel: loose}',
            'config: {securityLevel: loose}\ntitle: "Flow"',
            'title: "Flow"\ntitle: "Duplicate"',
            "title: {config: unsafe}",
            'title: &title "Flow"',
            "title: *title",
            'title: !!str "Flow"',
            "title: |\n  Flow\nconfig: unsafe",
            'title: "Flow\nconfig: unsafe"',
            'title: "Flow" # comment',
            'title: ""',
            "title: " + json.dumps("x" * 256),
            'title: "unterminated',
            r'title: "bad\qescape"',
        ):
            source = "---\n" + metadata + "\n---\nflowchart LR\nA --> B"
            with self.subTest(metadata=metadata), self.assertRaises(RenderPolicyError):
                validate_source(source, None)

    def test_title_does_not_relax_source_or_option_policy(self):
        source = '---\ntitle: "Flow"\n---\nflowchart LR\nA --> B'
        for suffix, options in (("\nclick A callback", None), ("", {"theme": "dark"})):
            with (
                self.subTest(suffix=suffix, options=options),
                self.assertRaises(RenderPolicyError),
            ):
                validate_source(source + suffix, options)

    def test_size_unicode_and_options(self):
        for source, options, code in [
            ("é" * MAX_SOURCE_BYTES, None, "source_too_large"),
            ("\ud800", None, "invalid_request"),
            (
                "flowchart LR\nA --> B",
                {"securityLevel": "loose"},
                "unsupported_options",
            ),
        ]:
            with self.assertRaises(RenderPolicyError) as exc:
                validate_source(source, options)
            self.assertEqual(exc.exception.code, code)


@unittest.skipUnless(
    Path("/app/renderer-manifest.json").is_file(), "requires the hardened Linux image"
)
class TestRealProcessIsolation(unittest.TestCase):
    def execute(self, code, **kwargs):
        return run_engine([sys.executable, "-c", code], **kwargs)

    def test_private_pid_network_and_environment(self):
        result = self.execute("""import json,os,socket
from pathlib import Path
s=socket.socket(); s.settimeout(.2)
try: s.connect(('1.1.1.1',443)); reachable=True
except OSError: reachable=False
print(json.dumps({'pid':os.getpid(),'interfaces':socket.if_nameindex(),'reachable':reachable,'token_present':any('TOKEN' in k for k in os.environ),'processes':sorted(p.name for p in Path('/proc').iterdir() if p.name.isdigit()),'capabilities':[l.strip() for l in Path('/proc/self/status').read_text().splitlines() if l.startswith(('CapEff:','CapPrm:','CapInh:','CapAmb:'))]}))""")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["pid"], 1)
        self.assertEqual(data["processes"], ["1"])
        self.assertEqual([i[1] for i in data["interfaces"]], ["lo"])
        self.assertFalse(data["reachable"])
        self.assertFalse(data["token_present"])
        self.assertTrue(
            all(line.endswith("0000000000000000") for line in data["capabilities"])
        )

    def test_timeout_output_caps_cleanup_and_detached_descendants(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = str(Path(directory, "escaped"))
            child = (
                "import time; from pathlib import Path; time.sleep(1); Path("
                + repr(marker)
                + ").touch()"
            )
            code = (
                'import subprocess,sys,time; subprocess.Popen([sys.executable,"-c",'
                + repr(child)
                + "],start_new_session=True); time.sleep(5)"
            )
            before = set(Path("/tmp").glob("diagram-engine-*"))
            with self.assertRaises(RenderPolicyError) as exc:
                self.execute(code, timeout=0.3)
            self.assertEqual(exc.exception.code, "engine_timeout")
            import time

            time.sleep(1.2)
            self.assertFalse(Path(marker).exists())
            self.assertEqual(before, set(Path("/tmp").glob("diagram-engine-*")))
        for stream, length in [
            ("stdout", 4 * 1024 * 1024 + 1),
            ("stderr", 16 * 1024 + 1),
        ]:
            with self.assertRaises(RenderPolicyError) as exc:
                self.execute(f'import sys; sys.{stream}.buffer.write(b"x" * {length})')
            self.assertEqual(exc.exception.code, "resource_limit")
        self.assertEqual(
            self.execute('print("recovered")').stdout.strip(), b"recovered"
        )


@unittest.skipUnless(
    Path("/app/renderer-manifest.json").is_file(), "requires the hardened Linux image"
)
class TestEnginePolicies(unittest.TestCase):
    def test_plantuml_cannot_include_a_local_file_even_bypassing_source_filter(self):
        from app.plantuml_service import PlantUMLValidationError, render_svg

        with tempfile.TemporaryDirectory() as directory:
            secret = Path(directory, "private.puml")
            secret.write_text("Alice -> Bob: PRIVATE_INCLUDE_MARKER")
            with self.assertRaises(PlantUMLValidationError):
                render_svg("@startuml\n!include " + str(secret) + "\n@enduml")

    def test_mermaid_frontmatter_title_is_visible_svg_text(self):
        from app.mermaid_service import render_svg
        from xml.etree import ElementTree

        source = '---\ntitle: "Request flow"\n---\nflowchart LR\nA --> B'
        validate_source(source, None)
        svg = ElementTree.fromstring(render_svg(source))
        texts = [
            "".join(node.itertext())
            for node in svg.iter("{http://www.w3.org/2000/svg}text")
        ]
        self.assertIn("Request flow", texts)

    def test_mermaid_emits_svg_text_without_foreign_html(self):
        from app.mermaid_service import render_svg

        content = render_svg('flowchart LR\nA["<b>Client</b>"] --> B[API]')
        self.assertNotIn("<foreignObject", content)
        self.assertNotIn("<script", content)
        self.assertIn("<text", content)

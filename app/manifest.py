"""Build-time engine/font identity and runtime engine readiness."""

import json
import subprocess
import sys
from functools import lru_cache
from hashlib import sha256
from pathlib import Path

from .limits import POLICY_VERSION, RenderPolicyError

MANIFEST_PATH = Path("/app/renderer-manifest.json")


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


@lru_cache(maxsize=1)
def get_manifest():
    try:
        manifest = json.loads(MANIFEST_PATH.read_bytes())
        expected = manifest.pop("manifest_sha256")
        if sha256(canonical_json(manifest)).hexdigest() != expected:
            raise ValueError
        manifest["manifest_sha256"] = expected
        if manifest["policy_version"] != POLICY_VERSION:
            raise ValueError
        return manifest
    except (OSError, ValueError, KeyError):
        raise RenderPolicyError(
            "engine_unavailable", "Renderer build metadata is unavailable.", 503
        ) from None


def _version(*command):
    result = subprocess.run(
        command, capture_output=True, text=True, check=True, timeout=10
    )
    return (result.stdout or result.stderr).strip()


def build_manifest():
    cli_root = Path("/opt/mermaid-cli/lib/node_modules/@mermaid-js/mermaid-cli")
    fonts = sorted(set(_version("fc-list", "--format", "%{file}\n").splitlines()))
    font_files = {name: sha256(Path(name).read_bytes()).hexdigest() for name in fonts}
    source_files = sorted(Path("/app/app").glob("*.py")) + sorted(
        Path("/app/mermaid").glob("*.json")
    )
    source_hashes = {
        str(path.relative_to("/app")): sha256(path.read_bytes()).hexdigest()
        for path in source_files
    }
    manifest = {
        "contract_version": 1,
        "service_version": "2.2.0",
        "policy_version": POLICY_VERSION,
        "source_sha256": sha256(canonical_json(source_hashes)).hexdigest(),
        "engines": {
            "plantuml": _version(
                "java", "-jar", "/app/plantuml/plantuml.jar", "-version"
            ).splitlines()[0],
            "plantuml_jar_sha256": sha256(
                Path("/app/plantuml/plantuml.jar").read_bytes()
            ).hexdigest(),
            "mermaid_cli": json.loads((cli_root / "package.json").read_bytes())[
                "version"
            ],
            "mermaid": json.loads(
                (cli_root / "node_modules/mermaid/package.json").read_bytes()
            )["version"],
            "chromium": _version("chromium", "--version"),
            "graphviz": _version("dot", "-V"),
            "java": _version("java", "-version"),
            "node": _version("node", "--version"),
            "python": sys.version.split()[0],
        },
        "fonts": font_files,
        "fonts_sha256": sha256(canonical_json(font_files)).hexdigest(),
        "system_packages_sha256": sha256(
            _version("dpkg-query", "-W").encode()
        ).hexdigest(),
        "effective_options": {
            "execution_boundary": "container",
            "puppeteer": json.loads(
                Path("/app/mermaid/puppeteer-config.json").read_bytes()
            ),
            "plantuml_security_profile": "SANDBOX",
            "mermaid": json.loads(
                Path("/app/mermaid/mermaid-config.json").read_bytes()
            ),
        },
    }
    manifest["manifest_sha256"] = sha256(canonical_json(manifest)).hexdigest()
    MANIFEST_PATH.write_bytes(canonical_json(manifest))


if __name__ == "__main__":
    build_manifest()

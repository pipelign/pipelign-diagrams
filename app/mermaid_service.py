"""Server-side Mermaid rendering through the official Mermaid CLI."""

from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import DiagramValidationError, RendererInternalError
from .limits import MAX_OUTPUT_BYTES, RenderPolicyError
from .logging_config import configure_logging
from .models import (
    DiagramLanguage,
    OutputFormat,
    ValidationIssue,
    ValidationResult,
)
from .process_runner import run_engine
from .renderer import DiagramRenderer, RenderedDiagram

configure_logging()
logger = logging.getLogger(__name__)


class MermaidValidationError(DiagramValidationError):
    """Raised when Mermaid reports invalid diagram source."""

    def __init__(self, result: ValidationResult) -> None:
        super().__init__(result, language=DiagramLanguage.MERMAID)


class MermaidInternalError(RendererInternalError):
    """Raised when Mermaid CLI cannot render for an internal reason."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message,
            language=DiagramLanguage.MERMAID,
            details=details,
            public_message="The Mermaid renderer could not process the diagram.",
        )


@dataclass(frozen=True)
class MermaidConfig:
    """Runtime configuration for invoking Mermaid CLI."""

    command: str
    timeout_seconds: float
    puppeteer_config_path: str | None

    @classmethod
    def from_env(cls) -> MermaidConfig:
        command = os.getenv("MERMAID_CMD", "mmdc")
        timeout_raw = os.getenv("MERMAID_TIMEOUT_SECONDS", "20")
        try:
            timeout_seconds = float(timeout_raw)
        except ValueError:
            timeout_seconds = 20.0

        configured_path = os.getenv("MERMAID_PUPPETEER_CONFIG_PATH")
        if configured_path:
            puppeteer_config_path = configured_path
        else:
            container_default = Path("/app/mermaid/puppeteer-config.json")
            puppeteer_config_path = (
                str(container_default) if container_default.is_file() else None
            )

        return cls(
            command=command,
            timeout_seconds=timeout_seconds,
            puppeteer_config_path=puppeteer_config_path,
        )


_ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_LINE_NUMBER = re.compile(r"(?:parse|lexical) error on line\s+(\d+)", re.IGNORECASE)


def _parse_validation_output(stderr_text: str) -> ValidationResult | None:
    """Return a sanitized validation result when stderr describes bad source."""
    normalized = _ANSI_ESCAPE.sub("", stderr_text)
    lowered = normalized.lower()

    if "no diagram type detected" in lowered or "unknowndiagramerror" in lowered:
        issue = ValidationIssue(
            message="No supported Mermaid diagram type was detected.",
        )
        return ValidationResult(ok=False, errors=[issue])

    validation_markers = (
        "parse error",
        "lexical error",
        "syntax error in text",
        "error parsing mermaid diagram",
    )
    if not any(marker in lowered for marker in validation_markers):
        return None

    line_match = _LINE_NUMBER.search(normalized)
    line = int(line_match.group(1)) if line_match else None
    if "lexical error" in lowered:
        message = "Lexical error in Mermaid diagram."
    else:
        message = "Parse error in Mermaid diagram."

    issue = ValidationIssue(message=message, line=line)
    return ValidationResult(ok=False, errors=[issue])


def _run_mermaid(
    source: str,
    output_format: OutputFormat,
    *,
    config: MermaidConfig | None = None,
) -> bytes:
    if config is None:
        config = MermaidConfig.from_env()

    if not source.strip():
        raise MermaidValidationError(
            ValidationResult(
                ok=False,
                errors=[ValidationIssue(message="Diagram source must not be empty.")],
            )
        )

    with tempfile.TemporaryDirectory(prefix="pipelign-diagrams-") as temp_dir:
        input_path = Path(temp_dir, "diagram.mmd")
        output_path = Path(temp_dir, f"diagram.{output_format.value}")
        input_path.write_text(source, encoding="utf-8")

        command = [
            config.command,
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--quiet",
            "--configFile",
            "/app/mermaid/mermaid-config.json",
        ]
        if config.puppeteer_config_path:
            command.extend(["--puppeteerConfigFile", config.puppeteer_config_path])

        logger.info(
            "Starting Mermaid subprocess",
            extra={
                "timeoutSeconds": config.timeout_seconds,
                "outputFormat": output_format.value,
                "sourceLength": len(source),
            },
        )
        try:
            completed = run_engine(
                command,
                cwd=temp_dir,
                timeout=config.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise MermaidInternalError(
                "Mermaid subprocess timed out",
                details={"timeoutSeconds": config.timeout_seconds},
            ) from exc
        except OSError as exc:
            raise MermaidInternalError(
                "Failed to start Mermaid subprocess",
                details={"error": str(exc)},
            ) from exc

        logger.info(
            "Mermaid subprocess finished with return code %s",
            completed.returncode,
        )
        if completed.returncode != 0:
            result = _parse_validation_output(
                (completed.stderr or completed.stdout or b"").decode(
                    "utf-8", errors="replace"
                )
            )
            if result is not None:
                raise MermaidValidationError(result)
            raise MermaidInternalError(
                "Mermaid failed with a non-zero exit code",
                details={"returnCode": completed.returncode},
            )

        try:
            with output_path.open("rb") as output:
                content = output.read(MAX_OUTPUT_BYTES + 1)
            if len(content) > MAX_OUTPUT_BYTES:
                raise RenderPolicyError(
                    "resource_limit", "Rendering exceeded the output limit.", 413
                )
            return content
        except OSError as exc:
            raise MermaidInternalError(
                "Mermaid returned no rendered output",
                details={"error": str(exc)},
            ) from exc


def render_png(source: str, *, config: MermaidConfig | None = None) -> bytes:
    return _run_mermaid(source, OutputFormat.PNG, config=config)


def render_svg(source: str, *, config: MermaidConfig | None = None) -> str:
    output = _run_mermaid(source, OutputFormat.SVG, config=config)
    try:
        return output.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MermaidInternalError("Mermaid returned invalid SVG data") from exc


def validate_diagram(
    source: str,
    *,
    config: MermaidConfig | None = None,
) -> ValidationResult:
    try:
        _run_mermaid(source, OutputFormat.SVG, config=config)
    except MermaidValidationError as exc:
        return exc.result
    return ValidationResult(ok=True)


class MermaidRenderer(DiagramRenderer):
    """Generic renderer adapter for Mermaid CLI."""

    language = DiagramLanguage.MERMAID
    supported_formats = frozenset({OutputFormat.PNG, OutputFormat.SVG})

    def render(
        self,
        source: str,
        output_format: OutputFormat,
        options: Mapping[str, Any] | None = None,
    ) -> RenderedDiagram:
        del options  # Reserved by the public API for future renderer options.
        if output_format == OutputFormat.PNG:
            return RenderedDiagram(render_png(source), "image/png")
        if output_format == OutputFormat.SVG:
            return RenderedDiagram(
                render_svg(source).encode("utf-8"),
                "image/svg+xml; charset=utf-8",
            )
        raise ValueError(f"Unsupported Mermaid output format: {output_format.value}")

    def validate(
        self,
        source: str,
        options: Mapping[str, Any] | None = None,
    ) -> ValidationResult:
        del options
        return validate_diagram(source)

from __future__ import annotations

"""
Integration layer between the FastAPI application and the PlantUML CLI.

This module is responsible for:

* Reading configuration (JAR path, timeouts, Java command) from the environment.
* Performing a lightweight structural validation of incoming diagrams before
  invoking PlantUML.
* Spawning and supervising the ``java`` subprocess that runs ``plantuml.jar``.
* Translating PlantUML exit codes and stderr output into strongly-typed
  ``ValidationResult`` instances or rich exceptions that the API layer can
  convert into HTTP responses.
"""

import logging
import os
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .errors import DiagramValidationError, RendererInternalError
from .logging_config import configure_logging
from .models import DiagramLanguage, OutputFormat, ValidationIssue, ValidationResult
from .renderer import DiagramRenderer, RenderedDiagram

configure_logging()
logger = logging.getLogger(__name__)


class PlantUMLValidationError(DiagramValidationError):
    """Raised when PlantUML reports a validation error for the given source."""

    def __init__(self, result: ValidationResult) -> None:
        super().__init__(result, language=DiagramLanguage.PLANTUML)


class PlantUMLInternalError(RendererInternalError):
    """Raised when PlantUML fails for internal or unexpected reasons."""

    def __init__(
        self,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            language=DiagramLanguage.PLANTUML,
            details=details,
            public_message="The PlantUML renderer could not process the diagram.",
        )


@dataclass
class PlantUMLConfig:
    """Runtime configuration for invoking the PlantUML JAR."""

    jar_path: str
    timeout_seconds: float

    @classmethod
    def from_env(cls) -> PlantUMLConfig:
        """
        Build a ``PlantUMLConfig`` from environment variables.

        Environment variables:

        * ``PLANTUML_JAR_PATH`` - filesystem path to ``plantuml.jar``.
        * ``PLANTUML_TIMEOUT_SECONDS`` - maximum run time for the subprocess.
        """
        jar_path = os.getenv("PLANTUML_JAR_PATH", "/app/plantuml/plantuml.jar")
        timeout_raw = os.getenv("PLANTUML_TIMEOUT_SECONDS", "20")
        try:
            timeout_seconds = float(timeout_raw)
        except ValueError:
            timeout_seconds = 20.0
        return cls(jar_path=jar_path, timeout_seconds=timeout_seconds)


def _ensure_basic_uml_structure(source: str) -> None:
    """
    Perform a quick structural sanity check before invoking PlantUML.

    We require:
      - first non-empty line:  @startuml
      - last non-empty line:   @enduml
      - at least one non-empty line in between
    """
    lines = [line for line in source.splitlines()]
    # Strip leading/trailing completely empty lines for robustness.
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()

    ok = True
    if len(lines) < 3:
        ok = False
    else:
        first = lines[0].strip()
        last = lines[-1].strip()
        middle_non_empty = any(line.strip() for line in lines[1:-1])
        if first != "@startuml" or last != "@enduml" or not middle_non_empty:
            ok = False

    if ok:
        return

    logger.warning(
        "Basic UML structure validation failed",
        extra={"sourcePreview": source[:200]},
    )
    issue = ValidationIssue(
        message=(
            "Diagram must start with '@startuml', end with '@enduml', "
            "and contain non-empty content between them."
        ),
        line=None,
    )
    result = ValidationResult(ok=False, errors=[issue], warnings=[])
    raise PlantUMLValidationError(result)


def _build_base_command(config: PlantUMLConfig) -> list[str]:
    """Return the base ``java`` command used for all PlantUML invocations."""
    java_cmd = os.getenv("JAVA_CMD", "java")
    return [
        java_cmd,
        "-jar",
        config.jar_path,
        "-pipeNoStderr",
    ]


def _run_plantuml(
    args: Sequence[str],
    source: str,
    *,
    capture_binary: bool,
    config: PlantUMLConfig | None = None,
) -> subprocess.CompletedProcess:
    """
    Invoke the PlantUML subprocess with the given arguments and source.

    The ``capture_binary`` flag controls whether stdout/stderr are captured
    as bytes (for PNG and some syntax-check modes) or decoded text. Any
    low-level subprocess failures are normalised into ``PlantUMLInternalError``.
    """
    if config is None:
        config = PlantUMLConfig.from_env()

    if not os.path.exists(config.jar_path):
        logger.error("PlantUML JAR not found at '%s'", config.jar_path)
        raise PlantUMLInternalError(
            "PlantUML JAR not found",
            details={"jarPath": config.jar_path},
        )

    cmd = _build_base_command(config) + list(args)

    logger.debug("PlantUML command: %s", cmd)

    # Log the exact source being sent, truncated to avoid overly large log entries.
    max_preview = 5000
    preview = (
        source
        if len(source) <= max_preview
        else source[:max_preview] + "... [truncated]"
    )
    logger.debug("PlantUML source (%d chars):\n%s", len(source), preview)

    logger.info(
        "Starting PlantUML subprocess",
        extra={
            "jarPath": config.jar_path,
            "timeoutSeconds": config.timeout_seconds,
            "plantumlArgs": list(args),
            "sourceLength": len(source),
            "captureBinary": capture_binary,
        },
    )

    try:
        completed = subprocess.run(
            cmd,
            input=source.encode("utf-8") if capture_binary else source,
            capture_output=True,
            text=not capture_binary,
            timeout=config.timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        logger.error(
            "PlantUML subprocess timed out after %s seconds",
            config.timeout_seconds,
            extra={"cmd": cmd},
        )
        raise PlantUMLInternalError(
            "PlantUML subprocess timed out",
            details={"timeoutSeconds": config.timeout_seconds, "cmd": cmd},
        ) from exc
    except OSError as exc:
        logger.exception(
            "Failed to start PlantUML subprocess",
            extra={"cmd": cmd},
        )
        raise PlantUMLInternalError(
            "Failed to start PlantUML subprocess",
            details={"cmd": cmd, "error": str(exc)},
        ) from exc

    logger.info(
        "PlantUML subprocess finished with return code %s",
        completed.returncode,
    )

    return completed


def _parse_validation_output(stderr_text: str) -> ValidationResult:
    """
    Parse PlantUML stderr/stdout when running in pipe mode with -pipeNoStderr.

    Typical syntax error output looks like:
        ERROR
        5
        Syntax Error?
    """

    lines = [line.strip() for line in stderr_text.splitlines() if line.strip()]
    errors: list[ValidationIssue] = []

    i = 0
    while i < len(lines):
        if lines[i].upper() == "ERROR" and i + 2 < len(lines):
            line_number_text = lines[i + 1]
            message_text = lines[i + 2]
            try:
                line_number = int(line_number_text)
            except ValueError:
                line_number = None
            errors.append(
                ValidationIssue(
                    message=message_text,
                    line=line_number,
                )
            )
            i += 3
        else:
            # Fallback: treat line as a generic error message.
            errors.append(
                ValidationIssue(
                    message=lines[i],
                    line=None,
                )
            )
            i += 1

    if not errors:
        return ValidationResult(ok=True, errors=[], warnings=[])

    return ValidationResult(ok=False, errors=errors, warnings=[])


def _classify_and_raise_on_failure(
    completed: subprocess.CompletedProcess,
    *,
    treat_as_validation: bool,
) -> None:
    if completed.returncode == 0:
        logger.debug("PlantUML completed successfully")
        return

    stderr_text = ""
    # completed.stderr may be bytes or str depending on text flag.
    if isinstance(completed.stderr, bytes):
        stderr_text = completed.stderr.decode("utf-8", errors="replace")
    elif isinstance(completed.stderr, str):
        stderr_text = completed.stderr

    if treat_as_validation:
        result = _parse_validation_output(stderr_text or "")
        if not result.ok:
            logger.warning(
                "PlantUML validation error detected",
                extra={
                    "returnCode": completed.returncode,
                    "stderr": stderr_text,
                    "errorCount": len(result.errors),
                },
            )
            raise PlantUMLValidationError(result)

    logger.error(
        "PlantUML failed with non-zero exit code",
        extra={
            "returnCode": completed.returncode,
            "stderr": stderr_text,
        },
    )
    raise PlantUMLInternalError(
        "PlantUML failed with non-zero exit code",
        details={
            "returnCode": completed.returncode,
            "stderr": stderr_text,
        },
    )


def render_png(source: str, *, config: PlantUMLConfig | None = None) -> bytes:
    """
    Render the given PlantUML diagram to PNG bytes.

    Raises:
        PlantUMLValidationError: if PlantUML reports syntax errors.
        PlantUMLInternalError: for unexpected subprocess failures.
    """
    _ensure_basic_uml_structure(source)
    completed = _run_plantuml(
        ["-tpng", "-pipe"],
        source,
        capture_binary=True,
        config=config,
    )
    _classify_and_raise_on_failure(completed, treat_as_validation=True)
    if completed.stdout is None:
        raise PlantUMLInternalError("PlantUML returned no PNG data")
    return completed.stdout  # type: ignore[return-value]


def render_svg(source: str, *, config: PlantUMLConfig | None = None) -> str:
    """
    Render the given PlantUML diagram to an SVG XML string.

    The diagram is first structurally validated, then passed to PlantUML.
    """
    _ensure_basic_uml_structure(source)
    completed = _run_plantuml(
        ["-tsvg", "-pipe"],
        source,
        capture_binary=False,
        config=config,
    )
    _classify_and_raise_on_failure(completed, treat_as_validation=True)
    if not isinstance(completed.stdout, str):
        raise PlantUMLInternalError("PlantUML returned no SVG data")
    return completed.stdout


def render_ascii(source: str, *, config: PlantUMLConfig | None = None) -> str:
    """
    Render the given PlantUML diagram to an ASCII art representation.

    Useful for debugging or environments where image formats are inconvenient.
    """
    _ensure_basic_uml_structure(source)
    completed = _run_plantuml(
        ["-ttxt", "-pipe"],
        source,
        capture_binary=False,
        config=config,
    )
    _classify_and_raise_on_failure(completed, treat_as_validation=True)
    if not isinstance(completed.stdout, str):
        raise PlantUMLInternalError("PlantUML returned no ASCII data")
    return completed.stdout


def validate_diagram(
    source: str, *, config: PlantUMLConfig | None = None
) -> ValidationResult:
    """
    Validate the given PlantUML diagram using PlantUML's syntax checker.

    Returns a ``ValidationResult`` that mirrors the error information produced
    by PlantUML. A completely valid diagram yields ``ok=True`` with empty
    ``errors`` and ``warnings`` lists.
    """
    _ensure_basic_uml_structure(source)
    # Use capture_binary=True so subprocess does not decode stdout as UTF-8.
    # Some PlantUML versions write binary (e.g. PNG) to stdout for -check-syntax;
    # we only need return code and stderr for validation.
    completed = _run_plantuml(
        ["-check-syntax", "-pipe"],
        source,
        capture_binary=True,
        config=config,
    )

    if completed.returncode == 0:
        return ValidationResult(ok=True, errors=[], warnings=[])

    stderr_text = ""
    if isinstance(completed.stderr, bytes):
        stderr_text = completed.stderr.decode("utf-8", errors="replace")
    elif isinstance(completed.stderr, str):
        stderr_text = completed.stderr

    result = _parse_validation_output(stderr_text or "")
    if result.ok:
        # If parsing failed to detect any explicit validation error, surface as internal.
        raise PlantUMLInternalError(
            "PlantUML validation failed but no errors were parsed",
            details={
                "returnCode": completed.returncode,
                "stderr": stderr_text,
            },
        )
    return result


class PlantUMLRenderer(DiagramRenderer):
    """Generic renderer adapter for the existing PlantUML integration."""

    language = DiagramLanguage.PLANTUML
    supported_formats = frozenset(
        {OutputFormat.PNG, OutputFormat.SVG, OutputFormat.ASCII}
    )

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
        if output_format == OutputFormat.ASCII:
            return RenderedDiagram(
                render_ascii(source).encode("utf-8"),
                "text/plain; charset=utf-8",
            )
        raise ValueError(f"Unsupported PlantUML output format: {output_format.value}")

    def validate(
        self,
        source: str,
        options: Mapping[str, Any] | None = None,
    ) -> ValidationResult:
        del options
        return validate_diagram(source)

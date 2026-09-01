from __future__ import annotations

"""FastAPI application for language-agnostic diagram rendering."""

import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse

from .diagram_service import diagram_service
from .errors import DiagramValidationError, RendererInternalError
from .logging_config import configure_logging
from .models import (
    DiagramLanguage,
    InternalErrorResponse,
    OutputFormat,
    RenderRequest,
    ValidationResult,
)

configure_logging()
logger = logging.getLogger(__name__)
UI_PATH = Path(__file__).with_name("static") / "index.html"

app = FastAPI(
    title="pipelign-diagrams",
    version="2.0.0",
    description="Render and validate PlantUML and Mermaid diagrams.",
)


@app.get("/", include_in_schema=False)
async def test_ui() -> FileResponse:
    """Serve the lightweight browser UI for exercising the rendering API."""
    return FileResponse(UI_PATH, media_type="text/html")


def _error_headers(error_type: str, language: DiagramLanguage | None) -> dict[str, str]:
    headers = {"X-Diagram-Error": error_type}
    if language == DiagramLanguage.PLANTUML:
        # Retained for compatibility with existing PlantUML API consumers.
        headers["X-PlantUML-Error"] = error_type
    return headers


@app.exception_handler(DiagramValidationError)
async def diagram_validation_error_handler(
    request: Request,
    exc: DiagramValidationError,
) -> JSONResponse:
    logger.warning(
        "Diagram validation error for request %s %s",
        request.method,
        request.url.path,
        extra={"language": exc.language.value if exc.language else None},
    )
    return JSONResponse(
        status_code=400,
        content=exc.result.model_dump(),
        headers=_error_headers("validation_failed", exc.language),
    )


@app.exception_handler(RendererInternalError)
async def renderer_internal_error_handler(
    request: Request,
    exc: RendererInternalError,
) -> JSONResponse:
    logger.error(
        "Renderer error for request %s %s: %s",
        request.method,
        request.url.path,
        exc.message,
        extra={
            "details": exc.details,
            "language": exc.language.value if exc.language else None,
        },
    )
    payload = InternalErrorResponse(message=exc.public_message)
    return JSONResponse(
        status_code=500,
        content=payload.model_dump(),
        headers=_error_headers("internal_error", exc.language),
    )


@app.get("/health")
async def health() -> dict[str, str]:
    """Lightweight liveness endpoint used for container and uptime checks."""
    return {"status": "ok"}


def _render(body: RenderRequest, output_format: OutputFormat) -> Response:
    logger.info(
        "Render requested (language=%s, format=%s, sourceLength=%d)",
        body.language.value,
        output_format.value,
        len(body.source),
    )
    rendered = diagram_service.render(
        body.language,
        body.source,
        output_format,
        body.options,
    )
    return Response(content=rendered.content, media_type=rendered.media_type)


@app.post(
    "/render/png",
    responses={
        200: {"content": {"image/png": {}}},
        400: {"description": "Validation error", "model": ValidationResult},
        500: {"description": "Renderer error", "model": InternalErrorResponse},
    },
)
def render_png_endpoint(body: RenderRequest) -> Response:
    """Render a PlantUML or Mermaid diagram to PNG."""
    return _render(body, OutputFormat.PNG)


@app.post(
    "/render/svg",
    responses={
        200: {"content": {"image/svg+xml": {}}},
        400: {"description": "Validation error", "model": ValidationResult},
        500: {"description": "Renderer error", "model": InternalErrorResponse},
    },
)
def render_svg_endpoint(body: RenderRequest) -> Response:
    """Render a PlantUML or Mermaid diagram to SVG."""
    return _render(body, OutputFormat.SVG)


@app.post(
    "/render/ascii",
    responses={
        200: {"content": {"text/plain": {}}},
        400: {"description": "Validation error", "model": ValidationResult},
        500: {"description": "Renderer error", "model": InternalErrorResponse},
    },
)
def render_ascii_endpoint(body: RenderRequest) -> Response:
    """Render a PlantUML diagram to ASCII; Mermaid does not support this format."""
    return _render(body, OutputFormat.ASCII)


@app.post(
    "/validate",
    response_model=ValidationResult,
    responses={
        200: {"description": "Diagram is valid"},
        400: {"description": "Diagram is invalid", "model": ValidationResult},
        500: {"description": "Renderer error", "model": InternalErrorResponse},
    },
)
def validate_endpoint(body: RenderRequest) -> Any:
    """Validate a PlantUML or Mermaid diagram without returning an image."""
    logger.info(
        "Validate requested (language=%s, sourceLength=%d)",
        body.language.value,
        len(body.source),
    )
    result = diagram_service.validate(body.language, body.source, body.options)
    if result.ok:
        return result
    return JSONResponse(
        status_code=400,
        content=result.model_dump(),
        headers=_error_headers("validation_failed", body.language),
    )

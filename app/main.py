from __future__ import annotations

"""
FastAPI application exposing HTTP endpoints for PlantUML validation and rendering.

The module wires together the HTTP layer (FastAPI), domain models, and the
PlantUML subprocess integration implemented in ``plantuml_service``. It also
configures structured logging and centralises error handling so that callers
always receive predictable JSON payloads.
"""

import logging
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse

from .logging_config import configure_logging
from .models import (
    InternalErrorResponse,
    RenderRequest,
    ValidationResult,
)
from .plantuml_service import (
    PlantUMLInternalError,
    PlantUMLValidationError,
    render_ascii,
    render_png,
    render_svg,
    validate_diagram,
)

configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="PlantUML Renderer", version="1.0.0")


@app.exception_handler(PlantUMLValidationError)
async def plantuml_validation_error_handler(
    request: Request, exc: PlantUMLValidationError
) -> JSONResponse:
    """Translate structured PlantUML validation failures into a 400 response."""
    logger.warning(
        "PlantUML validation error for request %s %s",
        request.method,
        request.url.path,
    )
    return JSONResponse(
        status_code=400,
        content=exc.result.model_dump(),
        headers={"X-PlantUML-Error": "validation_failed"},
    )


@app.exception_handler(PlantUMLInternalError)
async def plantuml_internal_error_handler(
    request: Request, exc: PlantUMLInternalError
) -> JSONResponse:
    """Translate unexpected PlantUML or subprocess failures into a 500 response."""
    logger.error(
        "PlantUML internal error for request %s %s: %s",
        request.method,
        request.url.path,
        exc.message,
        extra={"details": exc.details},
    )
    payload = InternalErrorResponse(
        message=exc.message,
        details=exc.details if exc.details else None,
    )
    return JSONResponse(
        status_code=500,
        content=payload.model_dump(),
        headers={"X-PlantUML-Error": "internal_error"},
    )


@app.get("/health")
async def health() -> dict[str, str]:
    """Lightweight liveness endpoint used for container and uptime checks."""
    logger.debug("Health check requested")
    return {"status": "ok"}


@app.post(
    "/render/png",
    responses={
        200: {"content": {"image/png": {}}},
        400: {"description": "Validation error", "model": ValidationResult},
        500: {"description": "Internal error", "model": InternalErrorResponse},
    },
)
async def render_png_endpoint(body: RenderRequest) -> Response:
    """
    Render a PlantUML diagram to PNG.

    The request is first structurally validated, then passed through the
    PlantUML subprocess. On success, raw PNG bytes are returned with the
    appropriate ``image/png`` content type.
    """
    logger.info(
        "Render PNG requested (sourceLength=%d)",
        len(body.source),
    )
    png_bytes = render_png(body.source)
    return Response(content=png_bytes, media_type="image/png")


@app.post(
    "/render/svg",
    responses={
        200: {"content": {"image/svg+xml": {}}},
        400: {"description": "Validation error", "model": ValidationResult},
        500: {"description": "Internal error", "model": InternalErrorResponse},
    },
)
async def render_svg_endpoint(body: RenderRequest) -> Response:
    """
    Render a PlantUML diagram to SVG.

    Returns the SVG document as UTF-8 encoded text with an
    ``image/svg+xml`` media type.
    """
    logger.info(
        "Render SVG requested (sourceLength=%d)",
        len(body.source),
    )
    svg_text = render_svg(body.source)
    return Response(content=svg_text, media_type="image/svg+xml; charset=utf-8")


@app.post(
    "/render/ascii",
    responses={
        200: {"content": {"text/plain": {}}},
        400: {"description": "Validation error", "model": ValidationResult},
        500: {"description": "Internal error", "model": InternalErrorResponse},
    },
    response_class=PlainTextResponse,
)
async def render_ascii_endpoint(body: RenderRequest) -> PlainTextResponse:
    """
    Render a PlantUML diagram to an ASCII art representation.

    This is useful for quick inspection in terminals or plain-text logs.
    """
    logger.info(
        "Render ASCII requested (sourceLength=%d)",
        len(body.source),
    )
    ascii_text = render_ascii(body.source)
    return PlainTextResponse(content=ascii_text)


@app.post(
    "/validate",
    response_model=ValidationResult,
    responses={
        200: {"description": "Diagram is valid"},
        400: {"description": "Diagram is invalid", "model": ValidationResult},
        500: {"description": "Internal error", "model": InternalErrorResponse},
    },
)
async def validate_endpoint(body: RenderRequest) -> Any:
    """
    Validate a PlantUML diagram without producing an image.

    On success, returns a ``ValidationResult`` with ``ok=True``. For invalid
    diagrams, a 400 response is returned containing the same model but with
    detailed issues describing where parsing failed.
    """
    logger.info(
        "Validate requested (sourceLength=%d)",
        len(body.source),
    )
    result = validate_diagram(body.source)
    if result.ok:
        return result
    # For invalid diagrams, surface as 400 with the same schema.
    return JSONResponse(
        status_code=400,
        content=result.model_dump(),
        headers={"X-PlantUML-Error": "validation_failed"},
    )


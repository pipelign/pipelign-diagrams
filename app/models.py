from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DiagramLanguage(str, Enum):
    """Diagram source languages supported by the public API."""

    PLANTUML = "plantuml"
    MERMAID = "mermaid"


class OutputFormat(str, Enum):
    """Output formats understood by one or more renderers."""

    PNG = "png"
    SVG = "svg"
    ASCII = "ascii"


class RenderRequest(BaseModel):
    """Request body for all render and validate endpoints."""

    source: str
    language: DiagramLanguage = DiagramLanguage.PLANTUML
    options: dict[str, Any] | None = None


class ValidationIssue(BaseModel):
    """Represents a single validation error or warning from a renderer."""

    message: str
    line: int | None = None


class ValidationResult(BaseModel):
    """Structured validation result for a diagram."""

    ok: bool
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)


class InternalErrorResponse(BaseModel):
    """Shape of internal error responses returned by the API."""

    ok: bool = False
    errorType: str = "internal_error"
    message: str
    details: dict[str, Any] | None = None

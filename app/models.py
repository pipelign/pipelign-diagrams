from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel


class RenderRequest(BaseModel):
    """Request body for all render and validate endpoints."""

    source: str
    options: Optional[dict[str, Any]] = None


class ValidationIssue(BaseModel):
    """Represents a single validation error or warning from PlantUML."""

    message: str
    line: Optional[int] = None


class ValidationResult(BaseModel):
    """Structured validation result for a PlantUML diagram."""

    ok: bool
    errors: List[ValidationIssue] = []
    warnings: List[ValidationIssue] = []


class InternalErrorResponse(BaseModel):
    """Shape of internal error responses returned by the API."""

    ok: bool = False
    errorType: str = "internal_error"
    message: str
    details: Optional[dict[str, Any]] = None


"""Renderer-independent exceptions used at service and HTTP boundaries."""

from __future__ import annotations

from typing import Any

from .models import DiagramLanguage, ValidationResult


class DiagramValidationError(Exception):
    """Raised when diagram source or a render request is invalid."""

    def __init__(
        self,
        result: ValidationResult,
        *,
        language: DiagramLanguage | None = None,
    ) -> None:
        self.result = result
        self.language = language
        super().__init__("Diagram validation failed")


class RendererInternalError(Exception):
    """An internal renderer failure with a safe message for API callers."""

    def __init__(
        self,
        message: str,
        *,
        language: DiagramLanguage | None = None,
        details: dict[str, Any] | None = None,
        public_message: str = "The diagram could not be rendered.",
    ) -> None:
        self.message = message
        self.language = language
        self.details = details or {}
        self.public_message = public_message
        super().__init__(message)

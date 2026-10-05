"""Machine authentication, bounded admission and restricted rendering inputs."""

import asyncio
import hmac
import os
import re
from contextlib import contextmanager
from threading import BoundedSemaphore

from starlette.responses import JSONResponse

from .limits import MAX_REQUEST_BYTES, MAX_SOURCE_BYTES, RenderPolicyError

_RENDER_SLOT = BoundedSemaphore(1)
_FORBIDDEN = re.compile(
    r"!include\w*\b|!theme\b|%(?:getenv|load_json|load_yaml|file_exists)\s*\("
    r"|\[\[|<\s*(?:img|image|script|iframe)\b|\b(?:https?|ftp|file)\s*:"
    r"|^\s*click\s|%%\s*\{",
    re.IGNORECASE | re.MULTILINE,
)


def validate_source(source, options):
    try:
        size = len(source.encode("utf-8"))
    except UnicodeError:
        raise RenderPolicyError(
            "invalid_request", "Source must be valid UTF-8 text.", 422
        ) from None
    if size > MAX_SOURCE_BYTES:
        raise RenderPolicyError(
            "source_too_large", "Diagram source code exceeds 128 KiB.", 413
        )
    if options not in (None, {}):
        raise RenderPolicyError(
            "unsupported_options",
            "Renderer options are fixed by the restricted profile.",
            422,
        )
    if _FORBIDDEN.search(source) or source.lstrip().startswith("---"):
        raise RenderPolicyError(
            "policy_rejected",
            "Use self-contained diagram code without includes, external resources, links or configuration overrides.",
        )


@contextmanager
def render_slot():
    if not _RENDER_SLOT.acquire(blocking=False):
        raise RenderPolicyError("overloaded", "The renderer is busy. Retry later.", 503)
    try:
        yield
    finally:
        _RENDER_SLOT.release()


class RendererGate:
    """Authenticate before reading bounded bodies; leave only liveness public."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def safe_send(message):
            if message["type"] == "http.response.start":
                message["headers"] = [
                    *message.get("headers", []),
                    (b"cache-control", b"private, no-store"),
                    (b"x-content-type-options", b"nosniff"),
                    (
                        b"content-security-policy",
                        b"sandbox; default-src 'none'; style-src 'unsafe-inline'",
                    ),
                ]
            await send(message)

        async def reject(status, code, message):
            response = JSONResponse(
                {"ok": False, "errorType": code, "message": message, "details": None},
                status_code=status,
            )
            await response(scope, receive, safe_send)

        if scope["path"] == "/health" and scope["method"] == "GET":
            return await self.app(scope, receive, safe_send)
        current = os.getenv("DIAGRAM_API_TOKEN", "")
        previous = os.getenv("DIAGRAM_API_TOKEN_PREVIOUS", "")
        if (
            len(current) < 32
            or not current.isascii()
            or any(c.isspace() for c in current + previous)
            or (previous and (len(previous) < 32 or not previous.isascii()))
        ):
            return await reject(
                503,
                "authentication_unconfigured",
                "Renderer authentication is not configured.",
            )
        headers = [
            value for key, value in scope["headers"] if key.lower() == b"authorization"
        ]
        candidate = (
            headers[0][7:]
            if len(headers) == 1 and headers[0].startswith(b"Bearer ")
            else b""
        )
        valid = hmac.compare_digest(candidate, current.encode("ascii"))
        if previous:
            valid = hmac.compare_digest(candidate, previous.encode("ascii")) | valid
        if not valid:
            return await reject(
                401, "authentication_failed", "Valid renderer credentials are required."
            )
        body = bytearray()
        try:
            async with asyncio.timeout(5):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    chunk = message.get("body", b"")
                    if len(body) + len(chunk) > MAX_REQUEST_BYTES:
                        return await reject(
                            413,
                            "request_too_large",
                            "Request body exceeds the size limit.",
                        )
                    body.extend(chunk)
                    if not message.get("more_body", False):
                        break
        except TimeoutError:
            return await reject(408, "request_timeout", "Request body timed out.")
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, bounded_receive, safe_send)

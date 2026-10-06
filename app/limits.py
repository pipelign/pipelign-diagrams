"""Reviewed renderer limits and source-independent public failures."""

MAX_SOURCE_BYTES = 128 * 1024
MAX_REQUEST_BYTES = 768 * 1024
MAX_OUTPUT_BYTES = 4 * 1024 * 1024
MAX_DIAGNOSTIC_BYTES = 16 * 1024
ENGINE_TIMEOUT_SECONDS = 20
POLICY_VERSION = "pipelign-restricted-v2"


class RenderPolicyError(Exception):
    def __init__(self, code, message, status=400):
        self.code = code
        self.message = message
        self.status = status
        super().__init__(message)

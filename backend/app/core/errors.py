"""ATRIO error model.

Every error returned by the API maps to one of these. The HTTP layer
translates them into the spec's `{"error": {"code", "message", ...}}`.
"""
from __future__ import annotations

from typing import Any


class AtrioError(Exception):
    """Base class for all ATRIO domain errors."""

    code: str = "INTERNAL"
    http_status: int = 500
    message: str = "Internal server error"

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
        code: str | None = None,
        http_status: int | None = None,
    ) -> None:
        super().__init__(message or self.message)
        if message is not None:
            self.message = message
        if code is not None:
            self.code = code
        if http_status is not None:
            self.http_status = http_status
        self.details = details or {}

    def to_payload(self, request_id: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"error": {"code": self.code, "message": self.message}}
        if self.details:
            body["error"]["details"] = self.details
        if request_id is not None:
            body["error"]["request_id"] = request_id
        return body


class NotFoundError(AtrioError):
    code = "NOT_FOUND"
    http_status = 404
    message = "Resource not found"


class ValidationFailed(AtrioError):
    code = "VALIDATION_FAILED"
    http_status = 422
    message = "Request validation failed"


class Unauthenticated(AtrioError):
    code = "UNAUTHENTICATED"
    http_status = 401
    message = "Authentication required"


class Forbidden(AtrioError):
    code = "FORBIDDEN"
    http_status = 403
    message = "Forbidden"


class ConflictState(AtrioError):
    code = "CONFLICT_STATE"
    http_status = 409
    message = "Resource is in a conflicting state"


class RateLimited(AtrioError):
    code = "RATE_LIMITED"
    http_status = 429
    message = "Rate limit exceeded"


class TwoPartyRequired(Forbidden):
    code = "TWO_PARTY_REQUIRED"
    message = "Two-party authorisation required"


class MandateViolation(Forbidden):
    code = "MANDATE_VIOLATION"
    message = "Action violates the active mandate"


class InferenceFailure(AtrioError):
    code = "INFERENCE_FAILED"
    http_status = 503
    message = "All inference providers failed"


class StorageFailure(AtrioError):
    code = "STORAGE_FAILED"
    http_status = 503
    message = "Object storage operation failed"


class UploadTooLarge(AtrioError):
    code = "UPLOAD_TOO_LARGE"
    http_status = 413
    message = "Upload exceeds size limit"


class UnsupportedMediaType(AtrioError):
    code = "UNSUPPORTED_MEDIA_TYPE"
    http_status = 415
    message = "File type not supported"


class ProposalExpired(ConflictState):
    code = "PROPOSAL_EXPIRED"
    message = "Treasury proposal has expired"

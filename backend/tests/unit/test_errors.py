"""Unit tests for app.core.errors."""
from __future__ import annotations

import pytest

from app.core.errors import (
    AtrioError,
    ConflictState,
    Forbidden,
    InferenceFailure,
    MandateViolation,
    NotFoundError,
    ProposalExpired,
    RateLimited,
    StorageFailure,
    TwoPartyRequired,
    Unauthenticated,
    UnsupportedMediaType,
    UploadTooLarge,
    ValidationFailed,
)


def test_base_default_payload():
    e = AtrioError()
    p = e.to_payload()
    assert p == {"error": {"code": "INTERNAL", "message": "Internal server error"}}


def test_payload_with_details_and_request_id():
    e = NotFoundError("nope", details={"thing": 1})
    p = e.to_payload("req-123")
    assert p["error"]["code"] == "NOT_FOUND"
    assert p["error"]["details"] == {"thing": 1}
    assert p["error"]["request_id"] == "req-123"


def test_payload_with_override_code_and_status():
    e = AtrioError("custom", code="CUSTOM_CODE", http_status=418)
    assert e.code == "CUSTOM_CODE"
    assert e.http_status == 418
    assert "custom" in e.to_payload()["error"]["message"]


@pytest.mark.parametrize(
    "cls,code,status",
    [
        (NotFoundError, "NOT_FOUND", 404),
        (ValidationFailed, "VALIDATION_FAILED", 422),
        (Unauthenticated, "UNAUTHENTICATED", 401),
        (Forbidden, "FORBIDDEN", 403),
        (ConflictState, "CONFLICT_STATE", 409),
        (RateLimited, "RATE_LIMITED", 429),
        (TwoPartyRequired, "TWO_PARTY_REQUIRED", 403),
        (MandateViolation, "MANDATE_VIOLATION", 403),
        (InferenceFailure, "INFERENCE_FAILED", 503),
        (StorageFailure, "STORAGE_FAILED", 503),
        (UploadTooLarge, "UPLOAD_TOO_LARGE", 413),
        (UnsupportedMediaType, "UNSUPPORTED_MEDIA_TYPE", 415),
        (ProposalExpired, "PROPOSAL_EXPIRED", 409),
    ],
)
def test_subclasses_have_expected_codes(cls, code, status):
    e = cls()
    assert e.code == code
    assert e.http_status == status

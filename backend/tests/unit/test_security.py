"""Unit tests for app.core.security."""
from __future__ import annotations

import time

import pytest

from app.core.security import (
    TokenError,
    constant_time_eq,
    create_access_token,
    create_magic_link_token,
    create_refresh_token,
    decode_token,
    hash_password,
    random_token,
    verify_password,
)


def test_access_token_round_trip():
    token = create_access_token(subject="user-1", tenant_id="tenant-1", role="founder")
    claims = decode_token(token)
    assert claims["sub"] == "user-1"
    assert claims["tenant_id"] == "tenant-1"
    assert claims["role"] == "founder"
    assert claims["type"] == "access"


def test_access_token_with_extra_claims():
    token = create_access_token(
        subject="u", tenant_id="t", role="founder", extra_claims={"scope": "wide"}
    )
    claims = decode_token(token)
    assert claims["scope"] == "wide"


def test_refresh_token_marked_correctly():
    token = create_refresh_token(subject="u", tenant_id="t")
    claims = decode_token(token)
    assert claims["type"] == "refresh"


def test_magic_link_token_marked_correctly():
    token = create_magic_link_token(email="x@y.com")
    claims = decode_token(token)
    assert claims["type"] == "magic_link"
    assert claims["sub"] == "x@y.com"


def test_decode_invalid_token_raises():
    with pytest.raises(TokenError):
        decode_token("nonsense.not.a.jwt")


def test_decode_tampered_signature_raises():
    token = create_access_token(subject="u", tenant_id="t", role="r")
    bad = token[:-3] + "XXX"
    with pytest.raises(TokenError):
        decode_token(bad)


def test_password_hash_and_verify():
    h = hash_password("hunter2")
    assert h != "hunter2"
    assert verify_password("hunter2", h) is True
    assert verify_password("wrong", h) is False


def test_random_token_unique_and_urlsafe():
    a = random_token()
    b = random_token()
    assert a != b
    # url-safe — no '/', '+', '='
    assert "/" not in a and "+" not in a


def test_constant_time_eq():
    assert constant_time_eq("abc", "abc") is True
    assert constant_time_eq("abc", "abd") is False
    assert constant_time_eq("a", "ab") is False


def test_keypair_path_loads_when_file_exists(tmp_path, monkeypatch):
    # Generate a real RSA keypair to verify the RS256 branch
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = tmp_path / "p.pem"
    pub = tmp_path / "u.pem"
    priv.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    pub.write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )
    from app.core.config import Settings

    s = Settings(
        atrio_env="local",
        jwt_private_key_path=str(priv),
        jwt_public_key_path=str(pub),
    )
    tok = create_access_token(subject="x", tenant_id="y", role="founder", settings=s)
    claims = decode_token(tok, settings=s)
    assert claims["sub"] == "x"


def test_prod_env_without_keys_raises():
    from app.core.config import Settings
    from app.core.security import _signing_material

    s = Settings(
        atrio_env="prod",
        jwt_private_key_path="/nonexistent/private",
        jwt_public_key_path="/nonexistent/public",
    )
    with pytest.raises(RuntimeError, match="JWT keys not found"):
        _signing_material(s)


def test_token_expiry_in_the_past_raises():
    """Token issued with exp in the past must fail to decode."""
    from datetime import UTC, datetime
    from jose import jwt as joselib

    from app.core.config import Settings

    s = Settings(atrio_env="test")
    now = int(time.time())
    claims = {
        "sub": "u",
        "tenant_id": "t",
        "role": "r",
        "type": "access",
        "iat": now - 7200,
        "exp": now - 3600,
        "jti": "x",
    }
    secret = s.jwt_test_secret
    expired = joselib.encode(claims, secret, algorithm="HS256")
    with pytest.raises(TokenError):
        decode_token(expired, settings=s)
    _ = datetime.now(UTC)  # silence import-unused

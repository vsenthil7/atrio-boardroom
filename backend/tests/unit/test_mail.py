"""Unit tests for the mailer."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core.config import Settings
from app.mail import (
    Email,
    LogMailer,
    NullMailer,
    SMTPConfig,
    SMTPMailer,
    build_mailer,
    render_magic_link_email,
)


def test_null_mailer_records_send():
    m = NullMailer()
    e = Email(to="x@y.com", subject="hi", text_body="ping")
    m.send(e)
    m.send(e)
    assert len(m.sent) == 2
    assert m.sent[0].to == "x@y.com"


def test_log_mailer_does_not_raise():
    m = LogMailer()
    m.send(Email(to="x@y.com", subject="hi", text_body="long " * 50))


def test_smtp_mailer_invokes_send_fn():
    sent = []

    def fake(msg):
        sent.append(msg)

    m = SMTPMailer(
        config=SMTPConfig(host="x", port=587, username="u", password="p"),
        _send_fn=fake,
    )
    m.send(Email(to="x@y.com", subject="hi", text_body="ping", html_body="<p>hi</p>"))
    assert len(sent) == 1
    msg = sent[0]
    assert msg["To"] == "x@y.com"
    assert msg["Subject"] == "hi"
    # multipart with html alt
    parts = list(msg.iter_parts())
    assert any("hi" in p.get_content() for p in parts)


def test_smtp_mailer_text_only():
    sent = []
    m = SMTPMailer(
        config=SMTPConfig(host="x"),
        _send_fn=sent.append,
    )
    m.send(Email(to="x@y.com", subject="s", text_body="t"))
    assert sent[0].get_content().strip() == "t"


def test_build_mailer_test_env():
    m = build_mailer(Settings(atrio_env="test"))
    assert isinstance(m, NullMailer)


def test_build_mailer_local_env():
    m = build_mailer(Settings(atrio_env="local"))
    assert isinstance(m, LogMailer)


def test_build_mailer_prod_without_smtp_falls_back():
    m = build_mailer(Settings(atrio_env="prod", smtp_host=""))
    assert isinstance(m, LogMailer)


def test_build_mailer_prod_with_smtp():
    m = build_mailer(
        Settings(
            atrio_env="prod",
            smtp_host="smtp.example.com",
            smtp_port=587,
        )
    )
    assert isinstance(m, SMTPMailer)
    assert m.config.host == "smtp.example.com"


def test_render_magic_link_includes_url_and_expiry():
    e = render_magic_link_email(
        email="user@x.com",
        link_url="https://app.atrio.example/signin?token=abc123",
        expires_minutes=10,
    )
    assert e.to == "user@x.com"
    assert "10 minutes" in e.text_body
    assert "abc123" in e.text_body
    assert e.html_body is not None
    assert "abc123" in e.html_body
    assert "Sign in" in e.html_body


def test_render_magic_link_default_expiry():
    e = render_magic_link_email(email="u@x.com", link_url="https://x/y")
    assert "15 minutes" in e.text_body


@pytest.mark.parametrize("env", ["demo", "staging"])
def test_build_mailer_other_envs_with_smtp(env):
    m = build_mailer(Settings(atrio_env=env, smtp_host="smtp.example.com"))
    assert isinstance(m, SMTPMailer)


def test_smtp_real_send_with_mock(monkeypatch):
    """Exercise the real SMTP code path (no fake send_fn) with a MagicMock smtplib."""
    captured = {}

    class _FakeSMTP:
        def __init__(self, host, port, timeout):
            captured["host"] = host
            captured["port"] = port

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self):
            captured["tls"] = True

        def login(self, u, p):
            captured["auth"] = (u, p)

        def send_message(self, msg):
            captured["msg"] = msg

    import smtplib

    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    m = SMTPMailer(
        config=SMTPConfig(host="smtp.example.com", username="u", password="p")
    )
    m.send(Email(to="x@y.com", subject="s", text_body="b"))
    assert captured["host"] == "smtp.example.com"
    assert captured["tls"] is True
    assert captured["auth"] == ("u", "p")
    assert captured["msg"]["To"] == "x@y.com"

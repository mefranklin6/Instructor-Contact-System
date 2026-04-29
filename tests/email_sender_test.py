"""Tests for EmailSender (init + unarmed path only; live SMTP not exercised)."""

import pytest


def test_email_sender_raises_when_smtp_config_missing(monkeypatch):
    """EmailSender raises ValueError when SMTP_HOST and SMTP_FROM are absent."""
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_FROM", raising=False)

    from src.email_sender import EmailSender

    with pytest.raises(ValueError, match="Missing required SMTP configuration"):
        EmailSender(armed=False)


def test_email_sender_unarmed_send_returns_true(monkeypatch):
    """Unarmed EmailSender.send() returns True without touching SMTP."""
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM", "no-reply@example.com")

    from src.email_sender import EmailSender

    sender = EmailSender(armed=False)
    assert sender.send("to@example.com", "Subject", "Body") is True
    assert sender.send("to@example.com", "Subject", "Body", cc_addrs=["cc@example.com"]) is True

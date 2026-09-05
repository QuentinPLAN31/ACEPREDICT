"""
Tests unitaires de services/email_service.py — dégradation gracieuse sans
SMTP configuré, et gestion d'échec réseau/authentification, comme pour
weather_service.py et ai_narrative.py.
"""
from app.services import email_service


def test_not_configured_returns_false_without_raising(monkeypatch):
    monkeypatch.setattr(email_service.settings, "smtp_host", "")
    monkeypatch.setattr(email_service.settings, "smtp_user", "")
    monkeypatch.setattr(email_service.settings, "smtp_password", "")
    assert email_service.is_configured() is False
    assert email_service.send_password_reset_email("a@b.com", "https://example.com/reset") is False


def test_smtp_failure_degrades_gracefully(monkeypatch):
    monkeypatch.setattr(email_service.settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(email_service.settings, "smtp_user", "user")
    monkeypatch.setattr(email_service.settings, "smtp_password", "pass")

    class ExplodingSMTP:
        def __init__(self, *args, **kwargs):
            raise ConnectionRefusedError("smtp down")

    monkeypatch.setattr(email_service.smtplib, "SMTP", ExplodingSMTP)
    assert email_service.is_configured() is True
    # Ne doit jamais lever d'exception, même si le serveur SMTP est injoignable.
    assert email_service.send_password_reset_email("a@b.com", "https://example.com/reset") is False

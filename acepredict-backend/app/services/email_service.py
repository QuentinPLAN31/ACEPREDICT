"""
Envoi d'e-mails transactionnels (pour l'instant : réinitialisation de mot de
passe). SMTP générique via smtplib — fonctionne avec n'importe quel
fournisseur (Gmail avec un "mot de passe d'application", Brevo/Mailjet/OVH,
un serveur SMTP d'hébergeur, etc.), pas de dépendance à un service tiers
propriétaire.

Dégradation gracieuse, comme ai_narrative.py/weather_service.py/stripe_service.py
ailleurs dans ce backend : sans SMTP_* configuré, on n'envoie rien par e-mail
mais on affiche le lien de réinitialisation dans les logs du serveur (utile en
développement local, et ça évite que /auth/forgot-password ne soit totalement
muet si tu testes avant d'avoir branché un vrai SMTP). En production, configure
SMTP_* dans .env pour un envoi réel.
"""
import logging
import smtplib
from email.message import EmailMessage
from typing import Optional

from app.config import settings

logger = logging.getLogger("acepredict.email")


def is_configured() -> bool:
    return bool(settings.smtp_host and settings.smtp_user and settings.smtp_password)


def send_password_reset_email(to_email: str, reset_link: str) -> bool:
    """Retourne True si l'e-mail a été envoyé (ou False en cas d'échec) —
    ne lève jamais d'exception, cf. politique de dégradation gracieuse du
    reste du backend (l'appelant ne doit jamais planter /auth/forgot-password,
    ni révéler si l'envoi a échoué : ça fuiterait quels e-mails existent)."""
    if not is_configured():
        logger.warning(
            "SMTP non configuré — lien de réinitialisation pour %s (à copier "
            "manuellement pour tester) : %s",
            to_email, reset_link,
        )
        return False

    msg = EmailMessage()
    msg["Subject"] = "Réinitialise ton mot de passe AcePredict"
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = to_email
    msg.set_content(
        "Tu as demandé la réinitialisation de ton mot de passe AcePredict.\n\n"
        f"Clique sur ce lien pour choisir un nouveau mot de passe (valable 1 heure) :\n{reset_link}\n\n"
        "Si tu n'es pas à l'origine de cette demande, ignore simplement cet e-mail : "
        "ton mot de passe actuel reste inchangé."
    )
    msg.add_alternative(
        f"""\
<html><body style="font-family:sans-serif;background:#131a16;color:#fff;padding:24px;">
  <h2 style="color:#D7F22C;">Réinitialise ton mot de passe</h2>
  <p>Tu as demandé la réinitialisation de ton mot de passe AcePredict.</p>
  <p><a href="{reset_link}" style="display:inline-block;background:#D7F22C;color:#131a16;
     padding:12px 20px;border-radius:8px;text-decoration:none;font-weight:bold;">
     Choisir un nouveau mot de passe</a></p>
  <p style="color:#9AA69A;font-size:13px;">Ce lien est valable 1 heure. Si tu n'es pas à
     l'origine de cette demande, ignore cet e-mail : ton mot de passe actuel reste inchangé.</p>
</body></html>""",
        subtype="html",
    )

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        return True
    except Exception:
        logger.exception("Échec d'envoi de l'e-mail de réinitialisation à %s", to_email)
        return False

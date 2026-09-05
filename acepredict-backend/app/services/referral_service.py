"""
Génération du code de parrainage (page "Invite et gagne") : court, unique,
facile à coller dans un lien (ravageapp-style ravageapp.fr/r/xxx, ici
visitennis_1.html?ref=xxx). Pas de dépendance à l'ID utilisateur (UUID trop
long/moche à partager).
"""
import secrets
import string
from datetime import datetime

from sqlalchemy.orm import Session

from app import models

_ALPHABET = string.ascii_uppercase + string.digits
_LENGTH = 8
_MAX_ATTEMPTS = 20

# Récompense (en analyses bonus, même monnaie que le pack ponctuel de la page
# Pricing) versée au PARRAIN quand un filleul prend un plan payant — cf.
# routers/billing.py, webhook checkout.session.completed.
REFERRAL_PLAN_BONUS = {
    "starter": 10,
    "pro": 20,
    "lifetime": 50,
}

# Paliers cumulés sur le nombre de filleuls ABONNÉS (pas juste inscrits) —
# bonus one-shot supplémentaire, en plus de la récompense par filleul.
REFERRAL_TIERS = [
    {"threshold": 1, "bonus_analyses": 10},
    {"threshold": 3, "bonus_analyses": 30},
    {"threshold": 5, "bonus_analyses": 60},
    {"threshold": 10, "bonus_analyses": 150},
]


def generate_referral_code(db: Session) -> str:
    for _ in range(_MAX_ATTEMPTS):
        code = "".join(secrets.choice(_ALPHABET) for _ in range(_LENGTH))
        exists = db.query(models.User).filter(models.User.referral_code == code).first()
        if not exists:
            return code
    # Improbable avec 36^8 combinaisons, mais on ne boucle jamais à l'infini.
    raise RuntimeError("Impossible de générer un code de parrainage unique")


def grant_subscription_reward(db: Session, referred_user: models.User, plan: str) -> None:
    """
    Appelé une seule fois par filleul, au moment où il prend un plan payant
    (cf. routers/billing.py) : verse la récompense au parrain (+ palier
    éventuellement débloqué) et marque le parrainage "subscribed". No-op
    silencieux si ce filleul n'a pas été parrainé, ou l'a déjà été récompensé
    (idempotent — un webhook Stripe peut être redélivré).
    """
    referral = (
        db.query(models.Referral)
        .filter(models.Referral.referred_user_id == referred_user.id, models.Referral.status == "registered")
        .first()
    )
    if not referral:
        return

    referrer = db.query(models.User).filter(models.User.id == referral.referrer_id).first()
    if not referrer:
        return

    bonus = REFERRAL_PLAN_BONUS.get(plan, 0)
    referral.status = "subscribed"
    referral.subscribed_at = datetime.utcnow()

    if not referrer.quota:
        referrer.quota = models.UsageQuota(user_id=referrer.id, analyses_limit=5)
        db.add(referrer.quota)
    referrer.quota.analyses_limit += bonus

    # Palier atteint pile avec ce nouveau filleul abonné (le compte ne peut
    # passer un seuil qu'une fois, donc pas de garde anti-doublon nécessaire).
    subscribed_count = (
        db.query(models.Referral)
        .filter(models.Referral.referrer_id == referrer.id, models.Referral.status == "subscribed")
        .count()
    ) + 1  # +1 : la ligne ci-dessus n'est pas encore commit()ée au moment du count
    tier = next((t for t in REFERRAL_TIERS if t["threshold"] == subscribed_count), None)
    if tier:
        bonus += tier["bonus_analyses"]
        referrer.quota.analyses_limit += tier["bonus_analyses"]

    # bonus_analyses_granted reflète le total attribuable à CE filleul (plan +
    # palier débloqué grâce à lui), pour que /referrals/me (qui en fait la
    # somme) affiche le vrai total gagné sans requête supplémentaire.
    referral.bonus_analyses_granted = bonus

"""
Page "Invite et gagne" du frontend : lien de parrainage personnel, suivi des
filleuls, récompenses en analyses bonus (même monnaie que le pack ponctuel de
la page Pricing — pas de "crédits" ou d'argent réel, contrairement à un
concurrent comme Ravage qui distribue des crédits image).

La récompense elle-même est déclenchée ailleurs : cf. routers/billing.py,
webhook checkout.session.completed, au moment où un filleul prend un plan
payant (c'est le seul endroit qui a la certitude Stripe qu'un paiement a eu
lieu — jamais ici, qui ne fait que lire l'état déjà en base).
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.services.referral_service import REFERRAL_TIERS

router = APIRouter(prefix="/referrals", tags=["referrals"])


@router.get("/me")
def my_referrals(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    referrals = (
        db.query(models.Referral)
        .filter(models.Referral.referrer_id == current_user.id)
        .order_by(models.Referral.created_at.desc())
        .all()
    )
    subscribed = [r for r in referrals if r.status == "subscribed"]
    pending = [r for r in referrals if r.status != "subscribed"]
    total_bonus = sum(r.bonus_analyses_granted for r in referrals)

    return {
        "referral_code": current_user.referral_code,
        # settings.frontend_base_url vient de FRONTEND_BASE_URL (.env) -- même
        # source que le lien de réinitialisation de mot de passe (auth.py) :
        # avant, ce fichier avait sa propre constante en dur, jamais mise à
        # jour au déploiement -- le lien de parrainage partagé pointait donc
        # toujours vers localhost, inutilisable pour quiconque hors de cette
        # machine. Cf. README "Synchronisation des données" -- même logique
        # que le reste de ce backend : une seule source de vérité par valeur.
        "referral_link": f"{settings.frontend_base_url}/visitennis_1.html?ref={current_user.referral_code}",
        "stats": {
            "filleuls_abonnes": len(subscribed),
            "filleuls_inscrits": len(referrals),
            "en_attente": len(pending),
            "analyses_bonus_gagnees": total_bonus,
        },
        "tiers": [
            {**tier, "unlocked": len(subscribed) >= tier["threshold"]}
            for tier in REFERRAL_TIERS
        ],
        # Anonymisé : le filleul n'est jamais identifié (email/nom) à son
        # parrain, seul le statut et les dates sont exposés.
        "referrals": [
            {
                "status": r.status,
                "created_at": r.created_at,
                "subscribed_at": r.subscribed_at,
                "bonus_analyses_granted": r.bonus_analyses_granted,
            }
            for r in referrals
        ],
    }

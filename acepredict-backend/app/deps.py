"""
Dépendances FastAPI réutilisables : utilisateur courant, gating par plan/quota.
"""
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.security import decode_access_token
from app import models

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Identifiants invalides ou expirés",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_error

    user_id = decode_access_token(token)
    if not user_id:
        raise credentials_error

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user or not user.is_active:
        raise credentials_error
    return user


# Nombre d'analyses par plan (point 4 : gating des plans). TOUS les plans
# payants sont désormais des quotas JOURNALIERS (cf. PLAN_PERIODS ci-dessous
# et la page pricing) -- changement du 2026-09-21 : Starter 3/jour, Pro
# 6/jour. Lifetime = "abonnement Pro à vie" payé en une fois (99€) : mêmes
# 6 analyses complètes/jour que Pro, permanent, jamais unlimited (avant ce
# correctif la page pricing annonçait "analyses illimitées" pour Pro/Lifetime
# alors que le quota réel restait fini -- texte et code étaient incohérents).
# Seul le plan free reste sur un quota MENSUEL (3/mois).
PLAN_QUOTAS = {
    "free": 3,
    "starter": 3,
    "pro": 6,
    "lifetime": 6,
}

# Durée de la période de reset par plan -- "day" pour tous les plans payants
# (rechargés chaque jour), "month" pour le plan gratuit uniquement.
PLAN_PERIODS = {
    "free": "month",
    "starter": "day",
    "pro": "day",
    "lifetime": "day",
}


def _period_length(plan: str) -> timedelta:
    return timedelta(days=1) if PLAN_PERIODS.get(plan, "month") == "day" else timedelta(days=30)


def require_quota(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> models.User:
    """Vérifie que l'utilisateur n'a pas dépassé son quota d'analyses avant
    de le laisser consommer un endpoint de prédiction (services/prediction.py).
    Réinitialise aussi le compteur si la période courante (jour ou mois selon
    le plan, cf. PLAN_PERIODS) est écoulée -- avant ce correctif, analyses_used
    ne redescendait JAMAIS à 0, quel que soit le plan."""
    quota = current_user.quota
    if quota is None:
        quota = models.UsageQuota(
            user_id=current_user.id,
            analyses_limit=PLAN_QUOTAS.get(current_user.plan.value, 5),
            period_start=datetime.utcnow(),
        )
        db.add(quota)
        db.commit()
        db.refresh(quota)

    plan = current_user.plan.value
    period_start = quota.period_start or datetime.utcnow()
    if datetime.utcnow() - period_start >= _period_length(plan):
        quota.analyses_used = 0
        quota.period_start = datetime.utcnow()
        quota.analyses_limit = PLAN_QUOTAS.get(plan, quota.analyses_limit)
        # bonus_analyses (packs achetés à l'unité) N'EST PAS remis à 0 ici --
        # un pack payé doit survivre au reset périodique du plan de base.
        db.commit()
        db.refresh(quota)

    if quota.analyses_used >= quota.analyses_limit + (quota.bonus_analyses or 0):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Quota d'analyses atteint pour votre plan. Passez à un plan supérieur ou achète des analyses supplémentaires.",
        )
    return current_user

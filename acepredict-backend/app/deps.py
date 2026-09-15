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


# Nombre d'analyses par plan (point 4 : gating des plans). Le plan Starter
# est désormais un quota JOURNALIER (2/jour, cf. PLAN_PERIODS ci-dessous et
# la page pricing) -- changement du 2026-09-15, avant lui était un quota
# mensuel de 50 jamais vraiment appliqué comme "1 analyse/jour" (le texte
# affiché sur la page pricing ne correspondait à aucune logique de reset
# réelle : period_start existait déjà sur UsageQuota mais n'était encore
# jamais relu/réinitialisé nulle part).
PLAN_QUOTAS = {
    "free": 5,
    "starter": 2,
    "pro": 500,
    "lifetime": 10_000,
}

# Durée de la période de reset par plan -- "day" pour Starter (2 analyses
# rechargées chaque jour), "month" pour les autres (comportement historique).
PLAN_PERIODS = {
    "free": "month",
    "starter": "day",
    "pro": "month",
    "lifetime": "month",
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

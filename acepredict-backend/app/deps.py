"""
Dépendances FastAPI réutilisables : utilisateur courant, gating par plan/quota.
"""
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


# Nombre d'analyses/mois par plan (point 4 : gating des plans).
PLAN_QUOTAS = {
    "free": 5,
    "starter": 50,
    "pro": 500,
    "lifetime": 10_000,
}


def require_quota(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> models.User:
    """Vérifie que l'utilisateur n'a pas dépassé son quota d'analyses avant
    de le laisser consommer un endpoint de prédiction (services/prediction.py)."""
    quota = current_user.quota
    if quota is None:
        quota = models.UsageQuota(
            user_id=current_user.id,
            analyses_limit=PLAN_QUOTAS.get(current_user.plan.value, 5),
        )
        db.add(quota)
        db.commit()
        db.refresh(quota)

    if quota.analyses_used >= quota.analyses_limit:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Quota d'analyses atteint pour votre plan. Passez à un plan supérieur.",
        )
    return current_user

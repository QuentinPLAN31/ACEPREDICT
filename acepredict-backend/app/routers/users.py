"""
Page "Compte" du frontend : infos perso, plan/abonnement en cours.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.deps import get_current_user

router = APIRouter(prefix="/users", tags=["users"])


@router.patch("/me", response_model=schemas.UserOut)
def update_me(
    payload: schemas.UserUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Bouton "Modifier" à côté de l'e-mail sur la page Compte du frontend."""
    if payload.email and payload.email != current_user.email:
        existing = db.query(models.User).filter(models.User.email == payload.email).first()
        if existing:
            raise HTTPException(status_code=400, detail="Cet e-mail est déjà utilisé")
        current_user.email = payload.email

    if payload.full_name is not None:
        current_user.full_name = payload.full_name

    db.commit()
    db.refresh(current_user)
    return current_user


@router.get("/me/subscription")
def my_subscription(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sub = (
        db.query(models.Subscription)
        .filter(models.Subscription.user_id == current_user.id)
        .order_by(models.Subscription.created_at.desc())
        .first()
    )
    quota = current_user.quota
    return {
        "plan": current_user.plan.value,
        "stripe_status": sub.status if sub else None,
        "current_period_end": sub.current_period_end if sub else None,
        "analyses_used": quota.analyses_used if quota else 0,
        "analyses_limit": quota.analyses_limit if quota else 0,
    }

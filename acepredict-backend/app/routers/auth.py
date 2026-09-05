"""
Inscription / connexion / infos du compte courant (point 4 — authentification).
JWT stateless (pas de session serveur) — cohérent avec un frontend SPA statique.
"""
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app import models, schemas
from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.deps import PLAN_QUOTAS
from app.security import (
    hash_password, verify_password, create_access_token,
    generate_reset_token, hash_reset_token,
)
from app.services import email_service
from app.services.referral_service import generate_referral_code

router = APIRouter(prefix="/auth", tags=["auth"])

# Message volontairement identique que l'e-mail existe ou non en base — sinon
# /auth/forgot-password devient un moyen de vérifier quels e-mails sont
# inscrits sur AcePredict (énumération de comptes).
FORGOT_PASSWORD_GENERIC_MESSAGE = (
    "Si un compte existe avec cet e-mail, un lien de réinitialisation vient d'être envoyé."
)


@router.post("/register", response_model=schemas.UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Cet e-mail est déjà utilisé")

    user = models.User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        plan=models.PlanEnum.free,
        referral_code=generate_referral_code(db),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    quota = models.UsageQuota(user_id=user.id, analyses_limit=PLAN_QUOTAS["free"])
    db.add(quota)

    # Programme de parrainage (page "Invite et gagne") : lien du type
    # ?ref=XXXXXXXX ouvert par le nouvel inscrit -> on relie son compte à
    # l'inviteur. Ne bloque jamais l'inscription si le code est invalide/
    # inconnu ou si quelqu'un tente de se parrainer lui-même.
    if payload.ref_code:
        referrer = (
            db.query(models.User)
            .filter(models.User.referral_code == payload.ref_code.strip().upper())
            .first()
        )
        if referrer and referrer.id != user.id:
            db.add(models.Referral(referrer_id=referrer.id, referred_user_id=user.id))

    db.commit()

    return user


@router.post("/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="E-mail ou mot de passe incorrect")

    token = create_access_token(subject=user.id)
    return schemas.Token(access_token=token)


@router.get("/me", response_model=schemas.UserOut)
def me(current_user: models.User = Depends(get_current_user)):
    return current_user


@router.post("/forgot-password", response_model=schemas.MessageOut)
def forgot_password(
    payload: schemas.ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Déclenche l'envoi d'un lien de réinitialisation. Répond toujours avec
    le même message générique, que l'e-mail existe ou non, pour ne jamais
    révéler quels comptes sont inscrits."""
    user = db.query(models.User).filter(models.User.email == payload.email).first()
    if user:
        raw_token, token_hash, expires_at = generate_reset_token()
        user.reset_token_hash = token_hash
        user.reset_token_expires_at = expires_at
        db.commit()

        reset_link = f"{settings.frontend_base_url}/visitennis_1.html?reset_token={raw_token}"
        # En tâche de fond : l'envoi (réseau SMTP) ne doit jamais ralentir ni
        # faire échouer la réponse HTTP, ni permettre de mesurer le délai de
        # réponse pour deviner si l'e-mail existait (timing attack).
        background_tasks.add_task(email_service.send_password_reset_email, user.email, reset_link)

    return schemas.MessageOut(message=FORGOT_PASSWORD_GENERIC_MESSAGE)


@router.post("/reset-password", response_model=schemas.MessageOut)
def reset_password(payload: schemas.ResetPasswordRequest, db: Session = Depends(get_db)):
    token_hash = hash_reset_token(payload.token)
    user = db.query(models.User).filter(models.User.reset_token_hash == token_hash).first()

    if not user or not user.reset_token_expires_at or user.reset_token_expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Lien de réinitialisation invalide ou expiré")

    user.hashed_password = hash_password(payload.new_password)
    # Usage unique : le token est invalidé immédiatement après utilisation.
    user.reset_token_hash = None
    user.reset_token_expires_at = None
    db.commit()

    return schemas.MessageOut(message="Mot de passe mis à jour. Tu peux te connecter.")

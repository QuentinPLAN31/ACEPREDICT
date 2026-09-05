"""
Stripe Checkout + webhook (page "Pricing" du frontend : Starter/Pro/Lifetime,
mensuel ou annuel) + résiliation depuis la page "Compte".
"""
from datetime import datetime

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.deps import get_current_user
from app.deps import PLAN_QUOTAS
from app.services import stripe_service
from app.services.referral_service import grant_subscription_reward

DEMO_MODE_MESSAGE = (
    "Paiement en mode démo : Stripe n'est pas configuré (ou mal configuré) sur "
    "ce backend (STRIPE_SECRET_KEY / STRIPE_PRICE_* dans .env). L'intégration "
    "est fonctionnelle et prête, il suffit d'ajouter de vraies clés Stripe "
    "pour activer les paiements réels."
)

router = APIRouter(prefix="/billing", tags=["billing"])


@router.post("/checkout", response_model=schemas.CheckoutSessionOut)
def create_checkout(
    payload: schemas.CheckoutSessionRequest,
    current_user: models.User = Depends(get_current_user),
):
    if payload.plan not in ("starter", "pro", "lifetime", "starter_annual", "pro_annual", "pack5"):
        raise HTTPException(status_code=400, detail="Plan invalide")

    try:
        url = stripe_service.create_checkout_session(
            user_email=current_user.email,
            plan=payload.plan,
            success_url="http://localhost:5500/visitennis_1.html?checkout=success",
            cancel_url="http://localhost:5500/visitennis_1.html?checkout=cancel",
        )
    except ValueError:
        # STRIPE_PRICE_* absent/vide dans .env : détecté avant le moindre appel réseau.
        raise HTTPException(status_code=400, detail=DEMO_MODE_MESSAGE)
    except stripe.error.StripeError:
        # Clé/price id présents mais invalides (ex: placeholders "sk_test_xxx"
        # jamais remplacés), ou Stripe injoignable : on ne laisse jamais
        # remonter une 500 brute jusqu'au frontend.
        raise HTTPException(status_code=400, detail=DEMO_MODE_MESSAGE)
    return schemas.CheckoutSessionOut(checkout_url=url)


@router.post("/cancel")
def cancel_subscription(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Bouton "Résilier l'abonnement" (page Compte) : résiliation à effet
    différé — l'accès premium reste actif jusqu'à current_period_end, comme
    annoncé sur la page Pricing ("résiliable à tout moment")."""
    sub = (
        db.query(models.Subscription)
        .filter(models.Subscription.user_id == current_user.id, models.Subscription.status == "active")
        .order_by(models.Subscription.created_at.desc())
        .first()
    )
    if not sub or not sub.stripe_subscription_id:
        raise HTTPException(status_code=400, detail="Aucun abonnement actif à résilier.")

    try:
        stripe_sub = stripe_service.cancel_subscription(sub.stripe_subscription_id)
    except stripe.error.StripeError:
        # Même logique que /checkout : Stripe non configuré (démo) ou clé
        # invalide ne doit jamais remonter une 500 brute au frontend.
        raise HTTPException(status_code=400, detail=DEMO_MODE_MESSAGE)

    sub.status = "canceling"
    period_end = stripe_sub.get("current_period_end")
    if period_end:
        sub.current_period_end = datetime.utcfromtimestamp(period_end)
    db.commit()
    return {"status": "canceling", "current_period_end": sub.current_period_end}


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Reçoit les événements Stripe (checkout.session.completed,
    customer.subscription.updated/deleted) et met à jour plan + quota.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe_service.construct_webhook_event(payload, sig_header)
    except Exception:
        raise HTTPException(status_code=400, detail="Signature webhook invalide")

    event_type = event["type"]
    data = event["data"]["object"]

    if event_type == "checkout.session.completed":
        email = data.get("customer_email")
        plan = data.get("metadata", {}).get("plan")
        user = db.query(models.User).filter(models.User.email == email).first()
        if user and plan == "pack5":
            # Pack ponctuel : +5 analyses ajoutées au quota actuel, pas un
            # abonnement — ne touche ni user.plan ni la table Subscription
            # (aucun stripe_subscription_id, mode "payment" côté Stripe).
            if not user.quota:
                user.quota = models.UsageQuota(
                    user_id=user.id,
                    analyses_limit=PLAN_QUOTAS.get(user.plan.value, 5),
                )
                db.add(user.quota)
            user.quota.analyses_limit += 5
            db.commit()
        elif user and plan:
            user.plan = models.PlanEnum(plan)
            user.stripe_customer_id = data.get("customer")
            if user.quota:
                user.quota.analyses_limit = PLAN_QUOTAS.get(plan, user.quota.analyses_limit)

            sub = models.Subscription(
                user_id=user.id,
                stripe_subscription_id=data.get("subscription"),
                plan=models.PlanEnum(plan),
                status="active",
            )
            db.add(sub)
            # Programme de parrainage (page "Invite et gagne") : verse la
            # récompense au parrain de `user`, si `user` a été parrainé et
            # n'a pas encore été récompensé (no-op sinon).
            grant_subscription_reward(db, user, plan)
            db.commit()

    elif event_type == "customer.subscription.updated":
        # Reflète côté Stripe un cancel_at_period_end (résilié via /billing/cancel
        # OU directement depuis le portail Stripe) : l'utilisateur garde l'accès
        # jusqu'à current_period_end, seul le badge de statut change.
        stripe_sub_id = data.get("id")
        sub = (
            db.query(models.Subscription)
            .filter(models.Subscription.stripe_subscription_id == stripe_sub_id)
            .first()
        )
        if sub:
            sub.status = "canceling" if data.get("cancel_at_period_end") else data.get("status", sub.status)
            period_end = data.get("current_period_end")
            if period_end:
                sub.current_period_end = datetime.utcfromtimestamp(period_end)
            db.commit()

    elif event_type == "customer.subscription.deleted":
        stripe_sub_id = data.get("id")
        sub = (
            db.query(models.Subscription)
            .filter(models.Subscription.stripe_subscription_id == stripe_sub_id)
            .first()
        )
        if sub:
            sub.status = "canceled"
            user = db.query(models.User).filter(models.User.id == sub.user_id).first()
            if user:
                user.plan = models.PlanEnum.free
                if user.quota:
                    user.quota.analyses_limit = PLAN_QUOTAS["free"]
            db.commit()

    return {"received": True}

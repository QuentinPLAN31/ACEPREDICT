"""
Programme créateurs : un créateur partage app-tennismind.com/?via=<slug>, le
navigateur garde le code 30 jours (localStorage), il est envoyé à
l'inscription et rattache le compte au créateur (une seule fois, jamais
réécrit). Au premier achat de ce compte, une commission fixe est enregistrée
(cf. routers/billing.py), versable après le délai de remboursement.

Grille (une fois par client) : pack 0,50 €, Starter 1,50 €, Pro 3 €,
Accès à vie 8 €. Bonus selon le nombre de clients payants amenés dans le
mois : 10-29 -> +25 %, 30 et plus -> +50 %.
"""
import re
import secrets
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app import models

COMMISSION_CENTS = {"pack5": 50, "starter": 150, "pro": 300, "lifetime": 800}
TIERS = [(30, 1.5), (10, 1.25), (0, 1.0)]  # (seuil clients payants du mois, multiplicateur)
# Le compte doit payer dans ce délai après son inscription via le lien.
ATTRIBUTION_DAYS = 30
# Commission versable une fois ce délai passé sans remboursement.
REFUND_HOLD_DAYS = 30

_SLUG_RE = re.compile(r"^[a-z0-9_-]{2,40}$")


def normalize_slug(code: Optional[str]) -> Optional[str]:
    if not code:
        return None
    slug = code.strip().lower()
    return slug if _SLUG_RE.match(slug) else None


def new_dashboard_key() -> str:
    return secrets.token_urlsafe(16)


def get_active_creator(db: Session, code: Optional[str]) -> Optional[models.Creator]:
    slug = normalize_slug(code)
    if not slug:
        return None
    return (
        db.query(models.Creator)
        .filter(models.Creator.slug == slug, models.Creator.is_active.is_(True))
        .first()
    )


def attribute_signup(db: Session, user: models.User, via_code: Optional[str]) -> None:
    """Rattache un compte NOUVEAU à un créateur. No-op si code inconnu ou
    compte déjà rattaché : n'empêche jamais l'inscription."""
    if user.creator_id:
        return
    creator = get_active_creator(db, via_code)
    if creator:
        user.creator_id = creator.id
        user.creator_attributed_at = datetime.utcnow()


def record_conversion(
    db: Session,
    user: models.User,
    plan: str,
    amount_cents: Optional[int] = None,
    session_id: Optional[str] = None,
    payment_intent: Optional[str] = None,
    customer_id: Optional[str] = None,
) -> Optional[models.CreatorConversion]:
    """Appelé à chaque paiement Checkout réussi. Une commission par client :
    la première dans le délai d'attribution ; si le client passe ensuite à
    une offre plus chère (toujours dans le délai, commission pas encore
    versée), la commission est montée au niveau de la nouvelle offre."""
    if not user.creator_id or not user.creator_attributed_at:
        return None
    base = plan.replace("_annual", "")
    commission = COMMISSION_CENTS.get(base)
    if commission is None:
        return None
    if datetime.utcnow() - user.creator_attributed_at > timedelta(days=ATTRIBUTION_DAYS):
        return None

    conv = db.query(models.CreatorConversion).filter(models.CreatorConversion.user_id == user.id).first()
    if conv:
        if session_id and conv.stripe_session_id == session_id:
            return conv  # webhook redélivré
        if conv.status == "pending" and commission > conv.commission_cents:
            conv.product, conv.commission_cents = base, commission
            conv.amount_cents = amount_cents
            conv.stripe_session_id = session_id
            conv.stripe_payment_intent = payment_intent
            conv.stripe_customer_id = customer_id or conv.stripe_customer_id
        return conv

    conv = models.CreatorConversion(
        creator_id=user.creator_id,
        user_id=user.id,
        product=base,
        amount_cents=amount_cents,
        commission_cents=commission,
        stripe_session_id=session_id,
        stripe_payment_intent=payment_intent,
        stripe_customer_id=customer_id,
        status="pending",
    )
    db.add(conv)
    return conv


def void_for_refund(db: Session, payment_intent: Optional[str], customer_id: Optional[str]) -> int:
    """Remboursement Stripe (charge.refunded) : annule la commission non
    encore versée liée à ce paiement / ce client."""
    q = db.query(models.CreatorConversion).filter(models.CreatorConversion.status == "pending")
    convs = []
    if payment_intent:
        convs = q.filter(models.CreatorConversion.stripe_payment_intent == payment_intent).all()
    if not convs and customer_id:
        convs = q.filter(models.CreatorConversion.stripe_customer_id == customer_id).all()
    for c in convs:
        c.status = "void"
    return len(convs)


def _month_bounds(month: str):
    start = datetime.strptime(month, "%Y-%m")
    end = datetime(start.year + (start.month == 12), start.month % 12 + 1, 1)
    return start, end


def multiplier_for(count: int) -> float:
    return next(m for seuil, m in TIERS if count >= seuil)


def creator_month(db: Session, creator: models.Creator, month: str) -> dict:
    start, end = _month_bounds(month)
    convs = (
        db.query(models.CreatorConversion)
        .filter(
            models.CreatorConversion.creator_id == creator.id,
            models.CreatorConversion.created_at >= start,
            models.CreatorConversion.created_at < end,
        )
        .all()
    )
    valid = [c for c in convs if c.status != "void"]
    mult = multiplier_for(len(valid))
    now = datetime.utcnow()
    by_product = {p: sum(1 for c in valid if c.product == p) for p in COMMISSION_CENTS}
    base = sum(c.commission_cents for c in valid)
    payable = sum(
        c.commission_cents for c in valid
        if c.status == "pending" and now - c.created_at >= timedelta(days=REFUND_HOLD_DAYS)
    )
    waiting = sum(
        c.commission_cents for c in valid
        if c.status == "pending" and now - c.created_at < timedelta(days=REFUND_HOLD_DAYS)
    )
    paid = sum(c.commission_cents for c in valid if c.status == "paid")
    signups = (
        db.query(models.User)
        .filter(
            models.User.creator_id == creator.id,
            models.User.creator_attributed_at >= start,
            models.User.creator_attributed_at < end,
        )
        .count()
    )
    r = lambda cents: round(cents * mult / 100, 2)
    return {
        "creator": creator.slug,
        "name": creator.name,
        "month": month,
        "clicks_total": creator.clicks or 0,
        "signups": signups,
        "paying_clients": len(valid),
        "refunded": len(convs) - len(valid),
        "by_product": by_product,
        "bonus_pct": round((mult - 1) * 100),
        "total_eur": r(base),
        "payable_eur": r(payable),
        "waiting_refund_period_eur": r(waiting),
        "paid_eur": r(paid),
    }


def mark_month_paid(db: Session, creator: models.Creator, month: str) -> int:
    """Marque comme versées les commissions du mois sorties du délai de
    remboursement."""
    start, end = _month_bounds(month)
    now = datetime.utcnow()
    convs = (
        db.query(models.CreatorConversion)
        .filter(
            models.CreatorConversion.creator_id == creator.id,
            models.CreatorConversion.status == "pending",
            models.CreatorConversion.created_at >= start,
            models.CreatorConversion.created_at < end,
        )
        .all()
    )
    n = 0
    for c in convs:
        if now - c.created_at >= timedelta(days=REFUND_HOLD_DAYS):
            c.status, c.paid_at = "paid", now
            n += 1
    return n

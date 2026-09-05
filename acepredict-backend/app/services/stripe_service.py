"""
Intégration Stripe Checkout + webhooks (point 6 — facturation/abonnements).
Plans mappés sur la page Pricing de l'app : Starter 10€/mois, Pro 19€/mois,
Lifetime 99€ (paiement unique).
"""
import stripe

from app.config import settings

stripe.api_key = settings.stripe_secret_key

PLAN_TO_PRICE = {
    "starter": settings.stripe_price_starter,
    "pro": settings.stripe_price_pro,
    "lifetime": settings.stripe_price_lifetime,
    # Facturation annuelle (tarif dégressif) — même plan interne (starter/pro),
    # juste un Price Stripe différent. Voir create_checkout_session ci-dessous :
    # le "_annual" est retiré avant d'écrire user.plan (cf. PlanEnum, pas de
    # valeur "starter_annual" côté modèle — seule la facturation change).
    "starter_annual": settings.stripe_price_starter_annual,
    "pro_annual": settings.stripe_price_pro_annual,
    # Pack ponctuel : +5 analyses, paiement unique, aucun abonnement créé
    # (cf. checkout.session.completed dans routers/billing.py).
    "pack5": settings.stripe_price_pack5,
}


def create_checkout_session(user_email: str, plan: str, success_url: str, cancel_url: str) -> str:
    price_id = PLAN_TO_PRICE.get(plan)
    if not price_id:
        raise ValueError(f"Plan inconnu ou non configuré: {plan}")

    mode = "payment" if plan in ("lifetime", "pack5") else "subscription"
    base_plan = plan.replace("_annual", "")

    session = stripe.checkout.Session.create(
        mode=mode,
        customer_email=user_email,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"plan": base_plan},
    )
    return session.url


def cancel_subscription(stripe_subscription_id: str):
    """Résiliation "à tout moment" = effective à la fin de la période déjà
    payée (cf. bouton Résilier de la page Compte) — jamais un remboursement
    immédiat au prorata, non géré ici."""
    return stripe.Subscription.modify(stripe_subscription_id, cancel_at_period_end=True)


def construct_webhook_event(payload: bytes, sig_header: str):
    return stripe.Webhook.construct_event(
        payload, sig_header, settings.stripe_webhook_secret
    )

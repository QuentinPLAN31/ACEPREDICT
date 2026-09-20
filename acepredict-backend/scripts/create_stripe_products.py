"""
Script à lancer UNE FOIS, en local, pour créer tous les produits/tarifs
AcePredict sur Stripe (mode Live) et le webhook associé -- évite de tout
cliquer à la main dans le dashboard Stripe.

Usage :
    export STRIPE_SECRET_KEY=sk_live_...
    python3 scripts/create_stripe_products.py

La clé secrète ne quitte JAMAIS ta machine : ce script tourne en local, lit
la clé depuis une variable d'environnement, et ne l'envoie nulle part
d'autre qu'à l'API Stripe elle-même. Colle uniquement les résultats
(Price ID, Webhook secret) ailleurs -- jamais la clé secrète.

Facturation "tous les 28 jours" (au lieu d'un mois calendaire classique) pour
Starter et Pro : Stripe le permet via un intervalle personnalisé en jours
(interval="day", interval_count=28). Les tarifs annuels restent de vraies
années (interval="year").
"""
import os
import sys

import stripe

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
if not stripe.api_key:
    print("ERREUR : variable d'environnement STRIPE_SECRET_KEY manquante.")
    print("Lance d'abord : export STRIPE_SECRET_KEY=sk_live_...")
    sys.exit(1)

if not stripe.api_key.startswith("sk_live_"):
    print(f"ATTENTION : cette clé ne commence pas par 'sk_live_' ({stripe.api_key[:12]}...).")
    confirm = input("Continuer quand même ? (o/N) ")
    if confirm.lower() != "o":
        sys.exit(0)

# URL du backend Railway -- utilisée pour créer le webhook automatiquement.
WEBHOOK_URL = "https://acepredict-production.up.railway.app/billing/webhook"

# (nom_produit, description, montant_en_centimes, devise, mode)
# mode = ("recurring", interval, interval_count) ou ("one_time",)
PRODUCTS = [
    ("AcePredict Starter", "Abonnement Starter -- facturé tous les 28 jours", 1000, "eur", ("recurring", "day", 28)),
    ("AcePredict Starter (annuel)", "Abonnement Starter -- facturation annuelle", 9600, "eur", ("recurring", "year", 1)),
    ("AcePredict Pro", "Abonnement Pro -- facturé tous les 28 jours", 1900, "eur", ("recurring", "day", 28)),
    ("AcePredict Pro (annuel)", "Abonnement Pro -- facturation annuelle", 18000, "eur", ("recurring", "year", 1)),
    ("AcePredict Lifetime", "Accès à vie -- paiement unique", 9900, "eur", ("one_time",)),
    ("AcePredict Pack 5 analyses", "Pack ponctuel de 5 analyses -- paiement unique", 499, "eur", ("one_time",)),
]

ENV_VAR_NAMES = [
    "STRIPE_PRICE_STARTER",
    "STRIPE_PRICE_STARTER_ANNUAL",
    "STRIPE_PRICE_PRO",
    "STRIPE_PRICE_PRO_ANNUAL",
    "STRIPE_PRICE_LIFETIME",
    "STRIPE_PRICE_PACK5",
]

print("=== Création des produits et tarifs Stripe ===\n")
price_ids = []
for (name, description, amount, currency, mode), env_name in zip(PRODUCTS, ENV_VAR_NAMES):
    product = stripe.Product.create(name=name, description=description)

    price_kwargs = {
        "product": product.id,
        "unit_amount": amount,
        "currency": currency,
    }
    if mode[0] == "recurring":
        _, interval, interval_count = mode
        price_kwargs["recurring"] = {"interval": interval, "interval_count": interval_count}

    price = stripe.Price.create(**price_kwargs)
    price_ids.append((env_name, price.id))
    print(f"✓ {name} -- {amount / 100:.2f}{currency.upper()} -- {price.id}")

print("\n=== Création du webhook ===\n")
try:
    webhook = stripe.WebhookEndpoint.create(
        url=WEBHOOK_URL,
        enabled_events=[
            "checkout.session.completed",
            "customer.subscription.updated",
            "customer.subscription.deleted",
        ],
    )
    print(f"✓ Webhook créé : {webhook.id}")
    print(f"  Signing secret (à mettre dans Railway, PAS ici) : {webhook.secret}")
except stripe.error.StripeError as e:
    print(f"⚠️  Webhook non créé automatiquement ({e}). Crée-le à la main dans le dashboard Stripe :")
    print(f"    URL : {WEBHOOK_URL}")
    print("    Événements : checkout.session.completed, customer.subscription.updated, customer.subscription.deleted")

print("\n=== Résumé -- colle ces lignes (SAUF le webhook secret) à Claude, et TOUT dans Railway → Variables ===\n")
for env_name, price_id in price_ids:
    print(f"{env_name}={price_id}")
print("STRIPE_SECRET_KEY=" + stripe.api_key)
print("(+ STRIPE_WEBHOOK_SECRET affiché ci-dessus, à copier UNIQUEMENT dans Railway)")

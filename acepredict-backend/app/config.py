"""
Configuration centralisée (variables d'environnement).
Charge automatiquement le fichier .env à la racine du projet.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql://acepredict:acepredict@localhost:5432/acepredict"

    # Auth
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 30

    # "Se connecter / S'inscrire avec Google" (cf. routers/auth.py /auth/google).
    # Client ID OAuth 2.0 (type "Application Web") créé sur
    # https://console.cloud.google.com/apis/credentials -- sert à vérifier que
    # le jeton d'identité Google reçu du frontend a bien été émis pour CETTE
    # app (vérification de l'audience), pas pour une autre. Le même Client ID
    # doit être renseigné côté frontend (GOOGLE_CLIENT_ID dans visitennis_1.html).
    google_client_id: str = ""

    # Stripe -- clé secrète et webhook secret restent des variables d'env
    # PURES (jamais de défaut en dur ici : ce sont de vraies clés d'accès).
    # Les Price ID en revanche sont de simples identifiants publics (comme un
    # ID de produit), sans risque à committer -- mis en dur ci-dessous comme
    # défauts pour ne pas dépendre de 6 variables Railway supplémentaires ;
    # un Price ID différent (ex: pour rebasculer en mode Test) peut toujours
    # être fourni via une variable d'env du même nom, qui prime sur ce défaut.
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    # Compte Stripe "AcePredict" (production, live) -- créés via
    # scripts/create_stripe_products.py le 2026-09-20. Starter/Pro facturés
    # tous les 28 jours (pas un mois calendaire), Starter_annual/Pro_annual
    # facturés une fois par an, Lifetime et Pack5 en paiement unique.
    stripe_price_starter: str = "price_1UHhBqPYpMDqCRPpIYtvHJKr"
    stripe_price_pro: str = "price_1UHhBrPYpMDqCRPpVIkvwQ1a"
    stripe_price_lifetime: str = "price_1UHhBsPYpMDqCRPpyenE5Owb"
    # Variantes "facturation annuelle" (tarif dégressif, cf. page Pricing).
    stripe_price_starter_annual: str = "price_1UHhBqPYpMDqCRPpsmGxQ4c7"
    stripe_price_pro_annual: str = "price_1UHhBrPYpMDqCRPpEuVKCnrz"
    # Pack ponctuel (paiement unique, pas d'abonnement) — cf. page Pricing.
    stripe_price_pack5: str = "price_1UHhBsPYpMDqCRPpV9njfbgU"

    # Live data (calendrier des prochains matchs — cf. services/livetennis_client.py)
    livetennisapi_key: str = ""
    livetennisapi_base_url: str = "https://api.livetennisapi.com/api/public/v1"

    # Probabilité de marché (cf. services/polymarket_service.py) — API Gamma
    # de Polymarket, publique et SANS clé (contrairement à The Odds API,
    # abandonnée : payante et peu fiable en pratique). polymarket_enabled
    # permet de désactiver la fonctionnalité sans toucher au code si jamais
    # elle devient un jour instable.
    polymarket_enabled: bool = True
    polymarket_base_url: str = "https://gamma-api.polymarket.com"

    # Météo (conditions de match — vent/température/humidité, cf. services/
    # weather_service.py et weather_providers.py). weather_provider choisit le
    # fournisseur : "openweathermap" (défaut, clé requise, sûr en commercial)
    # ou "open-meteo" (sans clé, mais licence non-commercial only — ne jamais
    # l'activer en prod tant que le site est monétisé, cf. README).
    weather_api_key: str = ""
    # openweathermap : site à but commercial (Stripe actif) -> open-meteo est
    # exclu (licence non-commercial only). Free tier OpenWeatherMap = 1000
    # appels/jour, gratuit, pas de CB, licence compatible usage commercial.
    weather_provider: str = "openweathermap"

    # Analyse approfondie générée par IA (commentaire en langage naturel à partir
    # des facteurs calculés — Elo, forme, head-to-head, fatigue, météo — cf.
    # services/ai_narrative.py). Clé sur https://console.anthropic.com/ .
    # Sans clé : l'analyse fonctionne normalement, juste sans ce commentaire.
    anthropic_api_key: str = ""
    # Vérifier le modèle le plus récent sur https://docs.claude.com/en/docs/about-claude/models
    # (l'ancien défaut "claude-sonnet-4-6" n'existe plus -- l'API le rejetait
    # silencieusement, ce qui désactivait l'analyse sans jamais avertir personne).
    anthropic_model: str = "claude-sonnet-5"

    # E-mail transactionnel (réinitialisation de mot de passe, cf.
    # services/email_service.py). SMTP générique — Gmail (mot de passe
    # d'application), Brevo/Mailjet, ou le SMTP de ton hébergeur.
    # Sans ces variables : le lien de réinitialisation est juste affiché dans
    # les logs du serveur au lieu d'être envoyé par e-mail (pratique pour
    # tester sans SMTP, à configurer avant la mise en prod réelle).
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    # URL de base du frontend, utilisée pour construire le lien envoyé dans
    # l'e-mail de réinitialisation. En local (fichier ouvert en double-clic),
    # laisse la valeur par défaut : le frontend sait la reconnaître.
    frontend_base_url: str = "http://localhost:5500"

    # Misc
    env: str = "development"
    # "null" = origine envoyée par un navigateur quand landing.html/visitennis_1.html
    # sont ouverts directement en double-cliquant (file://), sans serveur local —
    # cas le plus probable pour un projet scolaire. On l'autorise par défaut en dev.
    cors_origins: str = "http://localhost:3000,http://localhost:5173,http://localhost:5500,http://localhost:8080,null"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
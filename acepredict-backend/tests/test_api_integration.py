"""
Tests d'intégration bout-en-bout sur SQLite en mémoire : couvrent le flow
réellement utilisé par le frontend (inscription -> connexion -> compte ->
recherche de joueurs -> analyse -> historique -> checkout sans Stripe
configuré), pour éviter une régression silencieuse sur ces routes.
"""
import os
from datetime import datetime, timedelta

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import Base, get_db
from app import models

# Une base SQLite en mémoire partagée entre toutes les requêtes du test
# (StaticPool : sinon chaque connexion SQLAlchemy verrait une base vide).
engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def seed_players():
    db = TestingSessionLocal()
    p1 = models.Player(name="Carlos Alcaraz", country="ESP", tour="atp", elo_overall=2100)
    p2 = models.Player(name="Jannik Sinner", country="ITA", tour="atp", elo_overall=2050)
    db.add_all([p1, p2])
    db.commit()
    db.refresh(p1)
    db.refresh(p2)

    # Historique réel pour tester la "forme récente" (cf. build_prediction /
    # _recent_form) : p1 gagne 4 de ses 5 derniers matchs, p2 en perd 4.
    outcomes = ["V", "V", "D", "V", "V"]
    for i, outcome in enumerate(outcomes):
        db.add(models.Match(
            player1_id=p1.id,
            player2_id=p2.id,
            winner_id=p1.id if outcome == "V" else p2.id,
            tourney_date=datetime.utcnow() - timedelta(days=i + 1),
            surface="hard",
            source="manual",
        ))
    db.commit()

    yield {"p1": p1.id, "p2": p2.id}
    db.close()


def register_and_login(email="joueur@example.com", password="password123"):
    r = client.post("/auth/register", json={"email": email, "password": password, "full_name": "Joueur Test"})
    assert r.status_code == 201, r.text
    r = client.post("/auth/login", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_register_login_me():
    token = register_and_login("victor@example.com")
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == "victor@example.com"
    assert r.json()["plan"] == "free"


def test_update_profile():
    token = register_and_login("update-me@example.com")
    r = client.patch(
        "/users/me",
        json={"full_name": "Nouveau Nom"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["full_name"] == "Nouveau Nom"


def test_update_profile_email_conflict():
    register_and_login("taken@example.com")
    token = register_and_login("wants-taken-email@example.com")
    r = client.patch(
        "/users/me",
        json={"email": "taken@example.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400


def test_players_search():
    r = client.get("/players?q=Alcaraz")
    assert r.status_code == 200
    players = r.json()
    names = [p["name"] for p in players]
    assert "Carlos Alcaraz" in names
    # data_confidence toujours présent (libellé FR, cf. services/
    # data_confidence.py) -- seed_players ne le fixe pas explicitement, donc
    # valeur par défaut du modèle ("insufficient" -> "Données insuffisantes").
    alcaraz = next(p for p in players if p["name"] == "Carlos Alcaraz")
    assert alcaraz["data_confidence"] == "Données insuffisantes"


def test_analysis_flow_and_history(seed_players):
    token = register_and_login("analyse@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    r = client.post(
        "/analyses",
        json={"player1_id": seed_players["p1"], "player2_id": seed_players["p2"]},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["predicted_winner_id"] == seed_players["p1"]  # meilleur elo
    assert 0.5 < body["win_probability"] <= 1.0
    # Cf. README "Synchronisation des données" : niveau de fiabilité exposé
    # pour que le frontend avertisse plutôt que de bloquer l'analyse.
    assert body["player1_data_confidence"] == "Données insuffisantes"
    assert body["player2_data_confidence"] == "Données insuffisantes"

    # Forme récente calculée sur les vrais matchs seedés ci-dessus (4V-1D pour
    # p1, 1V-4D pour p2) — cf. app/services/prediction.py::_recent_form.
    assert body["detail"]["form_player1"] == {
        "results": ["V", "V", "D", "V", "V"],
        "wins": 4, "losses": 1, "label": "En grande forme",
    }
    assert body["detail"]["form_player2"] == {
        "results": ["D", "D", "V", "D", "D"],
        "wins": 1, "losses": 4, "label": "Forme fragile",
    }

    r = client.get("/analyses/history", headers=headers)
    assert r.status_code == 200
    history = r.json()
    assert len(history) == 1
    assert history[0]["player1_name"] == "Carlos Alcaraz"
    assert history[0]["predicted_winner_name"] == "Carlos Alcaraz"
    assert history[0]["player1_data_confidence"] == "Données insuffisantes"
    assert history[0]["player2_data_confidence"] == "Données insuffisantes"


def test_analysis_quota_exceeded(seed_players):
    token = register_and_login("quota@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    # plan free = 5 analyses/mois (voir app/deps.py PLAN_QUOTAS)
    for _ in range(5):
        r = client.post(
            "/analyses",
            json={"player1_id": seed_players["p1"], "player2_id": seed_players["p2"]},
            headers=headers,
        )
        assert r.status_code == 200
    r = client.post(
        "/analyses",
        json={"player1_id": seed_players["p1"], "player2_id": seed_players["p2"]},
        headers=headers,
    )
    assert r.status_code == 402


def test_checkout_without_stripe_configured():
    token = register_and_login("checkout@example.com")
    r = client.post(
        "/billing/checkout",
        json={"plan": "pro"},
        headers={"Authorization": f"Bearer {token}"},
    )
    # STRIPE_* absents de l'environnement de test -> message clair, pas un 500.
    assert r.status_code == 400
    assert "Stripe" in r.json()["detail"]


def test_checkout_pack5_accepted_but_demo_without_stripe():
    """Le pack ponctuel (+5 analyses, paiement unique) doit être un plan
    valide côté API, avec le même comportement démo que les autres."""
    token = register_and_login("pack5@example.com")
    r = client.post(
        "/billing/checkout",
        json={"plan": "pack5"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400
    assert "Stripe" in r.json()["detail"]


def test_cancel_subscription_without_active_sub():
    token = register_and_login("no-sub@example.com")
    r = client.post("/billing/cancel", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 400
    assert "actif" in r.json()["detail"]


def test_cancel_subscription_without_stripe_configured():
    """Un abonnement "actif" existe en base (ex: seedé manuellement / test),
    mais STRIPE_SECRET_KEY absent de l'environnement de test -> l'appel à
    Stripe échoue proprement, jamais un 500."""
    token = register_and_login("cancel-me@example.com")
    db = TestingSessionLocal()
    user = db.query(models.User).filter(models.User.email == "cancel-me@example.com").first()
    db.add(models.Subscription(
        user_id=user.id,
        stripe_subscription_id="sub_fake123",
        plan=models.PlanEnum.pro,
        status="active",
    ))
    db.commit()
    db.close()

    r = client.post("/billing/cancel", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 400, r.text
    assert "Stripe" in r.json()["detail"]


def test_analyses_requires_auth():
    r = client.post("/analyses", json={"player1_id": "x", "player2_id": "y"})
    assert r.status_code == 401


def test_register_generates_unique_referral_code():
    token = register_and_login("code-me@example.com")
    r = client.get("/referrals/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["referral_code"]
    assert len(body["referral_code"]) == 8
    assert body["referral_link"].endswith("?ref=" + body["referral_code"])
    assert body["stats"] == {
        "filleuls_abonnes": 0, "filleuls_inscrits": 0, "en_attente": 0, "analyses_bonus_gagnees": 0,
    }


def test_referral_signup_links_referrer():
    referrer_token = register_and_login("parrain@example.com")
    referrer_code = client.get(
        "/referrals/me", headers={"Authorization": f"Bearer {referrer_token}"}
    ).json()["referral_code"]

    r = client.post("/auth/register", json={
        "email": "filleul@example.com", "password": "password123", "ref_code": referrer_code,
    })
    assert r.status_code == 201, r.text

    stats = client.get(
        "/referrals/me", headers={"Authorization": f"Bearer {referrer_token}"}
    ).json()["stats"]
    assert stats == {"filleuls_abonnes": 0, "filleuls_inscrits": 1, "en_attente": 1, "analyses_bonus_gagnees": 0}


def test_referral_signup_with_unknown_code_does_not_block_registration():
    r = client.post("/auth/register", json={
        "email": "no-referrer@example.com", "password": "password123", "ref_code": "NOPE0000",
    })
    assert r.status_code == 201, r.text


def test_referral_reward_granted_on_subscription():
    """Teste directement le service (pas le webhook Stripe, trop coûteux à
    simuler ici) : quand un filleul "s'abonne", le parrain reçoit la
    récompense du plan + le palier "1er filleul abonné"."""
    from app.services.referral_service import grant_subscription_reward

    referrer_token = register_and_login("parrain2@example.com")
    referrer_code = client.get(
        "/referrals/me", headers={"Authorization": f"Bearer {referrer_token}"}
    ).json()["referral_code"]
    client.post("/auth/register", json={
        "email": "filleul2@example.com", "password": "password123", "ref_code": referrer_code,
    })

    db = TestingSessionLocal()
    referred = db.query(models.User).filter(models.User.email == "filleul2@example.com").first()
    grant_subscription_reward(db, referred, "pro")
    db.commit()
    db.close()

    stats = client.get(
        "/referrals/me", headers={"Authorization": f"Bearer {referrer_token}"}
    ).json()["stats"]
    # +20 (bonus plan pro) +10 (palier "1 filleul abonné")
    assert stats == {"filleuls_abonnes": 1, "filleuls_inscrits": 1, "en_attente": 0, "analyses_bonus_gagnees": 30}

    r = client.get("/referrals/me", headers={"Authorization": f"Bearer {referrer_token}"})
    tiers = {t["threshold"]: t["unlocked"] for t in r.json()["tiers"]}
    assert tiers[1] is True
    assert tiers[3] is False


def test_checkout_with_placeholder_stripe_keys_does_not_500(monkeypatch):
    """
    Reproduit le cas réel où quelqu'un laisse les placeholders de .env.example
    (STRIPE_SECRET_KEY=sk_test_xxx, STRIPE_PRICE_PRO=price_xxx) au lieu de
    vraies clés : Stripe est alors "configuré" (price_id non vide) mais
    l'appel réseau réel à l'API Stripe échoue. Doit rester un 400 propre,
    jamais un 500.
    """
    from app.services import stripe_service

    monkeypatch.setattr(stripe_service, "PLAN_TO_PRICE", {"pro": "price_xxx", "starter": "price_xxx", "lifetime": "price_xxx"})
    monkeypatch.setattr(stripe_service.stripe, "api_key", "sk_test_xxx")

    token = register_and_login("placeholder-stripe@example.com")
    r = client.post(
        "/billing/checkout",
        json={"plan": "pro"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400, r.text
    assert "Stripe" in r.json()["detail"]

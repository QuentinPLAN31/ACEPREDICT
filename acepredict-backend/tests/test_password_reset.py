"""
Tests du flow "Mot de passe oublié ?" : /auth/forgot-password puis
/auth/reset-password. Base SQLite en mémoire + TestClient FastAPI réels
(comme test_api_integration.py), email_service mocké (on ne veut pas de
vraie connexion SMTP dans les tests).
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
from app.security import hash_password, hash_reset_token, verify_password

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


client = TestClient(app)


@pytest.fixture(autouse=True)
def _use_this_module_db():
    """Portée la plus étroite possible (par test, avec restauration) plutôt
    qu'une affectation globale à l'import : test_api_integration.py fait une
    affectation permanente de app.dependency_overrides[get_db] au chargement
    du module, et comme pytest importe tous les fichiers de tests avant d'en
    exécuter aucun, une affectation permanente ici écraserait la sienne pour
    de bon (dernier fichier importé = dernière écriture qui gagne) et ferait
    échouer SES tests, exécutés plus tard, faute de retrouver leurs données.
    """
    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    yield
    if previous is not None:
        app.dependency_overrides[get_db] = previous
    else:
        app.dependency_overrides.pop(get_db, None)


def make_user(email="victor@example.com", password="motdepasse123"):
    db = TestingSessionLocal()
    user = models.User(email=email, hashed_password=hash_password(password), plan=models.PlanEnum.free)
    db.add(user)
    db.commit()
    db.refresh(user)
    db.close()
    return user


def test_forgot_password_unknown_email_returns_generic_message_and_sends_nothing(monkeypatch):
    """Pas de compte avec cet e-mail : même message générique, aucun envoi
    tenté (pas d'énumération de comptes possible depuis cette route)."""
    from app.services import email_service
    calls = []
    monkeypatch.setattr(email_service, "send_password_reset_email", lambda *a, **k: calls.append(a) or True)

    resp = client.post("/auth/forgot-password", json={"email": "personne@example.com"})
    assert resp.status_code == 200
    assert "Si un compte existe" in resp.json()["message"]
    assert calls == []


def test_forgot_password_known_email_stores_token_and_triggers_email(monkeypatch):
    user = make_user("reset-flow@example.com")

    from app.services import email_service
    calls = []
    monkeypatch.setattr(email_service, "send_password_reset_email", lambda to, link: calls.append((to, link)) or True)

    resp = client.post("/auth/forgot-password", json={"email": "reset-flow@example.com"})
    assert resp.status_code == 200
    assert "Si un compte existe" in resp.json()["message"]

    # BackgroundTasks s'exécute de façon synchrone avec TestClient.
    assert len(calls) == 1
    sent_to, reset_link = calls[0]
    assert sent_to == "reset-flow@example.com"
    assert "reset_token=" in reset_link

    db = TestingSessionLocal()
    refreshed = db.query(models.User).filter(models.User.id == user.id).first()
    assert refreshed.reset_token_hash is not None
    assert refreshed.reset_token_expires_at > datetime.utcnow()
    db.close()


def test_reset_password_with_valid_token_updates_password():
    user = make_user("valid-token@example.com", password="ancienMotDePasse1")
    raw_token = "test-raw-token-abc123"

    db = TestingSessionLocal()
    u = db.query(models.User).filter(models.User.id == user.id).first()
    u.reset_token_hash = hash_reset_token(raw_token)
    u.reset_token_expires_at = datetime.utcnow() + timedelta(minutes=30)
    db.commit()
    db.close()

    resp = client.post("/auth/reset-password", json={"token": raw_token, "new_password": "nouveauMotDePasse2"})
    assert resp.status_code == 200

    db = TestingSessionLocal()
    refreshed = db.query(models.User).filter(models.User.id == user.id).first()
    assert verify_password("nouveauMotDePasse2", refreshed.hashed_password)
    assert not verify_password("ancienMotDePasse1", refreshed.hashed_password)
    # Token à usage unique : invalidé après utilisation.
    assert refreshed.reset_token_hash is None
    assert refreshed.reset_token_expires_at is None
    db.close()


def test_reset_password_token_is_single_use():
    user = make_user("single-use@example.com")
    raw_token = "single-use-token-xyz"

    db = TestingSessionLocal()
    u = db.query(models.User).filter(models.User.id == user.id).first()
    u.reset_token_hash = hash_reset_token(raw_token)
    u.reset_token_expires_at = datetime.utcnow() + timedelta(minutes=30)
    db.commit()
    db.close()

    first = client.post("/auth/reset-password", json={"token": raw_token, "new_password": "premierChangement1"})
    assert first.status_code == 200

    second = client.post("/auth/reset-password", json={"token": raw_token, "new_password": "deuxiemeChangement2"})
    assert second.status_code == 400


def test_reset_password_with_expired_token_rejected():
    user = make_user("expired@example.com")
    raw_token = "expired-token-def456"

    db = TestingSessionLocal()
    u = db.query(models.User).filter(models.User.id == user.id).first()
    u.reset_token_hash = hash_reset_token(raw_token)
    u.reset_token_expires_at = datetime.utcnow() - timedelta(minutes=1)  # déjà expiré
    db.commit()
    db.close()

    resp = client.post("/auth/reset-password", json={"token": raw_token, "new_password": "nouveauMotDePasse3"})
    assert resp.status_code == 400
    assert "invalide ou expiré" in resp.json()["detail"]


def test_reset_password_with_unknown_token_rejected():
    resp = client.post("/auth/reset-password", json={"token": "ce-token-n-existe-pas", "new_password": "nouveauMotDePasse4"})
    assert resp.status_code == 400


def test_can_login_with_new_password_after_reset():
    make_user("login-after-reset@example.com", password="motDePasseInitial1")
    raw_token = "login-after-reset-token"

    db = TestingSessionLocal()
    u = db.query(models.User).filter(models.User.email == "login-after-reset@example.com").first()
    u.reset_token_hash = hash_reset_token(raw_token)
    u.reset_token_expires_at = datetime.utcnow() + timedelta(minutes=30)
    db.commit()
    db.close()

    client.post("/auth/reset-password", json={"token": raw_token, "new_password": "motDePasseTOTALEMENTnouveau1"})

    login = client.post("/auth/login", data={
        "username": "login-after-reset@example.com",
        "password": "motDePasseTOTALEMENTnouveau1",
    })
    assert login.status_code == 200
    assert "access_token" in login.json()

    old_login = client.post("/auth/login", data={
        "username": "login-after-reset@example.com",
        "password": "motDePasseInitial1",
    })
    assert old_login.status_code == 401

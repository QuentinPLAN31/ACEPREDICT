"""Programme créateurs : lien ?via=, attribution à l'inscription, commission
au premier paiement (webhook Stripe), annulation si remboursement, récap."""
import os
from datetime import datetime, timedelta

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.config import settings
from app.database import Base, get_db
from app import models
from app.services import stripe_service

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)
client = TestClient(app)
ADMIN = {"X-Admin-Token": "secret-admin"}


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(settings, "admin_token", "secret-admin")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    if previous is not None:
        app.dependency_overrides[get_db] = previous
    else:
        app.dependency_overrides.pop(get_db, None)


def webhook(monkeypatch, event):
    monkeypatch.setattr(stripe_service, "construct_webhook_event", lambda p, s: event)
    r = client.post("/billing/webhook", content=b"{}", headers={"stripe-signature": "x"})
    assert r.status_code == 200


def checkout(email, plan, sid, customer="cus_1", pi=None, amount=1900):
    return {"type": "checkout.session.completed", "data": {"object": {
        "id": sid, "customer_email": email, "customer": customer, "payment_intent": pi,
        "amount_total": amount, "metadata": {"plan": plan}, "subscription": None if pi else "sub_" + sid}}}


def make_creator(slug="tennisfan"):
    r = client.post("/creators/admin", json={"slug": slug, "name": "Tennis Fan"}, headers=ADMIN)
    assert r.status_code == 200
    return r.json()


def register(email, via=None):
    r = client.post("/auth/register", json={"email": email, "password": "motdepasse123", "via_code": via})
    assert r.status_code in (200, 201), r.text


def test_admin_requires_token():
    assert client.post("/creators/admin", json={"slug": "abc", "name": "x"}).status_code == 401


def test_full_flow_commission_upgrade_and_stats(monkeypatch):
    info = make_creator()
    assert info["link"].endswith("/?via=tennisfan")
    assert client.post("/creators/click", json={"code": "TennisFan"}).json() == {"ok": True}
    register("a@example.com", via="TennisFan")
    register("b@example.com")  # sans lien : jamais attribué

    webhook(monkeypatch, checkout("a@example.com", "pack5", "cs_1", pi="pi_1", amount=499))
    webhook(monkeypatch, checkout("a@example.com", "pack5", "cs_1", pi="pi_1", amount=499))  # redélivré
    webhook(monkeypatch, checkout("b@example.com", "pro", "cs_2", customer="cus_2"))
    db = TestingSessionLocal()
    convs = db.query(models.CreatorConversion).all()
    assert len(convs) == 1 and convs[0].commission_cents == 50
    db.close()

    # Passage au Pro dans le délai : commission montée à 3 €.
    webhook(monkeypatch, checkout("a@example.com", "pro", "cs_3"))
    db = TestingSessionLocal()
    conv = db.query(models.CreatorConversion).one()
    assert (conv.product, conv.commission_cents) == ("pro", 300)
    db.close()

    key = info["dashboard"].split("k=")[1]
    stats = client.get(f"/creators/stats/tennisfan?k={key}").json()
    assert stats["clicks_total"] == 1 and stats["signups"] == 1
    assert stats["paying_clients"] == 1 and stats["total_eur"] == 3.0
    assert stats["payable_eur"] == 0 and stats["waiting_refund_period_eur"] == 3.0
    assert client.get("/creators/stats/tennisfan?k=faux").status_code == 404


def test_refund_voids_and_payout_after_hold(monkeypatch):
    make_creator()
    register("c@example.com", via="tennisfan")
    register("d@example.com", via="tennisfan")
    webhook(monkeypatch, checkout("c@example.com", "lifetime", "cs_c", customer="cus_c", pi="pi_c", amount=9900))
    webhook(monkeypatch, checkout("d@example.com", "starter", "cs_d", customer="cus_d"))
    webhook(monkeypatch, {"type": "charge.refunded", "data": {"object": {"payment_intent": "pi_c", "customer": "cus_c"}}})

    db = TestingSessionLocal()
    for c in db.query(models.CreatorConversion).all():
        c.created_at = datetime.utcnow() - timedelta(days=31)
    db.commit()
    db.close()

    month = (datetime.utcnow() - timedelta(days=31)).strftime("%Y-%m")
    s = client.get(f"/creators/admin/summary?month={month}", headers=ADMIN).json()
    row = s["creators"][0]
    assert row["paying_clients"] == 1 and row["refunded"] == 1
    assert row["by_product"]["starter"] == 1 and row["payable_eur"] == 1.5
    assert client.post(f"/creators/admin/tennisfan/paid?month={month}", headers=ADMIN).json() == {"marked_paid": 1}
    row = client.get(f"/creators/admin/summary?month={month}", headers=ADMIN).json()["creators"][0]
    assert row["paid_eur"] == 1.5 and row["payable_eur"] == 0


def test_attribution_window_and_tier_bonus(monkeypatch):
    from app.services import creator_service as cs
    assert cs.multiplier_for(9) == 1.0 and cs.multiplier_for(10) == 1.25 and cs.multiplier_for(30) == 1.5
    make_creator()
    register("e@example.com", via="tennisfan")
    db = TestingSessionLocal()
    u = db.query(models.User).filter_by(email="e@example.com").one()
    u.creator_attributed_at = datetime.utcnow() - timedelta(days=40)
    db.commit()
    db.close()
    webhook(monkeypatch, checkout("e@example.com", "pro", "cs_e"))
    db = TestingSessionLocal()
    assert db.query(models.CreatorConversion).count() == 0
    db.close()

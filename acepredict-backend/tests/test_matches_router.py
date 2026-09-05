"""
Tests de GET /matches/upcoming et GET /matches/upcoming-list
(routers/matches.py) : depuis le refactor "synchronisation automatique",
ces deux routes lisent UNIQUEMENT la table Fixture (jamais d'appel live à
livetennis_client.py) -- cf. README "Synchronisation des données". Base
SQLite en mémoire dédiée à ce fichier, comme test_player_stats.py.
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
    """Portée par test, pas une affectation permanente au chargement du
    module -- cf. l'explication détaillée dans test_password_reset.py."""
    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    yield
    if previous is not None:
        app.dependency_overrides[get_db] = previous
    else:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture(scope="module", autouse=True)
def seed_data():
    db = TestingSessionLocal()

    alcaraz = models.Player(
        name="Carlos Alcaraz", country="ESP", tour="atp",
        data_confidence=models.DataConfidenceEnum.high, current_rank=2,
    )
    sinner = models.Player(
        name="Jannik Sinner", country="ITA", tour="atp",
        data_confidence=models.DataConfidenceEnum.high, current_rank=1,
    )
    inconnu = models.Player(
        name="Joueur Challenger", country="FRA", tour="atp",
        data_confidence=models.DataConfidenceEnum.insufficient,
    )
    wta_player1 = models.Player(name="Iga Swiatek", country="POL", tour="wta",
                                 data_confidence=models.DataConfidenceEnum.high, current_rank=1)
    wta_player2 = models.Player(name="Aryna Sabalenka", country="BLR", tour="wta",
                                 data_confidence=models.DataConfidenceEnum.high, current_rank=2)
    db.add_all([alcaraz, sinner, inconnu, wta_player1, wta_player2])
    db.commit()
    for p in (alcaraz, sinner, inconnu, wta_player1, wta_player2):
        db.refresh(p)

    now = datetime(2026, 11, 16, 18, 0, 0)
    db.add(models.Fixture(
        external_id="ltapi:atp-1", source="livetennisapi",
        player1_id=alcaraz.id, player2_id=sinner.id,
        player1_name_raw="Carlos Alcaraz", player2_name_raw="Jannik Sinner",
        tour="atp", surface="hard", indoor=True, round="F",
        tournament_name="ATP Finals", tournament_id_external="t1",
        city="Turin", scheduled_time=now,
    ))
    db.add(models.Fixture(
        external_id="ltapi:atp-2", source="livetennisapi",
        player1_id=alcaraz.id, player2_id=inconnu.id,
        player1_name_raw="Carlos Alcaraz", player2_name_raw="Joueur Challenger",
        tour="atp", surface="clay", indoor=False, round="QF",
        tournament_name="Challenger de Rennes", tournament_id_external="t2",
        city="Rennes", scheduled_time=now + timedelta(hours=2),
    ))
    db.add(models.Fixture(
        external_id="ltapi:wta-1", source="livetennisapi",
        player1_id=wta_player1.id, player2_id=wta_player2.id,
        player1_name_raw="Iga Swiatek", player2_name_raw="Aryna Sabalenka",
        tour="wta", surface="hard", indoor=False, round="F",
        tournament_name="WTA Finals", tournament_id_external="t3",
        city="Riyadh", scheduled_time=now + timedelta(hours=4),
    ))
    db.commit()

    yield {"alcaraz": alcaraz.id, "sinner": sinner.id, "inconnu": inconnu.id}
    db.close()


def test_upcoming_between_two_players_reads_fixture_table(seed_data):
    r = client.get(f"/matches/upcoming?player1_id={seed_data['alcaraz']}&player2_id={seed_data['sinner']}")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["tournament"] == "ATP Finals"
    assert data[0]["city"] == "Turin"
    assert data[0]["surface"] == "hard"
    assert data[0]["indoor"] is True


def test_upcoming_between_players_is_order_independent(seed_data):
    r = client.get(f"/matches/upcoming?player1_id={seed_data['sinner']}&player2_id={seed_data['alcaraz']}")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_upcoming_between_unknown_player_returns_404(seed_data):
    r = client.get(f"/matches/upcoming?player1_id=does-not-exist&player2_id={seed_data['sinner']}")
    assert r.status_code == 404


def test_upcoming_between_players_with_no_common_fixture_returns_empty_list(seed_data):
    r = client.get(f"/matches/upcoming?player1_id={seed_data['sinner']}&player2_id={seed_data['inconnu']}")
    assert r.status_code == 200
    assert r.json() == []


def test_upcoming_list_returns_all_tours_ordered_by_scheduled_time(seed_data):
    r = client.get("/matches/upcoming-list")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 3
    assert [m["tournament"] for m in data] == ["ATP Finals", "Challenger de Rennes", "WTA Finals"]


def test_upcoming_list_filters_by_tour(seed_data):
    r = client.get("/matches/upcoming-list?tour=wta")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["tournament"] == "WTA Finals"


def test_upcoming_list_exposes_player_ids_and_data_confidence(seed_data):
    r = client.get("/matches/upcoming-list?tour=atp")
    data = r.json()
    finals = next(m for m in data if m["tournament"] == "ATP Finals")
    assert finals["player1_id"] == seed_data["alcaraz"]
    assert finals["player1_data_confidence"] == "Fiable"
    assert finals["player2_data_confidence"] == "Fiable"

    challenger = next(m for m in data if m["tournament"] == "Challenger de Rennes")
    assert challenger["player2_id"] == seed_data["inconnu"]
    assert challenger["player2_data_confidence"] == "Données insuffisantes"
    # Auto-discovery (job horaire) garantit que le joueur existe déjà en
    # base -- toujours "analysable", contrairement à l'ancien comportement
    # basé sur l'API live où un joueur inconnu grisait le bouton.
    assert challenger["analyzable"] is True


def test_upcoming_list_respects_limit(seed_data):
    r = client.get("/matches/upcoming-list?limit=1")
    assert r.status_code == 200
    assert len(r.json()) == 1

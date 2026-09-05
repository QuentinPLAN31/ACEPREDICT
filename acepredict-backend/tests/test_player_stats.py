"""
Tests de GET /players/{id}/stats (routers/players.py :: get_player_stats) :
bilan carrière, série en cours, dernière victoire/défaite, forme récente,
titres, taux d'ace/double-fautes dérivés de l'historique de matchs (table
Match). Base SQLite en mémoire dédiée à ce fichier, comme test_api_integration.py.
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
    module -- cf. l'explication détaillée dans test_password_reset.py :
    pytest importe tous les fichiers de tests avant d'en exécuter aucun, donc
    une affectation globale ici écraserait pour de bon celle des autres
    fichiers (ex: test_api_integration.py) et ferait échouer LEURS tests,
    exécutés plus tard, faute de retrouver leurs données."""
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

    hero = models.Player(name="Rafael Nadal", country="ESP", tour="atp", elo_overall=2200)
    rival = models.Player(name="Novak Djokovic", country="SRB", tour="atp", elo_overall=2250)
    other = models.Player(name="Roger Federer", country="SUI", tour="atp", elo_overall=2150)
    lonely = models.Player(name="Joueur Sans Historique", country="FRA", tour="atp", elo_overall=1500)
    db.add_all([hero, rival, other, lonely])
    db.commit()
    for p in (hero, rival, other, lonely):
        db.refresh(p)

    roland_garros = models.Competition(name="Roland-Garros", category="grand_slam", tour="atp", season=2023)
    masters = models.Competition(name="Rome", category="masters_1000", tour="atp", season=2023)
    db.add_all([roland_garros, masters])
    db.commit()
    db.refresh(roland_garros)
    db.refresh(masters)

    # Ordre chronologique voulu (du plus ancien au plus récent) pour hero :
    #   D (vs rival)  ->  V (vs other, finale Rome, avec stats d'ace)  ->  V (vs rival, finale RG, avec stats d'ace)
    # Série en cours attendue : W, count=2. Dernière défaite : le match vs rival le plus ancien.
    db.add(models.Match(
        player1_id=hero.id, player2_id=rival.id, winner_id=rival.id,
        tourney_date=datetime(2023, 3, 1), round="QF", surface="hard",
        score="4-6 3-6", source="sackmann",
        stats={"w_ace": "10", "w_df": "2", "l_ace": "3", "l_df": "4"},
    ))
    db.add(models.Match(
        player1_id=hero.id, player2_id=other.id, winner_id=hero.id,
        tourney_date=datetime(2023, 5, 15), round="F", surface="clay",
        competition_id=masters.id, score="6-3 6-4", source="sackmann",
        stats={"w_ace": "8", "w_df": "1", "l_ace": "2", "l_df": "3"},
    ))
    db.add(models.Match(
        player1_id=hero.id, player2_id=rival.id, winner_id=hero.id,
        tourney_date=datetime(2023, 6, 11), round="F", surface="clay",
        competition_id=roland_garros.id, score="6-4 6-3 7-5", source="sackmann",
        stats={"w_ace": "12", "w_df": "3", "l_ace": "5", "l_df": "6"},
    ))
    db.commit()

    yield {"hero": hero.id, "rival": rival.id, "other": other.id, "lonely": lonely.id}
    db.close()


def test_404_for_unknown_player():
    r = client.get("/players/does-not-exist/stats")
    assert r.status_code == 404


def test_career_totals(seed_data):
    r = client.get(f"/players/{seed_data['hero']}/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["matches_played"] == 3
    assert data["wins"] == 2
    assert data["losses"] == 1
    assert data["win_rate"] == pytest.approx(2 / 3, rel=1e-3)


def test_current_streak_counts_consecutive_wins_from_most_recent(seed_data):
    r = client.get(f"/players/{seed_data['hero']}/stats")
    data = r.json()
    assert data["current_streak"] == {"type": "W", "count": 2}


def test_last_win_and_last_loss(seed_data):
    r = client.get(f"/players/{seed_data['hero']}/stats")
    data = r.json()
    assert data["last_win"]["opponent_name"] == "Novak Djokovic"
    assert data["last_win"]["tournament"] == "Roland-Garros"
    assert data["last_win"]["result"] == "W"
    assert data["last_loss"]["opponent_name"] == "Novak Djokovic"
    assert data["last_loss"]["result"] == "L"


def test_recent_form_ordered_most_recent_first(seed_data):
    r = client.get(f"/players/{seed_data['hero']}/stats")
    data = r.json()
    results = [m["result"] for m in data["recent_form"]]
    assert results == ["W", "W", "L"]


def test_titles_counted_from_final_round_wins(seed_data):
    r = client.get(f"/players/{seed_data['hero']}/stats")
    data = r.json()
    assert data["titles_count"] == 2
    tournament_names = {t["tournament"] for t in data["titles"]}
    assert tournament_names == {"Roland-Garros", "Rome"}


def test_serve_stats_averaged_from_correct_side(seed_data):
    r = client.get(f"/players/{seed_data['hero']}/stats")
    data = r.json()
    # hero est toujours player1 (côté "w_"/"l_" côté vainqueur du MATCH, pas
    # forcément hero) -- ici hero gagne 2 matchs (w_ace 8, 12) et en perd 1
    # en tant que player1 mais PERDANT du match (donc son ace count est l_ace=3).
    assert data["serve_stats"]["matches_with_data"] == 3
    assert data["serve_stats"]["avg_aces_per_match"] == round((3 + 8 + 12) / 3, 1)


def test_no_match_history_returns_zeros_and_no_serve_stats(seed_data):
    r = client.get(f"/players/{seed_data['lonely']}/stats")
    data = r.json()
    assert data["matches_played"] == 0
    assert data["wins"] == 0
    assert data["win_rate"] is None
    assert data["current_streak"] is None
    assert data["last_win"] is None
    assert data["last_loss"] is None
    assert data["serve_stats"] is None

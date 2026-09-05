"""
Tests de routers/analyses.py :: _find_matching_fixture / _weather_from_fixture
/ _market_from_fixture -- la reconstitution de `weather`/`market` à partir
d'une Fixture DÉJÀ synchronisée (scripts/sync_hourly.py), sans aucun appel
réseau (cf. README "Synchronisation des données"). Complète
test_weather_prediction.py / test_market_prediction.py qui testent
build_prediction() en aval, une fois ces dicts déjà reconstruits.
"""
import os
from datetime import datetime

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app import models
from app.routers.analyses import _find_matching_fixture, _market_from_fixture, _weather_from_fixture


def _fresh_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _two_players(db):
    p1 = models.Player(name="Carlos Alcaraz", tour="atp")
    p2 = models.Player(name="Jannik Sinner", tour="atp")
    db.add_all([p1, p2])
    db.commit()
    db.refresh(p1)
    db.refresh(p2)
    return p1, p2


def test_find_matching_fixture_returns_none_without_fixture():
    db = _fresh_session()
    p1, p2 = _two_players(db)
    assert _find_matching_fixture(db, p1.id, p2.id) is None
    db.close()


def test_find_matching_fixture_is_order_independent():
    db = _fresh_session()
    p1, p2 = _two_players(db)
    fixture = models.Fixture(
        player1_id=p1.id, player2_id=p2.id, tour="atp",
        tournament_name="ATP Finals", scheduled_time=datetime(2026, 11, 16),
    )
    db.add(fixture)
    db.commit()

    assert _find_matching_fixture(db, p1.id, p2.id) is not None
    assert _find_matching_fixture(db, p2.id, p1.id) is not None
    db.close()


def test_find_matching_fixture_prefers_tournament_name_match():
    db = _fresh_session()
    p1, p2 = _two_players(db)
    db.add(models.Fixture(
        player1_id=p1.id, player2_id=p2.id, tour="atp",
        tournament_name="Indian Wells", scheduled_time=datetime(2026, 3, 1),
    ))
    db.add(models.Fixture(
        player1_id=p1.id, player2_id=p2.id, tour="atp",
        tournament_name="ATP Finals", scheduled_time=datetime(2026, 11, 16),
    ))
    db.commit()

    found = _find_matching_fixture(db, p1.id, p2.id, tournament_name="atp finals")
    assert found.tournament_name == "ATP Finals"
    db.close()


def test_weather_from_fixture_none_when_no_fixture():
    assert _weather_from_fixture(None) is None


def test_weather_from_fixture_indoor_true_skips_temp_fields():
    fixture = models.Fixture(indoor=True)
    assert _weather_from_fixture(fixture) == {"indoor": True}


def test_weather_from_fixture_never_synced_returns_none():
    # weather_synced_at à None : jamais vérifié (pas de ville connue, ou
    # fixture pas encore passée par le job horaire) -- distinct de "vérifié,
    # rien trouvé" (cf. models.Fixture, docstring).
    fixture = models.Fixture(indoor=False, weather_synced_at=None)
    assert _weather_from_fixture(fixture) is None


def test_weather_from_fixture_synced_returns_denormalized_fields():
    fixture = models.Fixture(
        indoor=False, weather_synced_at=datetime(2026, 11, 16, 12, 0),
        weather_temp_c=18.5, weather_wind_kmh=12.0, weather_humidity_pct=60,
        weather_description="ciel dégagé",
    )
    assert _weather_from_fixture(fixture) == {
        "indoor": False, "temp_c": 18.5, "wind_kmh": 12.0, "humidity_pct": 60, "description": "ciel dégagé",
    }


def test_market_from_fixture_none_when_no_fixture():
    assert _market_from_fixture(None, "p1") is None


def test_market_from_fixture_never_synced_returns_none():
    fixture = models.Fixture(player1_id="p1", player2_id="p2", market_synced_at=None)
    assert _market_from_fixture(fixture, "p1") is None


def test_market_from_fixture_same_order_as_analysis():
    fixture = models.Fixture(
        player1_id="p1", player2_id="p2",
        market_synced_at=datetime(2026, 11, 16),
        market_player1_prob=0.6, market_player2_prob=0.4, market_question="p1 vs p2 ?",
    )
    result = _market_from_fixture(fixture, "p1")
    assert result == {"player1_prob": 0.6, "player2_prob": 0.4, "question": "p1 vs p2 ?"}


def test_market_from_fixture_reversed_order_from_analysis():
    # La Fixture a été synchronisée avec p2 comme "player1" (ordre choisi par
    # LiveTennisAPI) mais CETTE analyse a p1 comme joueur 1 -- les
    # probabilités doivent être ré-orientées, pas prises telles quelles.
    fixture = models.Fixture(
        player1_id="p2", player2_id="p1",
        market_synced_at=datetime(2026, 11, 16),
        market_player1_prob=0.6, market_player2_prob=0.4, market_question="p2 vs p1 ?",
    )
    result = _market_from_fixture(fixture, "p1")
    assert result == {"player1_prob": 0.4, "player2_prob": 0.6, "question": "p2 vs p1 ?"}

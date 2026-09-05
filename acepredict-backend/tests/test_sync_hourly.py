"""
Tests de scripts/sync_hourly.py :: run() — LiveTennisAPI/marché/météo
entièrement mockés (get_live_client, market_providers, weather_providers),
jamais de vrai appel réseau. Couvre : auto-discovery (avec/sans fiche bio
trouvée), idempotence de l'upsert Fixture, purge des fixtures disparues du
calendrier live, dénormalisation marché/météo, mise à jour des classements.
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app import models
from scripts import sync_hourly


def _fresh_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


class FakeLiveClient:
    """Remplace get_live_client() -- une instance par test, entièrement
    contrôlée (pas de httpx impliqué à ce niveau, sync_hourly.py n'appelle
    que les méthodes de LiveDataClient)."""

    def __init__(self, upcoming_by_tour=None, rankings_by_tour=None, profiles_by_name=None, city_by_tournament=None):
        self.upcoming_by_tour = upcoming_by_tour or {}
        self.rankings_by_tour = rankings_by_tour or {}
        self.profiles_by_name = profiles_by_name or {}
        self.city_by_tournament = city_by_tournament or {}

    async def get_upcoming_list(self, tour=None, limit=100):
        return self.upcoming_by_tour.get(tour, [])

    async def get_rankings(self, tour="atp"):
        return self.rankings_by_tour.get(tour, [])

    async def get_player_profile(self, name):
        return self.profiles_by_name.get(name)

    async def get_tournament_city(self, tournament_id):
        return self.city_by_tournament.get(tournament_id)


def _install_fake_client(monkeypatch, fake_client, configured=True):
    monkeypatch.setattr(sync_hourly, "is_configured", lambda: configured)
    monkeypatch.setattr(sync_hourly, "get_live_client", lambda: fake_client)


def _no_market(monkeypatch):
    class _NoMarket:
        def get_probability(self, p1, p2):
            return None
    monkeypatch.setattr(sync_hourly.market_providers, "get_market_provider", lambda: _NoMarket())


def _no_weather(monkeypatch):
    class _NoWeather:
        def get_conditions(self, city, match_date):
            return None
    monkeypatch.setattr(sync_hourly.weather_providers, "get_weather_provider", lambda: _NoWeather())


def _match(p1_name, p2_name, tour="atp", scheduled="2026-11-16T18:00:00Z", tournament_id="t1", **kw):
    m = {
        "player1_name": p1_name, "player2_name": p2_name, "tour": tour,
        "scheduled_time": scheduled, "tournament_id": tournament_id, "tournament": "Test Open",
        "surface": "Hard", "indoor": False, "round": "QF",
        "player1_country": None, "player1_ranking": None,
        "player2_country": None, "player2_ranking": None,
    }
    m.update(kw)
    return m


def test_run_returns_not_configured_when_no_api_key(monkeypatch):
    _install_fake_client(monkeypatch, FakeLiveClient(), configured=False)
    db = _fresh_session()

    report = sync_hourly.run(db=db)

    assert report["configured"] is False
    assert report["tours"] == []
    db.close()


def test_auto_discovery_creates_unknown_player_with_bio_data_as_low_confidence(monkeypatch):
    db = _fresh_session()
    db.add(models.Player(name="Carlos Alcaraz", tour="atp", data_confidence=models.DataConfidenceEnum.insufficient))
    db.commit()

    fake = FakeLiveClient(
        upcoming_by_tour={"atp": [_match("Carlos Alcaraz", "Joueur Inconnu")], "wta": []},
        profiles_by_name={"Joueur Inconnu": {"country": "FRA", "ranking": 250}},
    )
    _install_fake_client(monkeypatch, fake)
    _no_market(monkeypatch)
    _no_weather(monkeypatch)

    report = sync_hourly.run(db=db)

    inconnu = db.query(models.Player).filter(models.Player.name == "Joueur Inconnu").first()
    assert inconnu is not None
    assert inconnu.country == "FRA"
    assert inconnu.current_rank == 250
    assert inconnu.data_confidence == models.DataConfidenceEnum.low  # fiche bio trouvée, aucun match connu

    atp_report = next(t for t in report["tours"] if t["tour"] == "atp")
    assert atp_report["created_players"] == 1
    assert atp_report["upserted"] == 1
    db.close()


def test_auto_discovery_without_bio_data_marks_insufficient(monkeypatch):
    db = _fresh_session()
    db.add(models.Player(name="Carlos Alcaraz", tour="atp"))
    db.commit()

    fake = FakeLiveClient(
        upcoming_by_tour={"atp": [_match("Carlos Alcaraz", "Total Inconnu")], "wta": []},
        profiles_by_name={},  # aucune fiche trouvée nulle part
    )
    _install_fake_client(monkeypatch, fake)
    _no_market(monkeypatch)
    _no_weather(monkeypatch)

    sync_hourly.run(db=db)

    inconnu = db.query(models.Player).filter(models.Player.name == "Total Inconnu").first()
    assert inconnu is not None
    assert inconnu.data_confidence == models.DataConfidenceEnum.insufficient
    db.close()


def test_fixture_upsert_is_idempotent_across_two_runs(monkeypatch):
    db = _fresh_session()
    db.add_all([models.Player(name="Carlos Alcaraz", tour="atp"), models.Player(name="Jannik Sinner", tour="atp")])
    db.commit()

    fake = FakeLiveClient(upcoming_by_tour={"atp": [_match("Carlos Alcaraz", "Jannik Sinner")], "wta": []})
    _install_fake_client(monkeypatch, fake)
    _no_market(monkeypatch)
    _no_weather(monkeypatch)

    sync_hourly.run(db=db)
    sync_hourly.run(db=db)  # même liste live -> pas de doublon

    assert db.query(models.Fixture).count() == 1
    db.close()


def test_fixture_disappeared_from_live_calendar_is_pruned(monkeypatch):
    db = _fresh_session()
    db.add_all([models.Player(name="Carlos Alcaraz", tour="atp"), models.Player(name="Jannik Sinner", tour="atp")])
    db.commit()

    fake = FakeLiveClient(upcoming_by_tour={"atp": [_match("Carlos Alcaraz", "Jannik Sinner")], "wta": []})
    _install_fake_client(monkeypatch, fake)
    _no_market(monkeypatch)
    _no_weather(monkeypatch)
    sync_hourly.run(db=db)
    assert db.query(models.Fixture).count() == 1

    # Le match a disparu du calendrier live (annulé/reporté) au run suivant.
    fake.upcoming_by_tour["atp"] = []
    report = sync_hourly.run(db=db)

    assert db.query(models.Fixture).count() == 0
    atp_report = next(t for t in report["tours"] if t["tour"] == "atp")
    assert atp_report["pruned"] == 1
    db.close()


def test_market_and_weather_are_denormalized_on_fixture(monkeypatch):
    db = _fresh_session()
    db.add_all([models.Player(name="Carlos Alcaraz", tour="atp"), models.Player(name="Jannik Sinner", tour="atp")])
    db.commit()

    fake = FakeLiveClient(
        upcoming_by_tour={"atp": [_match("Carlos Alcaraz", "Jannik Sinner", indoor=False)], "wta": []},
        city_by_tournament={"t1": "Turin"},
    )
    _install_fake_client(monkeypatch, fake)

    class _Market:
        def get_probability(self, p1, p2):
            return {"player1_prob": 0.62, "player2_prob": 0.38, "question": "Alcaraz vs Sinner?"}
    monkeypatch.setattr(sync_hourly.market_providers, "get_market_provider", lambda: _Market())

    class _Weather:
        def get_conditions(self, city, match_date):
            assert city == "Turin"
            return {"temp_c": 18.5, "wind_kmh": 10.0, "humidity_pct": 55, "description": "ciel dégagé"}
    monkeypatch.setattr(sync_hourly.weather_providers, "get_weather_provider", lambda: _Weather())

    sync_hourly.run(db=db)

    fixture = db.query(models.Fixture).first()
    assert fixture.city == "Turin"
    assert fixture.market_player1_prob == 0.62
    assert fixture.market_synced_at is not None
    assert fixture.weather_temp_c == 18.5
    assert fixture.weather_synced_at is not None


def test_market_and_weather_stay_none_when_providers_find_nothing(monkeypatch):
    db = _fresh_session()
    db.add_all([models.Player(name="Carlos Alcaraz", tour="atp"), models.Player(name="Jannik Sinner", tour="atp")])
    db.commit()

    fake = FakeLiveClient(upcoming_by_tour={"atp": [_match("Carlos Alcaraz", "Jannik Sinner")], "wta": []})
    _install_fake_client(monkeypatch, fake)
    _no_market(monkeypatch)
    _no_weather(monkeypatch)

    sync_hourly.run(db=db)

    fixture = db.query(models.Fixture).first()
    assert fixture.market_player1_prob is None
    assert fixture.market_synced_at is None
    assert fixture.weather_temp_c is None
    assert fixture.weather_synced_at is None
    db.close()


def test_weather_is_skipped_for_indoor_matches(monkeypatch):
    db = _fresh_session()
    db.add_all([models.Player(name="Carlos Alcaraz", tour="atp"), models.Player(name="Jannik Sinner", tour="atp")])
    db.commit()

    fake = FakeLiveClient(
        upcoming_by_tour={"atp": [_match("Carlos Alcaraz", "Jannik Sinner", indoor=True)], "wta": []},
        city_by_tournament={"t1": "Turin"},
    )
    _install_fake_client(monkeypatch, fake)
    _no_market(monkeypatch)

    calls = {"n": 0}

    class _Weather:
        def get_conditions(self, city, match_date):
            calls["n"] += 1
            return {"temp_c": 18.5, "wind_kmh": 10.0, "humidity_pct": 55, "description": "x"}
    monkeypatch.setattr(sync_hourly.weather_providers, "get_weather_provider", lambda: _Weather())

    sync_hourly.run(db=db)

    assert calls["n"] == 0  # indoor -> météo non pertinente, jamais interrogée
    fixture = db.query(models.Fixture).first()
    assert fixture.weather_temp_c is None
    db.close()


def test_rankings_sync_updates_current_rank_for_matched_player(monkeypatch):
    db = _fresh_session()
    db.add(models.Player(name="Carlos Alcaraz", tour="atp"))
    db.commit()

    fake = FakeLiveClient(
        upcoming_by_tour={"atp": [], "wta": []},
        rankings_by_tour={"atp": [{"name": "Carlos Alcaraz", "ranking": 1}, {"name": "Inconnu Classement", "ranking": 2}]},
    )
    _install_fake_client(monkeypatch, fake)
    _no_market(monkeypatch)
    _no_weather(monkeypatch)

    report = sync_hourly.run(db=db)

    alcaraz = db.query(models.Player).filter(models.Player.name == "Carlos Alcaraz").first()
    assert alcaraz.current_rank == 1
    assert alcaraz.current_rank_synced_at is not None
    # "Inconnu Classement" n'existe pas encore en base -> le classement seul
    # ne déclenche PAS d'auto-discovery (réservée aux fixtures, cf. en-tête
    # du fichier) : aucun nouveau joueur créé pour autant.
    assert db.query(models.Player).count() == 1

    atp_report = next(t for t in report["tours"] if t["tour"] == "atp")
    assert atp_report["rankings_updated"] == 1
    db.close()


def test_self_match_from_ambiguous_names_is_skipped(monkeypatch):
    """Garde-fou : un fixture où player1 == player2 (résolution vers le même
    Player, ex: nom en double) ne doit jamais produire de Fixture invalide."""
    db = _fresh_session()
    db.add(models.Player(name="Carlos Alcaraz", tour="atp"))
    db.commit()

    fake = FakeLiveClient(upcoming_by_tour={"atp": [_match("Carlos Alcaraz", "Carlos Alcaraz")], "wta": []})
    _install_fake_client(monkeypatch, fake)
    _no_market(monkeypatch)
    _no_weather(monkeypatch)

    sync_hourly.run(db=db)

    assert db.query(models.Fixture).count() == 0
    db.close()

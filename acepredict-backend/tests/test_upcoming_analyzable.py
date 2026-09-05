"""
Teste l'annotation `analyzable` de GET /matches/upcoming-list (cf.
routers/matches.py::_annotate_analyzable) : la page "Matchs à venir" remonte
tous les niveaux du circuit (ATP jusqu'aux petits tournois ITF/Challenger),
alors que notre base ne contient que le circuit principal — le frontend a
besoin de savoir, par match, si les deux joueurs sont bien en base, pour
griser le bouton "Analyser" au lieu de laisser cliquer dans le vide.

Vraie base SQLite en mémoire (pas de mock sur la requête SQLAlchemy).
"""
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker

from app import models
from app.database import Base
from app.routers.matches import _annotate_analyzable

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


def make_db():
    db = TestingSessionLocal()
    db.add_all([
        models.Player(name="Novak Djokovic", country="SRB", tour="atp", elo_overall=2200),
        models.Player(name="Carlos Alcaraz", country="ESP", tour="atp", elo_overall=2150),
    ])
    db.commit()
    return db


def test_both_players_known_marks_analyzable_true():
    db = make_db()
    matches = [{"player1_name": "Novak Djokovic", "player2_name": "Carlos Alcaraz"}]
    out = _annotate_analyzable(db, matches)
    assert out[0]["analyzable"] is True
    db.close()


def test_unknown_player_marks_analyzable_false():
    db = make_db()
    matches = [{"player1_name": "Novak Djokovic", "player2_name": "Oliwier Sterniczuk"}]
    out = _annotate_analyzable(db, matches)
    assert out[0]["analyzable"] is False
    db.close()


def test_both_players_unknown_marks_analyzable_false():
    db = make_db()
    matches = [{"player1_name": "Joueur Inconnu 1", "player2_name": "Joueur Inconnu 2"}]
    out = _annotate_analyzable(db, matches)
    assert out[0]["analyzable"] is False
    db.close()


def test_name_matching_is_case_insensitive():
    db = make_db()
    matches = [{"player1_name": "novak djokovic", "player2_name": "CARLOS ALCARAZ"}]
    out = _annotate_analyzable(db, matches)
    assert out[0]["analyzable"] is True
    db.close()


def test_missing_player_name_marks_analyzable_false():
    db = make_db()
    matches = [{"player1_name": "Novak Djokovic", "player2_name": None}]
    out = _annotate_analyzable(db, matches)
    assert out[0]["analyzable"] is False
    db.close()


def test_annotation_does_not_mutate_or_drop_other_fields():
    db = make_db()
    matches = [{
        "player1_name": "Novak Djokovic", "player2_name": "Carlos Alcaraz",
        "tournament": "US Open", "surface": "hard",
    }]
    out = _annotate_analyzable(db, matches)
    assert out[0]["tournament"] == "US Open"
    assert out[0]["surface"] == "hard"
    assert "analyzable" not in matches[0]  # la liste d'entrée n'est pas mutée
    db.close()


def test_empty_list_returns_empty_list():
    db = make_db()
    assert _annotate_analyzable(db, []) == []
    db.close()

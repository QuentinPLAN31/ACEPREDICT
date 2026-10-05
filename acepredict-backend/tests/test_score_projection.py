from types import SimpleNamespace

import pytest

from app.services.score_projection import (
    build_score_projection, score_distribution, set_win_prob, _match_prob_from_set_prob,
)


@pytest.mark.parametrize("n", [2, 3])
@pytest.mark.parametrize("p", [0.5, 0.62, 0.8, 0.95])
def test_distribution_sums_to_one_and_reproduces_match_prob(p, n):
    dist = score_distribution(p, n)
    assert sum(d["probability"] for d in dist) == pytest.approx(1.0)
    fav = sum(d["probability"] for d in dist if d["side"] == "favorite")
    assert fav == pytest.approx(p, abs=1e-3)


def test_set_win_prob_is_monotone():
    assert set_win_prob(0.6, 2) < set_win_prob(0.8, 2) < set_win_prob(0.95, 2)
    assert _match_prob_from_set_prob(set_win_prob(0.7, 3), 3) == pytest.approx(0.7, abs=1e-3)


def test_projection_without_history_uses_default_and_best_of_5():
    w = SimpleNamespace(id="a", name="Alcaraz")
    l = SimpleNamespace(id="b", name="Sinner")
    proj = build_score_projection(None, w, l, 0.75, "hard", best_of_5=True)
    assert proj["best_of"] == 5
    assert proj["most_likely"]["score"].startswith("3-")
    assert proj["total_games"]["source"] == "default"
    assert proj["total_games"]["low"] < proj["total_games"]["expected"] < proj["total_games"]["high"]
    assert len(proj["scenarios"]) == 4


def test_projection_uses_real_game_counts_from_history():
    from datetime import datetime, timedelta
    from sqlalchemy import create_engine, StaticPool
    from sqlalchemy.orm import sessionmaker
    from app.database import Base
    from app import models

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    a = models.Player(name="Joueur A", tour="atp")
    b = models.Player(name="Joueur B", tour="atp")
    db.add_all([a, b]); db.commit(); db.refresh(a); db.refresh(b)
    # Matchs très serrés : 7-6 7-6 (13 jeux/set), un match abandonné ignoré.
    for i in range(8):
        db.add(models.Match(player1_id=a.id, player2_id=b.id, winner_id=a.id, score="7-6(4) 7-6(3)",
                            tourney_date=datetime.utcnow() - timedelta(days=i)))
    db.add(models.Match(player1_id=a.id, player2_id=b.id, winner_id=a.id, score="6-0 2-0 RET",
                        tourney_date=datetime.utcnow()))
    db.commit()

    proj = build_score_projection(db, a, b, 0.6, None, best_of_5=False)
    tg = proj["total_games"]
    assert tg["source"] == "history"
    assert tg["games_per_set"] == pytest.approx(13.0)
    assert tg["expected"] > 26  # beaucoup plus que la moyenne générique (~9.6/set)


def test_projection_includes_alternate_format():
    from app.services import score_projection
    w = SimpleNamespace(id="a", name="A")
    l = SimpleNamespace(id="b", name="B")
    r = score_projection.build_score_projection(None, w, l, 0.7, None, False)
    assert r["best_of"] == 3 and {s["score"] for s in r["scenarios"]} <= {"2-0", "2-1"}
    alt = r["alt"]
    assert alt["best_of"] == 5 and {s["score"] for s in alt["scenarios"]} <= {"3-0", "3-1", "3-2"}
    assert abs(sum(s["probability"] for s in alt["scenarios"]) - 1) < 0.05 or len(alt["scenarios"]) == 4
    r5 = score_projection.build_score_projection(None, w, l, 0.7, None, True)
    assert r5["best_of"] == 5 and r5["alt"]["best_of"] == 3

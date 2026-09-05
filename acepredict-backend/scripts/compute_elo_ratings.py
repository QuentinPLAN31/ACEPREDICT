"""
Job offline batch : recalcule les ratings Elo (global + par surface) de tous
les joueurs à partir des matchs en base, triés chronologiquement, et les
écrit sur players.elo_* (+ trace dans elo_history).

Usage :
    python -m scripts.compute_elo_ratings

A lancer après chaque ingestion (scripts/ingest_sackmann.py) ou périodiquement
via un cron/worker une fois de nouveaux résultats live intégrés.
"""
import sys

from sqlalchemy import nullslast

from app.database import SessionLocal
from app import models
from app.services.elo import EloEngine


def run(db=None) -> int:
    owns_session = db is None
    db = db or SessionLocal()
    try:
        matches = (
            db.query(models.Match)
            .filter(models.Match.winner_id.isnot(None))
            .order_by(nullslast(models.Match.tourney_date.asc()))
            .all()
        )

        engine = EloEngine()
        for m in matches:
            loser_id = m.player2_id if m.winner_id == m.player1_id else m.player1_id
            engine.process_match(
                winner_key=m.winner_id,
                loser_key=loser_id,
                surface=m.surface.value if m.surface else None,
            )

        updated = 0
        for player_id, rating in engine.ratings.items():
            player = db.query(models.Player).filter(models.Player.id == player_id).first()
            if not player:
                continue
            player.elo_overall = round(rating.overall, 2)
            player.elo_hard = round(rating.by_surface["hard"], 2)
            player.elo_clay = round(rating.by_surface["clay"], 2)
            player.elo_grass = round(rating.by_surface["grass"], 2)
            updated += 1

        db.commit()
        return updated
    finally:
        if owns_session:
            db.close()


if __name__ == "__main__":
    n = run()
    print(f"{n} joueurs mis à jour avec leurs nouveaux ratings Elo")
    sys.exit(0)

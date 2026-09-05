"""
Remplace les données de démo (42 matchs fictifs) par de vraies données ATP
2023-2026 (source publique Jeff Sackmann, licence CC BY-NC-SA — usage
NON-COMMERCIAL uniquement, voir data/real/ pour la licence complète).

Vide players / competitions / matches / elo_history / analyses puis
réingère les 4 saisons réelles et recalcule l'Elo.

Usage : python -m scripts.refresh_real_data
"""
import sys

from app.database import SessionLocal
from app import models
from scripts.ingest_sackmann import ingest_csv
from scripts import compute_elo_ratings

REAL_FILES = [
    "data/real/atp_matches_2023.csv",
    "data/real/atp_matches_2024.csv",
    "data/real/atp_matches_2025.csv",
    "data/real/atp_matches_2026.csv",
]


def run() -> None:
    db = SessionLocal()
    try:
        print("[refresh_real_data] Nettoyage des données de démo...")
        db.query(models.Analysis).delete()
        db.query(models.EloHistory).delete()
        db.query(models.Match).delete()
        db.query(models.Competition).delete()
        db.query(models.Player).delete()
        db.commit()

        total = 0
        for path in REAL_FILES:
            n = ingest_csv(path, tour="atp", db=db)
            print(f"[refresh_real_data] {path} -> {n} matchs importés.")
            total += n
        print(f"[refresh_real_data] Total : {total} matchs réels (saisons 2023-2026).")

        updated = compute_elo_ratings.run(db=db)
        print(f"[refresh_real_data] {updated} joueurs avec ratings Elo à jour.")

        top = (
            db.query(models.Player)
            .order_by(models.Player.elo_overall.desc())
            .limit(10)
            .all()
        )
        print("\n[refresh_real_data] Top 10 Elo actuel :")
        for i, p in enumerate(top, 1):
            print(f"  {i}. {p.name} ({p.country}) — {round(p.elo_overall)} Elo")
    finally:
        db.close()


if __name__ == "__main__":
    run()
    sys.exit(0)

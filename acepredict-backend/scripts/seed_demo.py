"""
Orchestration de démarrage : applique les migrations puis peuple la base
avec les données de démo (échantillon Sackmann + Elo) si elle est vide.

Idempotent — safe à lancer à chaque démarrage du conteneur (docker-compose
l'appelle avant uvicorn) : si des matchs existent déjà, l'ingestion est
sautée pour ne jamais dupliquer les données.

Usage : python -m scripts.seed_demo
"""
import subprocess
import sys

from app.database import SessionLocal
from app import models
from app.services import data_confidence
from scripts.ingest_sackmann import ingest_csv
from scripts import compute_elo_ratings

SAMPLE_CSV = "data/sample/atp_matches_sample.csv"


def run() -> None:
    print("[seed_demo] Application des migrations Alembic...")
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)

    db = SessionLocal()
    try:
        existing = db.query(models.Match).count()
        if existing > 0:
            print(f"[seed_demo] Base déjà peuplée ({existing} matchs) — ingestion sautée.")
            return

        print(f"[seed_demo] Base vide — ingestion de {SAMPLE_CSV}...")
        n = ingest_csv(SAMPLE_CSV, tour="atp", db=db)
        print(f"[seed_demo] {n} matchs importés.")

        updated = compute_elo_ratings.run(db=db)
        print(f"[seed_demo] {updated} joueurs mis à jour (ratings Elo).")

        # Sans cet appel, get_or_create_player() (ingest_sackmann.py) laisse
        # data_confidence à sa valeur par défaut la plus pessimiste
        # ("insufficient", cf. models.Player) pour TOUS les joueurs importés
        # ici -- même ceux qui ont un historique de matchs dans cet
        # échantillon. Un joueur découvert plus tard par sync_hourly.py (0
        # match connu chez nous) affichait alors un badge MEILLEUR qu'un
        # joueur déjà présent dans data/sample/. Même logique que
        # scripts/sync_daily.py, qui fait cet appel après chaque ingestion.
        changed = data_confidence.recompute_all(db)
        print(f"[seed_demo] {changed} niveau(x) de confiance des données recalculé(s).")
    finally:
        db.close()


if __name__ == "__main__":
    run()

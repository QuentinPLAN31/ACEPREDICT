"""
Script de MAINTENANCE : efface le classement (current_rank) de tous les
joueurs classés au-delà de la 100e place, pour les deux tours. Suite
logique de l'abandon du scraping de classement (scripts/
apply_manual_rankings.py) -- on ne veut plus que des rangs > 100 (issus de
l'ancien scraping, potentiellement obsolètes) traînent et se mélangent au
top 100 officiel saisi manuellement.

Ne supprime AUCUNE fiche joueur : met juste current_rank et
current_rank_synced_at à NULL. Le joueur redevient "non classé" (n'apparaît
plus dans le classement par défaut, mais reste trouvable par recherche et
garde tout son historique de matchs/Elo).

Usage :
    python -m scripts.clear_ranks_beyond_100
    python -m scripts.clear_ranks_beyond_100 --dry-run
"""
import sys

from app import models
from app.database import SessionLocal


def run(dry_run: bool = False) -> dict:
    db = SessionLocal()
    try:
        report = {}
        for tour in (models.TourEnum.atp, models.TourEnum.wta):
            q = db.query(models.Player).filter(
                models.Player.tour == tour,
                models.Player.current_rank.isnot(None),
                models.Player.current_rank > 100,
            )
            count = q.count()
            report[tour.value if hasattr(tour, "value") else str(tour)] = count
            if not dry_run:
                q.update({"current_rank": None, "current_rank_synced_at": None}, synchronize_session=False)
        if not dry_run:
            db.commit()
        return report
    finally:
        db.close()


def main():
    dry_run = "--dry-run" in sys.argv
    report = run(dry_run=dry_run)
    mode = "SIMULATION (--dry-run, rien n'a été modifié)" if dry_run else "APPLIQUÉ"
    for tour, count in report.items():
        print(f"[clear_ranks_beyond_100] {mode} -- {tour.upper()} : {count} joueur(s) au-delà du top 100 effacé(s) du classement.")


if __name__ == "__main__":
    sys.exit(main())

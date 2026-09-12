"""
Script de MAINTENANCE (à lancer une fois) : supprime les pseudo-fiches
"joueur" créées par erreur pour une PAIRE de double (ex. "Dabrowski /
Stefani"), à cause du parsing générique de scripts/services/
scrape_provider.py qui récupérait aussi le tableau de classement en double
présent sur la même page HTML (corrigé désormais -- cf. le filtre sur "/"
dans _parse_ranking_page). Ne supprime que si la fiche n'a AUCUNE référence
ailleurs (Match/Fixture/EloHistory/Analysis) -- sinon elle est laissée en
l'état et signalée, par prudence.

Usage :
    python -m scripts.cleanup_doubles_pseudo_players
    python -m scripts.cleanup_doubles_pseudo_players --dry-run
"""
import sys

from app import models
from app.database import SessionLocal


def _reference_count(db, player_id) -> int:
    n = 0
    n += db.query(models.Match).filter(
        (models.Match.player1_id == player_id)
        | (models.Match.player2_id == player_id)
        | (models.Match.winner_id == player_id)
    ).count()
    n += db.query(models.Fixture).filter(
        (models.Fixture.player1_id == player_id) | (models.Fixture.player2_id == player_id)
    ).count()
    n += db.query(models.EloHistory).filter(models.EloHistory.player_id == player_id).count()
    n += db.query(models.Analysis).filter(
        (models.Analysis.player1_id == player_id)
        | (models.Analysis.player2_id == player_id)
        | (models.Analysis.predicted_winner_id == player_id)
    ).count()
    return n


def run(dry_run: bool = False) -> dict:
    db = SessionLocal()
    try:
        candidates = db.query(models.Player).filter(models.Player.name.ilike("%/%")).all()
        report = {"deleted": 0, "skipped_referenced": []}
        for p in candidates:
            refs = _reference_count(db, p.id)
            if refs > 0:
                report["skipped_referenced"].append((p.name, refs))
                continue
            report["deleted"] += 1
            if not dry_run:
                db.delete(p)
        if not dry_run:
            db.commit()
        return report
    finally:
        db.close()


def main():
    dry_run = "--dry-run" in sys.argv
    report = run(dry_run=dry_run)
    mode = "SIMULATION (--dry-run, rien n'a été modifié)" if dry_run else "APPLIQUÉ"
    print(f"[cleanup_doubles_pseudo_players] {mode} : {report['deleted']} pseudo-fiche(s) de double supprimée(s).")
    if report["skipped_referenced"]:
        print("  Non supprimées (référencées ailleurs, à vérifier manuellement) :")
        for name, refs in report["skipped_referenced"]:
            print(f"    - {name} ({refs} référence(s))")


if __name__ == "__main__":
    sys.exit(main())

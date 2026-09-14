"""
Script de MAINTENANCE (à lancer UNE fois) : nettoie les dégâts causés par
la tentative (revenue en arrière depuis, cf. git log sur sync_hourly.py)
d'inclure tour="challenger" côté ATP -- cette catégorie de l'API tierce
s'est révélée mixte hommes/femmes (des tournois comme Valencia, Caldas da
Rainha, Szczecin contiennent en réalité des tableaux des deux genres, tous
étiquetés "challenger"), ce qui a fait entrer des JOUEUSES dans notre base
avec tour="atp" et créé des Fixture tour="atp" pour des matchs 100% féminins.

Deux étapes :
  1. Supprime TOUTES les Fixture tour="atp" actuelles (un simple cache du
     calendrier live, sans valeur historique -- se re-remplit proprement au
     prochain sync_hourly, désormais revenu à un fetch atp/wta strict).
  2. Supprime les Player tour="atp" créés par cet épisode : sackmann_id
     NULL (jamais importés depuis l'historique Sackmann -- donc forcément
     auto-découverts, pas de vraie fiche ATP historique) ET current_rank >
     100 (les 100 premiers ATP viennent de scripts/apply_manual_rankings.py,
     saisis à la main le même jour -- on ne les touche pas) ET aucune
     référence ailleurs (Match/EloHistory/Analysis -- les Fixture viennent
     d'être supprimées à l'étape 1, donc déjà hors course). Par prudence,
     les fiches encore référencées quelque part sont laissées et juste
     signalées.

Usage :
    python -m scripts.cleanup_challenger_gender_mixup
    python -m scripts.cleanup_challenger_gender_mixup --dry-run
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
        report = {"fixtures_deleted": 0, "players_deleted": 0, "players_skipped_referenced": []}

        fixtures = db.query(models.Fixture).filter(models.Fixture.tour == "atp").all()
        report["fixtures_deleted"] = len(fixtures)
        if not dry_run:
            for f in fixtures:
                db.delete(f)
            db.commit()

        candidates = db.query(models.Player).filter(
            models.Player.tour == "atp",
            models.Player.sackmann_id.is_(None),
            models.Player.current_rank.isnot(None),
            models.Player.current_rank > 100,
        ).all()
        for p in candidates:
            refs = _reference_count(db, p.id)
            if refs > 0:
                report["players_skipped_referenced"].append((p.name, refs))
                continue
            report["players_deleted"] += 1
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
    print(
        f"[cleanup_challenger_gender_mixup] {mode} : {report['fixtures_deleted']} fixture(s) ATP "
        f"supprimée(s), {report['players_deleted']} fiche(s) mal-genrée(s) supprimée(s)."
    )
    if report["players_skipped_referenced"]:
        print("  Non supprimées (référencées ailleurs, à vérifier manuellement) :")
        for name, refs in report["players_skipped_referenced"]:
            print(f"    - {name} ({refs} référence(s))")


if __name__ == "__main__":
    sys.exit(main())

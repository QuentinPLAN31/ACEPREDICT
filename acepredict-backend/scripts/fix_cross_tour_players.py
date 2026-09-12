"""
Script de MAINTENANCE (à lancer une fois, puis au besoin) : corrige les
joueuses WTA importées par erreur avec tour="atp" (bug historique dans
scripts/ingest_sackmann.py, probablement lancé sur un fichier de matchs WTA
sans passer --tour wta -- son défaut est "atp"). Conséquence en cascade :
chaque joueuse concernée a DEUX fiches en base --
  1. l'originale, mal taguée tour="atp", mais avec tout son historique
     Sackmann (sackmann_id, matchs, Elo...) ;
  2. une fiche neuve, correctement taguée tour="wta" mais SANS historique,
     créée après coup par scripts/sync_rankings_daily.py quand celui-ci n'a
     pas trouvé la vraie fiche (normal : il ne cherche que parmi les
     joueuses déjà tour="wta").
Conséquence visible : classement "Joueurs" qui mélange des noms d'hommes et
de femmes au même rang, doublons, incohérences.

Principe : on utilise le classement WTA (puis ATP, par symétrie/sécurité)
RÉELLEMENT SCRAPÉ EN DIRECT (app/services/scrape_provider.fetch_rankings)
comme source de vérité -- une joueuse qui apparaît dans le classement WTA
mondial actuel ne peut PAS être un joueur ATP. Pour chaque nom scrapé
WTA qui correspond (par ensemble de mots, accents retirés) à une fiche
tour="atp" :
  - si une fiche tour="wta" correspondante existe aussi (le "doublon
    neuf" créé par erreur) : on GARDE la fiche "atp" (elle a l'historique),
    on lui bascule tour="wta", on réattribue toutes les références de la
    fiche wta vers elle, puis on supprime la fiche wta ;
  - sinon : on bascule simplement son tour à "wta".
Aucune perte de données (mêmes garanties de réattribution de FK que
scripts/dedupe_players.py).

Usage :
    python -m scripts.fix_cross_tour_players            # applique
    python -m scripts.fix_cross_tour_players --dry-run   # simulation
"""
import asyncio
import re
import sys
import unicodedata

from app import models
from app.database import SessionLocal
from app.services import scrape_provider


def _norm_words(name: str) -> frozenset:
    if not name:
        return frozenset()
    txt = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return frozenset(w for w in re.split(r"[\s\-/]+", txt.lower()) if w)


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


def _reassign(db, old_id, new_id) -> None:
    db.query(models.Match).filter(models.Match.player1_id == old_id).update({"player1_id": new_id})
    db.query(models.Match).filter(models.Match.player2_id == old_id).update({"player2_id": new_id})
    db.query(models.Match).filter(models.Match.winner_id == old_id).update({"winner_id": new_id})
    db.query(models.Fixture).filter(models.Fixture.player1_id == old_id).update({"player1_id": new_id})
    db.query(models.Fixture).filter(models.Fixture.player2_id == old_id).update({"player2_id": new_id})
    db.query(models.EloHistory).filter(models.EloHistory.player_id == old_id).update({"player_id": new_id})
    db.query(models.Analysis).filter(models.Analysis.player1_id == old_id).update({"player1_id": new_id})
    db.query(models.Analysis).filter(models.Analysis.player2_id == old_id).update({"player2_id": new_id})
    db.query(models.Analysis).filter(models.Analysis.predicted_winner_id == old_id).update({"predicted_winner_id": new_id})


async def _fix_for_tour(db, true_tour: str, wrong_tour: str, dry_run: bool) -> dict:
    """true_tour = le tour où le joueur devrait réellement être classé
    (déduit du classement scrapé en direct) ; wrong_tour = le tour où sa
    fiche historique a été mal taguée."""
    report = {"fixed": 0, "merged_shells_deleted": 0}
    ranking_names = await scrape_provider.fetch_rankings(true_tour)
    if not ranking_names:
        return report

    wrong_candidates = db.query(models.Player).filter(models.Player.tour == wrong_tour).all()
    wrong_by_words = {}
    for p in wrong_candidates:
        key = _norm_words(p.name)
        if key:
            wrong_by_words.setdefault(key, []).append(p)

    true_candidates = db.query(models.Player).filter(models.Player.tour == true_tour).all()
    true_by_words = {}
    for p in true_candidates:
        key = _norm_words(p.name)
        if key:
            true_by_words.setdefault(key, []).append(p)

    for item in ranking_names:
        name = item.get("name")
        if not name:
            continue
        key = _norm_words(name)
        if not key:
            continue
        mistagged = wrong_by_words.get(key)
        if not mistagged or len(mistagged) != 1:
            continue  # absent ou ambigu -- on ne devine pas
        wrong_player = mistagged[0]

        shell_group = true_by_words.get(key)
        if shell_group and len(shell_group) == 1:
            shell = shell_group[0]
            if shell.id == wrong_player.id:
                continue
            report["merged_shells_deleted"] += 1
            if not dry_run:
                if not wrong_player.country and shell.country:
                    wrong_player.country = shell.country
                if wrong_player.current_rank is None and shell.current_rank is not None:
                    wrong_player.current_rank = shell.current_rank
                    wrong_player.current_rank_synced_at = shell.current_rank_synced_at
                _reassign(db, shell.id, wrong_player.id)
                db.delete(shell)
                wrong_player.tour = true_tour
        else:
            if not dry_run:
                wrong_player.tour = true_tour
        report["fixed"] += 1

    if not dry_run:
        db.commit()
    return report


async def run(dry_run: bool = False) -> dict:
    db = SessionLocal()
    try:
        report = {}
        # Le cas observé (des joueuses WTA taguées "atp") ; on vérifie aussi
        # le sens inverse par sécurité/symétrie, au cas où le même bug
        # d'ingestion se soit produit dans l'autre sens.
        report["wta_mistagged_as_atp"] = await _fix_for_tour(db, "wta", "atp", dry_run)
        report["atp_mistagged_as_wta"] = await _fix_for_tour(db, "atp", "wta", dry_run)
        return report
    finally:
        db.close()


def main():
    dry_run = "--dry-run" in sys.argv
    report = asyncio.run(run(dry_run=dry_run))
    mode = "SIMULATION (--dry-run, rien n'a été modifié)" if dry_run else "APPLIQUÉ"
    for key, r in report.items():
        print(f"[fix_cross_tour_players] {mode} -- {key} : {r['fixed']} fiche(s) corrigée(s) "
              f"(dont {r['merged_shells_deleted']} fusionnée(s) avec un doublon neuf supprimé).")


if __name__ == "__main__":
    sys.exit(main())

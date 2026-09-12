"""
Script de MAINTENANCE (à lancer une fois, après le correctif du calcul de
round dans app/services/scrape_provider.py et de l'idempotence dans
scripts/sync_draws_daily.py) : supprime les Match EN DOUBLE créés par
l'ancien bug -- un même match (compétition + paire de joueurs) recréé
plusieurs fois sous des rounds différents (ex: une fois en "R128", une
autre fois en "QF") parce que le round recalculé changeait d'un scraping à
l'autre tant que le tableau du tournoi n'était pas terminé.

Principe : pour chaque compétition, regroupe les Match (source="scrape")
par paire de joueurs (ordre indifférent). Pour chaque groupe de >1 ligne,
garde une seule ligne ("keeper") -- priorité au round le plus "avancé"
dans le tournoi (proche de la finale), qui correspond généralement au
dernier calcul (le plus fiable, fait avec le plus de colonnes visibles) --
et supprime les autres. Ne touche PAS aux Match source="sackmann"
(historique importé, jamais concerné par ce bug).

Usage :
    python -m scripts.dedupe_match_rounds            # applique la fusion
    python -m scripts.dedupe_match_rounds --dry-run   # simulation
"""
import sys

from app import models
from app.database import SessionLocal

_ROUND_ORDER = ["R128", "R64", "R32", "R16", "QF", "SF", "F"]


def _round_rank(round_code: str) -> int:
    try:
        return _ROUND_ORDER.index(round_code)
    except ValueError:
        return -1  # round inconnu/absent -> le moins prioritaire


def run(dry_run: bool = False) -> dict:
    db = SessionLocal()
    try:
        report = {"groups_merged": 0, "matches_deleted": 0}
        competitions = db.query(models.Competition).all()
        for comp in competitions:
            matches = (
                db.query(models.Match)
                .filter(models.Match.competition_id == comp.id, models.Match.source == "scrape")
                .all()
            )
            groups: dict[frozenset, list] = {}
            for m in matches:
                key = frozenset((m.player1_id, m.player2_id))
                groups.setdefault(key, []).append(m)

            for group in groups.values():
                if len(group) < 2:
                    continue
                scored = sorted(group, key=lambda m: _round_rank(m.round), reverse=True)
                keeper = scored[0]
                dupes = scored[1:]
                for dup in dupes:
                    if not dry_run:
                        # Réattribue au cas où un EloHistory/Analysis pointerait
                        # déjà sur ce match précis (rare mais possible).
                        db.query(models.EloHistory).filter(models.EloHistory.match_id == dup.id).update(
                            {"match_id": keeper.id}
                        )
                        db.delete(dup)
                report["groups_merged"] += 1
                report["matches_deleted"] += len(dupes)

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
        f"[dedupe_match_rounds] {mode} : {report['groups_merged']} groupe(s) de doublons fusionné(s), "
        f"{report['matches_deleted']} match(s) en double supprimé(s)."
    )


if __name__ == "__main__":
    sys.exit(main())

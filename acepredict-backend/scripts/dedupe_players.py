"""
Script de MAINTENANCE (à lancer une fois, puis au besoin) : fusionne les
joueurs EN DOUBLE créés par le classement scrapé (scripts/sync_rankings_daily.py)
quand le rapprochement par nom échouait -- chaque échec créait une NOUVELLE
fiche Player au lieu de mettre à jour la fiche existante, ce qui a fait
exploser le nombre de "joueurs classés" affichés (classement WTA passé de
~400 à ~1200 lignes, avec d'énormes trous de rang) sans qu'aucun nouveau
joueur n'existe réellement en double.

Principe : regroupe les Player d'un même tour par ENSEMBLE DE MOTS du nom
(accents retirés, insensible à la casse/ordre) -- "Jannik Sinner" et
"Sinner Jannik" tombent dans le même groupe, tout comme les variantes
accentuées ("Paštiková" / "Pastikova"). Pour chaque groupe de >1 fiche,
GARDE une seule fiche ("keeper") et réattribue vers elle toutes les
références en base (Match, Fixture, EloHistory, Analysis) avant de
supprimer les doublons -- aucune perte de données historique.

Choix du keeper (par ordre de priorité) :
  1. sackmann_id renseigné (= fiche d'origine de l'import historique, celle
     qui a le vrai historique de matchs) ;
  2. le plus de lignes déjà référencées ailleurs (Match/Fixture/EloHistory/
     Analysis) ;
  3. country renseigné ;
  4. sinon, arbitraire (le premier du groupe).
Les autres fiches du groupe sont fusionnées dedans (country/current_rank
copiés si absents chez le keeper) puis supprimées.

Usage :
    python -m scripts.dedupe_players            # applique la fusion
    python -m scripts.dedupe_players --dry-run   # simulation, rien n'est écrit
"""
import sys
import unicodedata

from app import models
from app.database import SessionLocal


def _norm_words(name: str) -> frozenset:
    if not name:
        return frozenset()
    txt = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return frozenset(w for w in txt.lower().replace("-", " ").split() if w)


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


def run(dry_run: bool = False) -> dict:
    db = SessionLocal()
    try:
        report = {"groups_merged": 0, "players_deleted": 0}
        for tour in (models.TourEnum.atp, models.TourEnum.wta):
            players = db.query(models.Player).filter(models.Player.tour == tour).all()
            groups: dict[frozenset, list] = {}
            for p in players:
                key = _norm_words(p.name)
                if not key:
                    continue
                groups.setdefault(key, []).append(p)

            for group in groups.values():
                if len(group) < 2:
                    continue
                scored = sorted(
                    group,
                    key=lambda p: (
                        1 if p.sackmann_id else 0,
                        _reference_count(db, p.id),
                        1 if p.country else 0,
                    ),
                    reverse=True,
                )
                keeper = scored[0]
                dupes = scored[1:]
                for dup in dupes:
                    if not keeper.country and dup.country:
                        keeper.country = dup.country
                    if keeper.current_rank is None and dup.current_rank is not None:
                        keeper.current_rank = dup.current_rank
                        keeper.current_rank_synced_at = dup.current_rank_synced_at
                    if not dry_run:
                        _reassign(db, dup.id, keeper.id)
                        db.delete(dup)
                report["groups_merged"] += 1
                report["players_deleted"] += len(dupes)

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
        f"[dedupe_players] {mode} : {report['groups_merged']} groupe(s) de doublons fusionné(s), "
        f"{report['players_deleted']} fiche(s) en double supprimée(s)."
    )


if __name__ == "__main__":
    sys.exit(main())

# A lancer via railway ssh: PYTHONPATH=/app python3 -m scripts.check_rankings_coverage
#
# L'annuaire "Joueurs" (classement general) affiche encore beaucoup de
# trous meme apres le fix de tri (players.py, sort=rank) -- ce script
# verifie si le probleme est cote DONNEES (des rangs jamais synchronises
# du tout en base, ou des doublons qui "consomment" un rang sans etre le
# bon joueur) plutot que cote tri.
from app import models
from app.database import SessionLocal


def main():
    db = SessionLocal()
    try:
        for tour in (models.TourEnum.atp, models.TourEnum.wta):
            players = (
                db.query(models.Player)
                .filter(models.Player.tour == tour, models.Player.current_rank.isnot(None))
                .order_by(models.Player.current_rank.asc())
                .all()
            )
            print(f"\n=== {tour.upper() if hasattr(tour,'upper') else tour} : {len(players)} joueur(s) avec un current_rank connu ===")
            ranks = [p.current_rank for p in players]
            if not ranks:
                print("  Aucun joueur classe du tout.")
                continue
            print(f"  Rang min={min(ranks)}, max={max(ranks)}")
            # Trous dans la sequence 1..100 (les rangs qu'on s'attend a voir
            # dans l'annuaire "top" affiche par defaut).
            present = set(ranks)
            missing = [r for r in range(1, 101) if r not in present]
            print(f"  Rangs manquants entre 1 et 100 ({len(missing)}) : {missing}")
            # Doublons de rang (2 joueurs seraient marques au meme rang --
            # ne devrait jamais arriver, chaque rang ATP/WTA est unique).
            dupe_ranks = {}
            for p in players:
                dupe_ranks.setdefault(p.current_rank, []).append(p.name)
            dupes = {r: names for r, names in dupe_ranks.items() if len(names) > 1 and r <= 100}
            if dupes:
                print(f"  ATTENTION -- rangs dupliques (<=100) : {dupes}")
            # last synced_at spread : un sync partiel/ancien ?
            synced_ats = [p.current_rank_synced_at for p in players if p.current_rank_synced_at]
            if synced_ats:
                print(f"  current_rank_synced_at : min={min(synced_ats)}, max={max(synced_ats)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()

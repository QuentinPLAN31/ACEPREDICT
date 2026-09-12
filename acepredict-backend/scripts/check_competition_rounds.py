# A lancer via railway ssh:
#   PYTHONPATH=/app python3 -m scripts.check_competition_rounds
#
# Diagnostic : le frontend (onglet Matchs/Tableau) filtre maintenant "1 bouton
# = 1 tour", et sur l'US Open (finale demain), le filtre "Huitièmes" affiche
# "Aucun match ne correspond à ce filtre" -- ce script montre EXACTEMENT ce
# qu'il y a en base (table Match ET table Fixture) round par round pour cette
# compétition, pour savoir si c'est un trou de données (sync incomplète) ou
# un comportement normal (round pas encore synchronisé / matchs de ce tour
# jamais stockés).
from collections import Counter

from app import models
from app.database import SessionLocal


def main():
    db = SessionLocal()
    try:
        comps = (
            db.query(models.Competition)
            .filter(models.Competition.name.ilike("%us open%"))
            .filter(models.Competition.tour == models.TourEnum.atp)
            .all()
        )
        if not comps:
            print("Aucune compétition 'US Open' (ATP) trouvée en base.")
            return
        for comp in comps:
            print(f"\n=== Competition: {comp.name} | tour={comp.tour} | saison={comp.season} | id={comp.id} ===")

            matches = db.query(models.Match).filter(models.Match.competition_id == comp.id).all()
            print(f"-- table Match (matchs joués, historique) : {len(matches)} ligne(s)")
            by_round_m = Counter((m.round or "?") for m in matches)
            for r, n in sorted(by_round_m.items()):
                print(f"     {r}: {n}")

            # Fixture n'a pas de FK competition_id direct -- rapprochement par
            # tournament_name (cf. app/models.py Fixture) et saison approximative
            # via scheduled_time.
            fixtures = (
                db.query(models.Fixture)
                .filter(models.Fixture.tournament_name.ilike(f"%{comp.name}%"))
                .all()
            )
            print(f"-- table Fixture (à venir/synchro horaire) : {len(fixtures)} ligne(s)")
            by_round_f = Counter((f.round or "?") for f in fixtures)
            for r, n in sorted(by_round_f.items()):
                print(f"     {r}: {n}")
            no_winner = sum(1 for m in matches if not m.winner_id)
            print(f"-- Match sans winner_id (ne devrait normalement jamais arriver) : {no_winner}")
    finally:
        db.close()


if __name__ == "__main__":
    main()

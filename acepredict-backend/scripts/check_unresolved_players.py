# A lancer via railway ssh: PYTHONPATH=/app python3 -m scripts.check_unresolved_players
#
# 4 matchs de Huitièmes de l'US Open 2026 manquent sur le site (confirmé
# contre le tableau officiel) : Khachanov-Tien, Cerundolo-Blockx,
# Shelton-Tsitsipás, Paul-Alcaraz. sync_draws_daily.py les ignore car
# _find_player_for_tour() échoue à rapprocher au moins un des deux noms à
# une fiche Player -- ce script teste précisément CES noms pour voir
# pourquoi (aucune fiche trouvée ? plusieurs candidats ambigus ?).
import re

from app import models
from app.database import SessionLocal


def _match_surname_in_name(scraped_name, full_name):
    surname = (scraped_name or "").strip().lower()
    if not surname or len(surname) < 3:
        return False
    return bool(re.search(r"\b" + re.escape(surname) + r"\b", (full_name or "").lower()))


NAMES_TO_CHECK = ["Khachanov", "Tien", "Cerundolo", "Blockx", "Shelton", "Tsitsipas", "Paul", "Alcaraz"]


def main():
    db = SessionLocal()
    try:
        candidates = db.query(models.Player).filter(models.Player.tour == models.TourEnum.atp).all()
        print(f"{len(candidates)} joueur(s) ATP en base au total.\n")
        for name in NAMES_TO_CHECK:
            matches = [p for p in candidates if _match_surname_in_name(name, p.name)]
            print(f"'{name}' -> {len(matches)} match(es) : {[(p.name, p.id) for p in matches]}")
    finally:
        db.close()


if __name__ == "__main__":
    main()

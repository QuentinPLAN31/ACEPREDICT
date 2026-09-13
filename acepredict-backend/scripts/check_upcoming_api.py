"""
Diagnostic : interroge DIRECTEMENT l'API tierce de matchs à venir
(app.services.livetennis_client.get_live_client().get_upcoming_list) pour
les deux tours, sans passer par la base de données -- pour savoir si le
déséquilibre ATP (1 match) / WTA (67 matchs) vient :
  a) d'un vrai calendrier ATP creux cette semaine (rien à faire, normal) ;
  b) d'un problème d'appel/filtrage côté notre code (bug à corriger) ;
  c) d'une couverture différente de l'API tierce selon le tour (ATP top
     tour uniquement vs WTA qui inclut aussi des tournois $125K, etc.).

Affiche, pour chaque tour, le nombre total de matchs renvoyés et la liste
des tournois distincts rencontrés (avec leur nombre de matchs).

Usage :
    python -m scripts.check_upcoming_api
"""
import asyncio
from collections import Counter

from app.services.livetennis_client import get_live_client


async def run():
    client = get_live_client()
    for tour in ("atp", "wta"):
        matches = await client.get_upcoming_list(tour=tour, limit=200)
        tournaments = Counter(m.get("tournament") for m in matches)
        print(f"\n=== {tour.upper()} : {len(matches)} match(s) renvoyé(s) par l'API ===")
        for name, count in tournaments.most_common():
            print(f"    {name!r} : {count}")
        if not matches:
            print("    (aucun match)")


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()

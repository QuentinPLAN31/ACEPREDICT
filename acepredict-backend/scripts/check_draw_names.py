# A lancer via railway ssh: PYTHONPATH=/app python3 -m scripts.check_draw_names
#
# Les 4 matchs manquants (Khachanov-Tien, Cerundolo-Blockx, Shelton-Tsitsipas,
# Paul-Alcaraz) échouent tous à cause d'un nom de famille AMBIGU (plusieurs
# joueurs partagent ce nom en base : 2 Tien, 2 Cerundolo -- frères --,
# 2 Tsitsipas -- frères --, 3 Paul). Ce script affiche le texte EXACT que
# fetch_draw() extrait de tennisexplorer.com pour ces joueurs (avec ou sans
# initiale du prénom ?) afin de savoir si on peut les distinguer par ce texte
# ou s'il faut départager autrement (ex: classement ATP).
import asyncio

from app.services import scrape_provider as sp

NEEDLES = ["tien", "cerundolo", "paul", "tsitsip", "khachanov", "blockx", "shelton", "alcaraz"]


async def main():
    entries = await sp.fetch_draw("atp", "US Open", 2026)
    print(f"{len(entries)} entrée(s) au total dans le tableau scrapé.\n")
    for e in entries:
        p1, p2, w = e["player1_name"], e["player2_name"], e["winner_name"]
        blob = f"{p1}|{p2}".lower()
        if any(n in blob for n in NEEDLES):
            print(f"  round={e['round']:>5}  '{p1}'  vs  '{p2}'   (gagnant scrapé: '{w}')")


asyncio.run(main())

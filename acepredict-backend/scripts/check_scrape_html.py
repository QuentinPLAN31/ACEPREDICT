# A lancer via railway ssh: PYTHONPATH=/app python3 check_scrape_html.py
#
# Le scraping tennisexplorer.com (app/services/scrape_provider.py) a été
# écrit sans pouvoir tester contre le vrai HTML (accès réseau direct
# bloqué depuis l'environnement où il a été écrit). Ce script :
#   1. affiche ce que fetch_rankings()/fetch_results_for_date() parsent
#      RÉELLEMENT une fois exécutés depuis Railway (qui, lui, a un accès
#      réseau normal) ;
#   2. si le résultat est vide ou visiblement faux, dump aussi un extrait
#      du HTML brut pour que je puisse corriger les sélecteurs.
# Colle-moi la sortie complète.
import asyncio
from datetime import date, timedelta

import httpx

from app.services import scrape_provider as sp


async def main():
    print("=== fetch_rankings('atp') ===")
    rankings = await sp.fetch_rankings("atp")
    print(f"{len(rankings)} ligne(s) parsée(s)")
    for r in rankings[:10]:
        print(" ", r)

    print("\n=== fetch_results_for_date('atp', hier) ===")
    yesterday = date.today() - timedelta(days=1)
    results = await sp.fetch_results_for_date("atp", yesterday)
    print(f"{len(results)} match(s) parsé(s) pour {yesterday}")
    for r in results[:10]:
        print(" ", r)

    if not rankings:
        print("\n=== HTML brut (classement ATP) -- 3000 premiers caractères ===")
        async with httpx.AsyncClient(timeout=15, headers=sp._HEADERS, follow_redirects=True) as client:
            r = await client.get(f"{sp.BASE_URL}/ranking/atp-men/")
            print(f"HTTP {r.status_code}")
            print(r.text[:3000])

    if not results:
        print("\n=== HTML brut (résultats du jour) -- 3000 premiers caractères ===")
        async with httpx.AsyncClient(timeout=15, headers=sp._HEADERS, follow_redirects=True) as client:
            r = await client.get(
                f"{sp.BASE_URL}/results/",
                params={"type": "atp-single", "year": yesterday.year, "month": yesterday.month, "day": yesterday.day},
            )
            print(f"HTTP {r.status_code}")
            print(r.text[:3000])


asyncio.run(main())

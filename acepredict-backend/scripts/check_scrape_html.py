# A lancer via railway ssh: PYTHONPATH=/app python3 scripts/check_scrape_html.py
#
# Le scraping tennisexplorer.com (app/services/scrape_provider.py) a été
# écrit sans pouvoir tester contre le vrai HTML (accès réseau direct
# bloqué depuis l'environnement où il a été écrit). Ce script affiche ce
# que fetch_rankings()/fetch_draw() parsent RÉELLEMENT une fois exécutés
# depuis Railway. Colle-moi la sortie complète.
import asyncio
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from app import models
from app.database import SessionLocal
from app.services import scrape_provider as sp


async def main():
    print("=== fetch_rankings('atp') ===")
    rankings = await sp.fetch_rankings("atp")
    print(f"{len(rankings)} ligne(s) parsée(s)")
    for r in rankings[:10]:
        print(" ", r)

    # Le champ 'country' n'a JAMAIS été rempli par _parse_ranking_page --
    # au lieu de re-deviner un sélecteur à l'aveugle, on imprime le HTML
    # BRUT de la ligne du #1 mondial pour voir la vraie structure du
    # drapeau/pays et corriger le parsing avec certitude.
    print("\n=== HTML brut de la ligne #1 (pour corriger l'extraction du pays) ===")
    async with httpx.AsyncClient(timeout=15, headers=sp._HEADERS, follow_redirects=True) as client:
        r = await client.get(f"{sp.BASE_URL}/ranking/atp-men/")
        soup = BeautifulSoup(r.text, "html.parser")
        found = False
        for table in soup.find_all("table"):
            for tr in table.find_all("tr"):
                cells = tr.find_all("td")
                if cells and cells[0].get_text(strip=True).rstrip(".").isdigit():
                    print(tr.prettify()[:3000])
                    found = True
                    break
            if found:
                break

    if not rankings:
        print("\n=== HTML brut (classement ATP) -- 3000 premiers caractères ===")
        async with httpx.AsyncClient(timeout=15, headers=sp._HEADERS, follow_redirects=True) as client:
            r = await client.get(f"{sp.BASE_URL}/ranking/atp-men/")
            print(f"HTTP {r.status_code}")
            print(r.text[:3000])

    print("\n=== fetch_draw() pour les tournois en cours connus en base ===")
    db = SessionLocal()
    try:
        current_year = datetime.utcnow().year
        comps = (
            db.query(models.Competition)
            .filter((models.Competition.season == None) | (models.Competition.season >= current_year))  # noqa: E711
            .all()
        )
        matched = [c for c in comps if sp._slug_for_competition(c.name or "")]
        print(f"{len(comps)} compétition(s) en base cette saison, {len(matched)} reconnue(s) dans TOURNAMENT_SLUGS :")
        for c in matched:
            print(f"  - {c.name} ({c.tour}, saison {c.season})")
        for c in matched[:2]:
            entries = await sp.fetch_draw(c.tour, c.name, c.season or current_year)
            print(f"\n--- fetch_draw('{c.tour}', '{c.name}', {c.season or current_year}) ---")
            print(f"{len(entries)} match(es) déjà joué(s) déduit(s) du tableau")
            for e in entries[:15]:
                print(" ", e)
    finally:
        db.close()


asyncio.run(main())

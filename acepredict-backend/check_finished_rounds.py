# A lancer via railway ssh: PYTHONPATH=/app python3 check_finished_rounds.py
#
# Pourquoi les boutons "1er tour / 2e tour / quarts..." semblent vides sur
# un tournoi EN COURS (ex: US Open pendant le tournoi) : les matchs à venir
# (table Fixture, synchronisés depuis LiveTennisAPI) sont PURGÉS une fois
# joués (cf. scripts/sync_hourly.py, STALE_AFTER) SANS jamais être
# transformés en résultat permanent (table Match). Résultat : dès qu'un tour
# est terminé, ses matchs disparaissent purement et simplement du site — il
# ne reste que les tours pas encore joués. Les boutons de filtre par tour ne
# sont donc pas cassés, ils reflètent honnêtement des données absentes.
#
# Pour corriger ça il faut que sync_hourly.py sauvegarde le résultat (score,
# vainqueur) d'un match dès qu'il est terminé, au lieu de juste supprimer sa
# Fixture -- mais je n'ai aucune visibilité depuis ici sur la forme exacte
# de la réponse d'un match "terminé" chez LiveTennisAPI (quel champ contient
# le score, le vainqueur, quelle valeur de "status" un match fini renvoie).
# Ce script interroge l'API avec plusieurs valeurs de "status" plausibles et
# affiche le JSON brut du premier match trouvé pour chacune -- colle-moi le
# résultat, ça me donnera tout ce qu'il faut pour écrire le vrai correctif.
import asyncio
import json

import httpx

from app.config import settings

BASE_URL = settings.livetennisapi_base_url
API_KEY = settings.livetennisapi_key


async def try_status(status: str):
    headers = {"Authorization": f"Bearer {API_KEY}"} if API_KEY else {}
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            r = await client.get(f"{BASE_URL}/matches", params={"status": status, "tour": "atp", "limit": 5}, headers=headers)
            print(f"\n=== status={status!r} -> HTTP {r.status_code} ===")
            if r.status_code != 200:
                print(r.text[:500])
                return
            data = r.json()
            items = data.get("data", data) if isinstance(data, dict) else data
            print(f"{len(items)} résultat(s). Premier match brut :")
            if items:
                print(json.dumps(items[0], indent=2, ensure_ascii=False, default=str)[:2000])
        except Exception as e:
            print(f"\n=== status={status!r} -> ERREUR : {e!r} ===")


async def main():
    if not BASE_URL:
        print("LIVETENNISAPI_BASE_URL n'est pas configuré -- rien à interroger.")
        return
    for status in ("finished", "completed", "ended", "past", "live"):
        await try_status(status)


asyncio.run(main())

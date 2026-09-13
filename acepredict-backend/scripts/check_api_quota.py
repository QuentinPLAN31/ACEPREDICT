"""
Diagnostic : fait UN appel direct à l'API tierce et affiche le code HTTP /
message d'erreur brut, sans l'avaler -- pour confirmer si "0 match reçu"
vient d'un quota journalier épuisé (429/403) ou d'autre chose.

Usage :
    python -m scripts.check_api_quota
"""
import asyncio

import httpx

from app.config import settings


async def run():
    headers = {"Authorization": f"Bearer {settings.livetennisapi_key}"} if settings.livetennisapi_key else {}
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{settings.livetennisapi_base_url}/matches",
            params={"status": "upcoming", "tour": "wta", "limit": 5},
            headers=headers,
        )
    print("Status code :", r.status_code)
    print("Corps de la réponse (premiers 500 caractères) :")
    print(r.text[:500])


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()

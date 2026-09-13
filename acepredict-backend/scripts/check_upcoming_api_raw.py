"""
Diagnostic (suite de check_upcoming_api.py) : appelle l'API tierce SANS
filtre `tour=` pour voir toutes les valeurs de "tour" qu'elle renvoie
réellement -- afin de vérifier si des matchs ATP existent bien mais sous un
libellé différent de "atp" (auquel cas notre filtre `params["tour"]=tour`
les raterait), ou si l'API n'a vraiment que ça côté ATP en ce moment.

Usage :
    python -m scripts.check_upcoming_api_raw
"""
import asyncio
from collections import Counter

import httpx

from app.config import settings


async def run():
    headers = {"Authorization": f"Bearer {settings.livetennisapi_key}"} if settings.livetennisapi_key else {}
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{settings.livetennisapi_base_url}/matches",
            params={"status": "upcoming", "limit": 200},
            headers=headers,
        )
        r.raise_for_status()
        raw = r.json()
    matches = raw.get("data", raw) if isinstance(raw, dict) else raw
    print(f"Total matchs renvoyés (sans filtre tour) : {len(matches)}")
    tours = Counter(m.get("tour") for m in matches)
    print("Répartition par valeur brute de 'tour' :")
    for tour_val, count in tours.most_common():
        print(f"    {tour_val!r} : {count}")
    tournaments = Counter((m.get("tour"), m.get("tournament")) for m in matches)
    print("\nDétail tour/tournoi :")
    for (tour_val, name), count in tournaments.most_common(30):
        print(f"    tour={tour_val!r} tournoi={name!r} : {count}")


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()

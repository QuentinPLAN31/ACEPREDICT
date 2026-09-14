"""
Diagnostic : dump BRUT (toutes les clés, pas seulement celles que
livetennis_client.py extrait) de quelques matchs tour="challenger", pour
voir si l'API fournit un champ exploitable pour distinguer hommes/femmes
dans cette catégorie (ex. "gender", "category", "event_type"...) qu'on
n'utilise pas encore. Si un tel champ existe et est fiable, on pourra
réintégrer le Challenger côté Hommes en filtrant dessus ; sinon, on
laisse tomber cette piste (cf. cleanup_challenger_gender_mixup.py).

Usage :
    python -m scripts.check_challenger_gender_field
"""
import asyncio
import json

import httpx

from app.config import settings


async def run():
    headers = {"Authorization": f"Bearer {settings.livetennisapi_key}"} if settings.livetennisapi_key else {}
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{settings.livetennisapi_base_url}/matches",
            params={"status": "upcoming", "tour": "challenger", "limit": 5},
            headers=headers,
        )
        r.raise_for_status()
        raw = r.json()
    matches = raw.get("data", raw) if isinstance(raw, dict) else raw
    print(f"{len(matches)} match(s) bruts reçus (tour=challenger) :\n")
    for m in matches:
        print(json.dumps(m, indent=2, ensure_ascii=False))
        print("---")


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()

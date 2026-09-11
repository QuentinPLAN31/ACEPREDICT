"""
Job de synchronisation QUOTIDIEN (1×/jour, idéalement la nuit) : classement
ATP/WTA -> Player.current_rank.

Source : scraping (app/services/scrape_provider.py, tennisexplorer.com),
PAS LiveTennisAPI -- le classement est de toute façon une donnée qui ne
bouge pas d'heure en heure (les tours eux-mêmes ne le republient qu'1×/
semaine), donc pas besoin de la faire peser sur un quota API limité.
LiveTennisAPI reste utilisé ailleurs (fixtures à venir, cotes, météo, cf.
scripts/sync_hourly.py) -- ce script-ci n'y touche plus du tout, ce qui
libère entièrement le quota côté classement.

Usage :
    python -m scripts.sync_rankings_daily

À planifier dans Railway comme un cron job séparé de sync_hourly (ex. tous
les jours à 03h00 UTC) -- Railway > service backend > Settings > Cron
Schedule, ou un second service "Cron Job" pointant sur cette commande.
"""
import sys
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app import models
from app.database import SessionLocal
from app.services import data_confidence, scrape_provider

TOURS = ("atp", "wta")


def _find_player(db: Session, name: str) -> Optional[models.Player]:
    if not name or not name.strip():
        return None
    return db.query(models.Player).filter(models.Player.name.ilike(name.strip())).first()


async def _sync_rankings(db: Session, tour: str, stats: Optional[dict] = None) -> int:
    """Met à jour Player.current_rank depuis le classement scrapé. Crée
    aussi la fiche des joueurs classés mais absents de notre base (au lieu
    de les ignorer silencieusement) -- sans ça, seul un joueur DÉJÀ connu
    par ailleurs (via une fixture à venir, un match historique...) pouvait
    recevoir un classement, ce qui laissait un classement très troué --
    notamment côté WTA, moins bien couverte que l'ATP par LiveTennisAPI
    pour les matchs à venir (donc moins de joueuses auto-découvertes par
    ce biais)."""
    items = await scrape_provider.fetch_rankings(tour)
    local_stats = stats if stats is not None else {"created_players": 0}

    updated = 0
    now = datetime.utcnow()
    for item in items or []:
        name = item.get("name")
        rank = item.get("rank")
        if not name or not rank:
            continue
        player = _find_player(db, name)
        if player:
            player.current_rank = rank
            player.current_rank_synced_at = now
        else:
            country = item.get("country")
            player = models.Player(name=name.strip(), tour=tour, country=country or None)
            player.current_rank = rank
            player.current_rank_synced_at = now
            has_bio = data_confidence.has_bio_signal(player)
            player.data_confidence = data_confidence.compute_confidence(0, has_bio_data=has_bio)
            db.add(player)
            local_stats["created_players"] += 1
        updated += 1
    db.commit()
    return updated


async def _run_async(db: Session) -> dict:
    report = {"tours": []}
    for tour in TOURS:
        stats = {"created_players": 0}
        updated = await _sync_rankings(db, tour, stats)
        report["tours"].append({"tour": tour, "rankings_updated": updated, **stats})
    return report


def run(db: Session | None = None) -> dict:
    import asyncio
    owns_session = db is None
    db = db or SessionLocal()
    try:
        return asyncio.run(_run_async(db))
    finally:
        if owns_session:
            db.close()


def main():
    report = run()
    for t in report["tours"]:
        print(
            f"[sync_rankings_daily] {t['tour'].upper()} : {t['rankings_updated']} classement(s) mis à jour, "
            f"{t['created_players']} joueur(s) découvert(s)."
        )
        if t["rankings_updated"] == 0:
            print(
                f"[sync_rankings_daily] ATTENTION : 0 résultat pour {t['tour'].upper()} -- "
                f"la structure HTML de tennisexplorer.com a peut-être changé, "
                f"ou le scraping est bloqué. Lancer scripts/check_scrape_html.py pour diagnostiquer."
            )


if __name__ == "__main__":
    sys.exit(main())

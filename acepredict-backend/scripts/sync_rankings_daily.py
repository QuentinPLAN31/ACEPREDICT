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
import re
import sys
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app import models
from app.database import SessionLocal
from app.services import data_confidence, scrape_provider

TOURS = ("atp", "wta")


def _name_words(name: str) -> set[str]:
    return {w for w in re.split(r"[\s\-]+", (name or "").strip().lower()) if w}


def _build_player_index(db: Session, tour: str) -> list[models.Player]:
    return db.query(models.Player).filter(models.Player.tour == tour).all()


def _find_player(scraped_name: str, candidates: list[models.Player]) -> Optional[models.Player]:
    """tennisexplorer affiche le classement au format 'Nom Prénom' (ex.
    'Sinner Jannik'), alors que notre base stocke la plupart du temps
    'Prénom Nom' (import historique Sackmann) -- un match EXACT (ilike)
    ratait donc quasi tous les joueurs déjà connus, ce qui créait un
    DOUBLON pour chacun (nouvelle fiche sans pays/photo/historique) au lieu
    de simplement mettre à jour son rang -- c'est ce qui expliquait à la
    fois des classements qui ne bougeaient pas (le doublon fraîchement créé
    n'était pas forcément celui affiché ailleurs) et des fiches incomplètes
    ('?' pour le pays, initiales à la place de la photo) même pour des
    joueurs top 10 déjà bien renseignés chez nous. On compare désormais par
    ENSEMBLE de mots (l'ordre n'a plus d'importance), puis, à défaut, par
    nom de famille seul (1er mot du format tennisexplorer) si ça désigne un
    unique joueur -- jamais de devinette en cas d'ambiguïté."""
    if not scraped_name or not scraped_name.strip():
        return None
    target = _name_words(scraped_name)
    if not target:
        return None
    exact = [p for p in candidates if _name_words(p.name) == target]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return None  # ambigu -- on ne devine pas

    surname = scraped_name.strip().split()[0]
    if len(surname) >= 3:
        surname_matches = [
            p for p in candidates
            if re.search(r"\b" + re.escape(surname.lower()) + r"\b", (p.name or "").lower())
        ]
        if len(surname_matches) == 1:
            return surname_matches[0]
    return None


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
    candidates = _build_player_index(db, tour)

    updated = 0
    now = datetime.utcnow()
    for item in items or []:
        name = item.get("name")
        rank = item.get("rank")
        if not name or not rank:
            continue
        player = _find_player(name, candidates)
        if player:
            player.current_rank = rank
            player.current_rank_synced_at = now
            # Rétro-comble le pays s'il manquait -- ne JAMAIS écraser une
            # valeur déjà connue (l'import historique est plus fiable que
            # le scraping, qui rate encore le pays sur beaucoup de lignes).
            if not player.country and item.get("country"):
                player.country = item.get("country")
        else:
            country = item.get("country")
            player = models.Player(name=name.strip(), tour=tour, country=country or None)
            player.current_rank = rank
            player.current_rank_synced_at = now
            has_bio = data_confidence.has_bio_signal(player)
            player.data_confidence = data_confidence.compute_confidence(0, has_bio_data=has_bio)
            db.add(player)
            db.flush()
            candidates.append(player)
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

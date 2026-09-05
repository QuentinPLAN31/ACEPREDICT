"""
Job de synchronisation HORAIRE : matchs à venir (fixtures), classements et,
pour chaque fixture, cotes de marché + météo — tout est écrit en base (table
Fixture, players.current_rank) pour que le site ne fasse plus JAMAIS d'appel
direct à une API externe depuis une requête utilisateur (cf. README
"Synchronisation des données").

Usage :
    python -m scripts.sync_hourly

Pour chaque tour (atp, wta) :
  1. Récupère le classement (LiveTennisAPI) -> met à jour Player.current_rank.
  2. Récupère la liste des prochains matchs (LiveTennisAPI) -> upsert Fixture
     par joueur, avec AUTO-DISCOVERY : un joueur absent de notre base est
     créé à la volée, puis on tente une fiche bio via LiveTennisAPI (SEULE
     "source secondaire" disponible ici sans clé ni scraping fragile —
     TennisExplorer et l'ITF n'exposent aucune API publique/gratuite
     exploitable ; LiveTennisAPI couvre déjà lui-même le Challenger/ITF,
     cf. son propre descriptif). Sans rien trouver, data_confidence =
     "insufficient" plutôt que de bloquer quoi que ce soit — la fiche existe
     quand même, juste marquée comme telle (cf. services/data_confidence.py).
  3. Pour chaque fixture, résout la ville du tournoi (une fois par tournoi,
     mise en cache par livetennis_client.py), puis récupère cotes de marché
     (Polymarket) + météo et les dénormalise sur la ligne.
  4. Supprime les Fixture de ce tour qui n'apparaissent plus dans le
     calendrier live actuel (match annulé/reporté) ou dont la date
     programmée est trop ancienne (déjà jouées).

Dégradation gracieuse à chaque étage (LiveTennisAPI/Polymarket/météo non
configurés ou en panne) — jamais d'exception qui interrompt le job entier
pour une source indisponible ; chaque étage manquant se traduit juste par
des champs laissés à None sur la Fixture concernée.
"""
import asyncio
import hashlib
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app import models
from app.database import SessionLocal
from app.services import data_confidence, market_providers, weather_providers
from app.services.livetennis_client import get_live_client, is_configured

TOURS = ("atp", "wta")
FIXTURE_LIST_LIMIT = 200

# Une Fixture dont la date programmée est dépassée depuis plus longtemps que
# ça est considérée jouée/obsolète — purgée pour ne pas laisser grossir la
# table indéfiniment (routers/matches.py ne renvoie de toute façon que les
# fixtures futures, mais autant nettoyer à la source).
STALE_AFTER = timedelta(days=2)

_SURFACE_VALUES = {s.value for s in models.SurfaceEnum}


def _normalize_surface(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    val = raw.strip().lower()
    return val if val in _SURFACE_VALUES else None


def _parse_scheduled_time(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        return None


def _external_id_for(tour: str, p1_name: str, p2_name: str, scheduled_time_raw: Optional[str]) -> str:
    """LiveTennisAPI ne renvoie pas d'id de match stable dans la liste large
    (get_upcoming_list) — on dérive un identifiant déterministe à partir de
    (tour, joueurs, horaire programmé), suffisant pour un upsert idempotent
    d'une exécution horaire à l'autre (cf. Fixture.external_id)."""
    basis = f"{tour}|{p1_name.strip().lower()}|{p2_name.strip().lower()}|{scheduled_time_raw or ''}"
    return "ltapi:" + hashlib.sha1(basis.encode("utf-8")).hexdigest()[:24]


def _find_player(db: Session, name: str) -> Optional[models.Player]:
    if not name or not name.strip():
        return None
    return db.query(models.Player).filter(models.Player.name.ilike(name.strip())).first()


async def _auto_discover_player(db: Session, name: str, tour: str, country: Optional[str],
                                  ranking: Optional[int], stats: dict) -> models.Player:
    """Crée la fiche d'un joueur inconnu, tente de l'enrichir via
    LiveTennisAPI (seule source secondaire disponible, cf. en-tête du
    fichier), et fixe data_confidence en conséquence — jamais bloquant."""
    player = models.Player(name=name.strip(), tour=tour, country=country or None)
    if ranking:
        player.current_rank = ranking
        player.current_rank_synced_at = datetime.utcnow()

    profile = None
    try:
        profile = await get_live_client().get_player_profile(name)
    except Exception:
        profile = None

    if profile:
        if not player.country and profile.get("country"):
            player.country = profile.get("country")
        if not player.hand and profile.get("hand"):
            player.hand = profile.get("hand")
        rank_from_profile = profile.get("ranking") or profile.get("rank")
        if player.current_rank is None and rank_from_profile:
            player.current_rank = rank_from_profile
            player.current_rank_synced_at = datetime.utcnow()

    has_bio = data_confidence.has_bio_signal(player)
    player.data_confidence = data_confidence.compute_confidence(0, has_bio_data=has_bio)

    db.add(player)
    db.flush()
    stats["created_players"] += 1
    return player


async def _resolve_player(db: Session, name: Optional[str], tour: str, country: Optional[str],
                            ranking: Optional[int], stats: dict) -> Optional[models.Player]:
    if not name or not name.strip():
        return None
    existing = _find_player(db, name)
    if existing:
        if ranking:
            existing.current_rank = ranking
            existing.current_rank_synced_at = datetime.utcnow()
        return existing
    return await _auto_discover_player(db, name, tour, country, ranking, stats)


async def _sync_rankings(db: Session, tour: str) -> int:
    try:
        rankings = await get_live_client().get_rankings(tour=tour)
    except Exception:
        return 0
    items = rankings.get("data", rankings) if isinstance(rankings, dict) else rankings

    updated = 0
    now = datetime.utcnow()
    for item in items or []:
        name = item.get("name")
        rank = item.get("ranking") or item.get("rank")
        if not name or not rank:
            continue
        player = _find_player(db, name)
        if player:
            player.current_rank = rank
            player.current_rank_synced_at = now
            updated += 1
    db.commit()
    return updated


async def _sync_fixtures_for_tour(db: Session, tour: str) -> dict:
    stats = {
        "tour": tour, "fetched": 0, "created_players": 0, "upserted": 0,
        "pruned": 0, "market_found": 0, "weather_found": 0,
    }
    try:
        matches = await get_live_client().get_upcoming_list(tour=tour, limit=FIXTURE_LIST_LIMIT)
    except Exception:
        return stats
    stats["fetched"] = len(matches)

    city_cache: dict[str, Optional[str]] = {}
    seen_external_ids: set[str] = set()

    for m in matches:
        p1_name, p2_name = m.get("player1_name"), m.get("player2_name")
        if not p1_name or not p2_name:
            continue

        p1 = await _resolve_player(db, p1_name, tour, m.get("player1_country"), m.get("player1_ranking"), stats)
        p2 = await _resolve_player(db, p2_name, tour, m.get("player2_country"), m.get("player2_ranking"), stats)
        if not p1 or not p2 or p1.id == p2.id:
            continue

        scheduled_time_raw = m.get("scheduled_time")
        external_id = _external_id_for(tour, p1_name, p2_name, scheduled_time_raw)
        seen_external_ids.add(external_id)

        tournament_id = m.get("tournament_id")
        city = None
        if tournament_id:
            if tournament_id not in city_cache:
                try:
                    city_cache[tournament_id] = await get_live_client().get_tournament_city(tournament_id)
                except Exception:
                    city_cache[tournament_id] = None
            city = city_cache[tournament_id]

        fixture = db.query(models.Fixture).filter(models.Fixture.external_id == external_id).first()
        if not fixture:
            fixture = models.Fixture(external_id=external_id, source="livetennisapi")
            db.add(fixture)

        fixture.player1_id = p1.id
        fixture.player2_id = p2.id
        fixture.player1_name_raw = p1_name
        fixture.player2_name_raw = p2_name
        fixture.tour = tour
        fixture.surface = _normalize_surface(m.get("surface"))
        fixture.indoor = m.get("indoor")
        fixture.round = m.get("round")
        fixture.tournament_name = m.get("tournament")
        fixture.tournament_id_external = tournament_id
        fixture.city = city
        fixture.scheduled_time = _parse_scheduled_time(scheduled_time_raw)
        db.flush()
        stats["upserted"] += 1

        # Cotes de marché + météo, dénormalisées sur la ligne : c'est CE job,
        # jamais une requête utilisateur, qui les récupère désormais.
        now = datetime.utcnow()
        try:
            market = market_providers.get_market_provider().get_probability(p1.name, p2.name)
        except Exception:
            market = None
        if market:
            fixture.market_player1_prob = market.get("player1_prob")
            fixture.market_player2_prob = market.get("player2_prob")
            fixture.market_question = market.get("question")
            fixture.market_synced_at = now
            stats["market_found"] += 1

        if city and not fixture.indoor:
            try:
                weather = weather_providers.get_weather_provider().get_conditions(city, fixture.scheduled_time)
            except Exception:
                weather = None
            if weather:
                fixture.weather_temp_c = weather.get("temp_c")
                fixture.weather_wind_kmh = weather.get("wind_kmh")
                fixture.weather_humidity_pct = weather.get("humidity_pct")
                fixture.weather_description = weather.get("description")
                fixture.weather_synced_at = now
                stats["weather_found"] += 1

    db.commit()

    # Purge : fixtures de ce tour absentes du calendrier live actuel (match
    # annulé/reporté) OU dont la date programmée est trop ancienne (déjà
    # jouées). Filtré côté Python (pas de composition de clause SQL avec un
    # set potentiellement vide) — le volume par tour reste modeste.
    stale_cutoff = datetime.utcnow() - STALE_AFTER
    for f in db.query(models.Fixture).filter(models.Fixture.tour == tour).all():
        is_too_old = bool(f.scheduled_time and f.scheduled_time < stale_cutoff)
        is_gone_from_live_calendar = f.external_id not in seen_external_ids
        if is_too_old or is_gone_from_live_calendar:
            db.delete(f)
            stats["pruned"] += 1
    db.commit()

    return stats


async def _run_async(db: Session) -> dict:
    report = {"configured": is_configured(), "tours": []}
    if not report["configured"]:
        return report
    for tour in TOURS:
        rankings_updated = await _sync_rankings(db, tour)
        tour_report = await _sync_fixtures_for_tour(db, tour)
        tour_report["rankings_updated"] = rankings_updated
        report["tours"].append(tour_report)
    return report


def run(db: Session | None = None) -> dict:
    owns_session = db is None
    db = db or SessionLocal()
    try:
        return asyncio.run(_run_async(db))
    finally:
        if owns_session:
            db.close()


def main():
    report = run()
    if not report["configured"]:
        print("[sync_hourly] LIVETENNISAPI_KEY non configurée -- rien à synchroniser.")
        return
    for t in report["tours"]:
        print(
            f"[sync_hourly] {t['tour'].upper()} : {t['fetched']} match(s) récupéré(s), "
            f"{t['created_players']} joueur(s) découvert(s), {t['upserted']} fixture(s) mise(s) à jour, "
            f"{t['rankings_updated']} classement(s) mis à jour, "
            f"{t['market_found']} cote(s) trouvée(s), {t['weather_found']} météo(s) trouvée(s), "
            f"{t['pruned']} fixture(s) obsolète(s) purgée(s)."
        )


if __name__ == "__main__":
    sys.exit(main())

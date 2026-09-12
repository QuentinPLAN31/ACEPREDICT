"""
Job de synchronisation QUOTIDIEN : convertit les matchs déjà joués d'un
tournoi EN COURS (tableau scrapé sur tennisexplorer.com) en Match
permanents -- sans ça, un match joué pendant un tournoi en cours ne laisse
AUCUNE trace une fois sa Fixture purgée par sync_hourly.py (cf. STALE_AFTER)
: "dernière victoire/défaite" restait figée à la dernière saison importée,
et les boutons de filtre par tour (1er tour, 2e tour...) restaient vides
tant que le tournoi n'était pas terminé et réimporté depuis les CSV
Sackmann.

Source : app/services/scrape_provider.fetch_draw() -- déduit le round et le
vainqueur de chaque match directement de la position des noms dans le
tableau du tournoi (pas besoin de scraper un score séparément). Limité aux
tournois listés dans scrape_provider.TOURNAMENT_SLUGS (à étendre au
besoin).

Usage :
    python -m scripts.sync_draws_daily

À planifier dans Railway comme un cron job quotidien (peut tourner à la
même heure que sync_rankings_daily.py).
"""
import re
import sys
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app import models
from app.database import SessionLocal
from app.services import scrape_provider


def _match_surname_in_name(scraped_name: str, full_name: str) -> bool:
    """tennisexplorer affiche juste le nom de famille (ex. 'Zverev') dans
    le tableau -- on le compare comme mot entier au nom complet connu chez
    nous, insensible à la casse. Best-effort : mieux vaut rater un
    rapprochement que se tromper de joueur."""
    surname = (scraped_name or "").strip().lower()
    if not surname or len(surname) < 3:
        return False
    return bool(re.search(r"\b" + re.escape(surname) + r"\b", (full_name or "").lower()))


def _surname_is_last_word(scraped_name: str, full_name: str) -> bool:
    """Comme _match_surname_in_name, mais exige que le nom de famille
    scrapé soit le DERNIER mot du nom complet (la vraie position du nom de
    famille) -- élimine les faux positifs où le mot apparaît ailleurs dans
    le nom (ex. scraped_name='Paul' ne doit PAS matcher 'Jean Paul Kadangah
    Kili' -- 'Paul' y est un prénom composé, pas le nom de famille -- ni
    'Paul Jubb', où c'est le PRÉNOM)."""
    surname = (scraped_name or "").strip().lower()
    words = (full_name or "").strip().lower().split()
    return bool(surname) and bool(words) and words[-1] == surname


def _find_player_for_tour(db: Session, scraped_name: str, tour: str) -> Optional[models.Player]:
    candidates = db.query(models.Player).filter(models.Player.tour == tour).all()

    # 1) Ne garder que les joueurs dont le nom de famille scrapé est bien le
    # DERNIER mot de leur nom complet (élimine par ex. 'Paul' matchant
    # 'Jean Paul Kadangah Kili' ou 'Paul Jubb' -- 'Paul' y est un prénom,
    # pas le nom de famille de Tommy Paul).
    matches = [p for p in candidates if _surname_is_last_word(scraped_name, p.name)]
    if not matches:
        # Repli : au cas où notre nom stocké ne finit pas exactement par ce
        # mot (ordre inhabituel, nom de famille composé...) -- on retente
        # avec l'ancien critère, plus permissif.
        matches = [p for p in candidates if _match_surname_in_name(scraped_name, p.name)]

    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        # Toujours ambigu (cas réel : des frères partageant le même nom de
        # famille, ex. les 2 Cerundolo, les 2 Tsitsipas) -- on départage par
        # le classement ATP/WTA connu (current_rank), le joueur en tableau
        # principal d'un tournoi de cette envergure étant quasi toujours
        # celui qui a le meilleur classement (le plus petit nombre) parmi
        # les homonymes. Si un seul a un classement connu, on le prend ; si
        # aucun n'en a, on reste prudent et on ne devine pas.
        ranked = [p for p in matches if p.current_rank is not None]
        if len(ranked) == 1:
            return ranked[0]
        if len(ranked) > 1:
            return min(ranked, key=lambda p: p.current_rank)
        return None  # toujours ambigu, aucun classement pour départager
    return None  # absent


async def sync_draw_for_competition(db: Session, comp: models.Competition) -> dict:
    result = {"competition": comp.name, "matches_found": 0, "matches_created": 0, "unresolved_players": 0}
    year = comp.season or datetime.utcnow().year
    try:
        entries = await scrape_provider.fetch_draw(comp.tour, comp.name, year)
    except Exception:
        return result
    result["matches_found"] = len(entries)
    if not entries:
        return result

    now = datetime.utcnow()
    total = len(entries)
    for i, e in enumerate(entries):
        p1 = _find_player_for_tour(db, e["player1_name"], comp.tour)
        p2 = _find_player_for_tour(db, e["player2_name"], comp.tour)
        if not p1 or not p2 or p1.id == p2.id:
            result["unresolved_players"] += 1
            continue
        winner_scraped = e["winner_name"]
        if winner_scraped == e["player1_name"]:
            winner_id = p1.id
        elif winner_scraped == e["player2_name"]:
            winner_id = p2.id
        else:
            continue

        # Idempotence : même compétition + paire de joueurs déjà connue -> on
        # met à jour la ligne existante plutôt que de dupliquer. Comparer sur
        # la PAIRE SEULE (round exclu de la clé) est indispensable : le round
        # d'un même match peut être recalculé différemment d'un scraping à
        # l'autre tant que le tableau évolue (cf. correctif dans
        # scrape_provider._DRAW_SIZE_TO_ROUND) -- comparer round+paire
        # créait un doublon à chaque fois que le round recalculé changeait.
        already = (
            db.query(models.Match)
            .filter(
                models.Match.competition_id == comp.id,
                ((models.Match.player1_id == p1.id) & (models.Match.player2_id == p2.id))
                | ((models.Match.player1_id == p2.id) & (models.Match.player2_id == p1.id)),
            )
            .first()
        )
        if already:
            if already.round != e["round"] or already.winner_id != winner_id:
                already.round = e["round"]
                already.winner_id = winner_id
                result["matches_created"] += 0  # mise à jour, pas une création
            continue

        # Date approximative : on ne connaît pas la date exacte du match via
        # cette page (juste sa position dans le tableau) -- on étale les
        # tours sur des jours distincts (le round le plus ancien = date la
        # plus reculée) uniquement pour que le tri chronologique / "dernière
        # victoire" reste cohérent, PAS comme date réelle fiable.
        tourney_date = now - timedelta(days=(total - i))

        match = models.Match(
            competition_id=comp.id,
            tourney_date=tourney_date,
            round=e["round"],
            surface=comp.surface,
            player1_id=p1.id,
            player2_id=p2.id,
            winner_id=winner_id,
            score=None,
            source="scrape",
        )
        db.add(match)
        result["matches_created"] += 1
    db.commit()
    return result


async def _run_async(db: Session) -> dict:
    report = {"competitions": []}
    current_year = datetime.utcnow().year
    comps = (
        db.query(models.Competition)
        .filter((models.Competition.season == None) | (models.Competition.season >= current_year))  # noqa: E711
        .all()
    )
    for comp in comps:
        if not scrape_provider._slug_for_competition(comp.name or ""):
            continue
        r = await sync_draw_for_competition(db, comp)
        report["competitions"].append(r)
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
    if not report["competitions"]:
        print("[sync_draws_daily] Aucun tournoi en cours ne correspond à TOURNAMENT_SLUGS -- rien à faire.")
        return
    for c in report["competitions"]:
        print(
            f"[sync_draws_daily] {c['competition']} : {c['matches_found']} match(s) trouvé(s) dans le tableau, "
            f"{c['matches_created']} Match créé(s), {c['unresolved_players']} joueur(s) non rapproché(s)."
        )


if __name__ == "__main__":
    sys.exit(main())

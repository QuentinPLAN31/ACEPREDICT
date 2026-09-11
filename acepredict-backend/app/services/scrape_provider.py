"""
Source de données par SCRAPING (tennisexplorer.com), pour tout ce qui
ne doit plus dépendre du quota LiveTennisAPI (100 requêtes/jour en FREE) :
classement ATP/WTA et résultats de matchs déjà joués.

Ce qui RESTE sur LiveTennisAPI (pas touché ici) : calendrier des matchs à
venir/en cours (Fixture), cotes de marché, météo, découverte de nouveaux
joueurs -- cf. scripts/sync_hourly.py.

tennisexplorer.com a été choisi car ses pages sont du HTML simple (pas de
rendu JS côté client, contrairement à atptour.com / wtatennis.com), donc
scrapable avec un simple client HTTP + parseur HTML, sans navigateur
headless. AUCUNE clé API, AUCUN quota.

IMPORTANT -- fragilité assumée : ce module dépend de la mise en page HTML
d'un site tiers qui peut changer sans préavis. Toute fonction ici est
défensive (jamais d'exception qui remonte -- retourne une liste/valeur
vide en cas d'échec de parsing) et loggue un avertissement plutôt que de
planter le job appelant. En cas de page vide/structure changée, voir
scripts/check_scrape_html.py pour un diagnostic (dump du HTML brut à coller
pour ajustement des sélecteurs).
"""
import logging
import re
from datetime import date as date_cls
from typing import Optional

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://www.tennisexplorer.com"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; AcePredictBot/1.0; +https://acepredict.app)",
    "Accept-Language": "en-US,en;q=0.9",
}
_TOUR_RANKING_SLUG = {"atp": "atp-men", "wta": "wta-women"}
_TOUR_RESULTS_TYPE = {"atp": "atp-single", "wta": "wta-single"}

_SCORE_TOKEN_RE = re.compile(r"^\d{1,2}$")


async def _get(url: str, params: Optional[dict] = None) -> Optional[str]:
    try:
        async with httpx.AsyncClient(timeout=15, headers=_HEADERS, follow_redirects=True) as client:
            r = await client.get(url, params=params)
            if r.status_code != 200:
                logger.warning("scrape_provider: HTTP %s sur %s", r.status_code, url)
                return None
            return r.text
    except Exception as e:
        logger.warning("scrape_provider: échec requête %s (%r)", url, e)
        return None


async def fetch_rankings(tour: str) -> list[dict]:
    """Classement ATP/WTA (page /ranking/<slug>/). Retourne une liste de
    dicts {rank, name, country, points} -- structure volontairement proche
    de ce que renvoyait LiveTennisAPI.get_rankings() pour rester un
    remplacement direct côté appelant."""
    slug = _TOUR_RANKING_SLUG.get(tour)
    if not slug:
        return []
    html = await _get(f"{BASE_URL}/ranking/{slug}/")
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict] = []
    # Générique plutôt que dépendant d'une classe CSS précise : on prend la
    # (les) table(s) HTML de la page et on ne garde que les lignes dont la
    # première cellule ressemble à un rang ("1.", "2", ...).
    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            cells = tr.find_all("td")
            if len(cells) < 2:
                continue
            rank_txt = cells[0].get_text(strip=True).rstrip(".")
            if not rank_txt.isdigit():
                continue
            rank = int(rank_txt)
            link = tr.find("a")
            name = link.get_text(strip=True) if link else None
            if not name:
                continue
            country = None
            flag_img = tr.find("img")
            if flag_img and flag_img.get("alt"):
                country = flag_img.get("alt").strip()
            points = None
            for cell in reversed(cells):
                txt = cell.get_text(strip=True).replace(",", "").replace("\xa0", "")
                if txt.isdigit() and len(txt) >= 3:
                    points = int(txt)
                    break
            out.append({"rank": rank, "name": name, "country": country, "points": points})
    return out


def _parse_set_scores(cells_text: list[str]) -> str:
    """Reconstruit un score lisible ('6-4 7-6') à partir des cellules de
    sets d'une ligne de résultat -- chaque cellule contient un chiffre par
    set joué (colonnes 'S 1 2 3 4 5' du tableau de résultats)."""
    digits = [t for t in cells_text if _SCORE_TOKEN_RE.match(t)]
    return " ".join(digits) if digits else ""


async def fetch_results_for_date(tour: str, day: date_cls) -> list[dict]:
    """Résultats déjà joués pour une date donnée, groupés par tournoi
    (page /results/?type=...&year=&month=&day=). Retourne une liste de
    dicts {tournament, winner_name, loser_name, score}. Le round n'est PAS
    fourni par cette page -- il est déjà connu par ailleurs (Fixture.round,
    lui-même issu de LiveTennisAPI) et n'a donc pas besoin d'être re-scrapé
    ici ; ce scraper sert uniquement à récupérer le SCORE final avant que
    la Fixture correspondante ne soit purgée (cf. sync_hourly.py).

    PARSING SPÉCULATIF -- non encore confirmé contre le HTML réel (accès
    direct bloqué depuis l'environnement où ce fichier a été écrit, cf.
    scripts/check_scrape_html.py). Chaque match est affiché sur DEUX lignes
    consécutives (un joueur par ligne, cf. exemple observé : la ligne du
    vainqueur listée en premier) -- on regroupe les lignes de joueur deux
    par deux au sein d'un même bloc tournoi. Si le HTML réel ne suit pas ce
    schéma, cette fonction renverra juste une liste vide (dégradation
    gracieuse) plutôt que des données fausses -- à corriger avec le dump
    HTML réel une fois testé en conditions réelles."""
    type_ = _TOUR_RESULTS_TYPE.get(tour)
    if not type_:
        return []
    html = await _get(
        f"{BASE_URL}/results/",
        params={"type": type_, "year": day.year, "month": day.month, "day": day.day},
    )
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict] = []
    current_tournament = None
    for el in soup.find_all(["tr", "h3", "h4"]):
        if el.name in ("h3", "h4"):
            txt = el.get_text(strip=True)
            if txt and len(txt) < 80:
                current_tournament = txt
            continue
        link = el.find("a")
        if not link:
            continue
        player_name = link.get_text(strip=True)
        if not player_name or len(player_name) > 60:
            continue
        cells = [c.get_text(strip=True) for c in el.find_all("td")]
        rows.append({
            "tournament": current_tournament,
            "player_name": player_name,
            "score": _parse_set_scores(cells),
        })

    out: list[dict] = []
    i = 0
    while i + 1 < len(rows):
        a, b = rows[i], rows[i + 1]
        if a["tournament"] and a["tournament"] == b["tournament"]:
            out.append({
                "tournament": a["tournament"],
                "winner_name": a["player_name"],
                "loser_name": b["player_name"],
                "score": a["score"] or b["score"],
            })
            i += 2
        else:
            i += 1
    return out

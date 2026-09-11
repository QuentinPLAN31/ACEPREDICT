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


# Mapping "notre nom de tournoi" -> slug URL tennisexplorer (cf.
# https://www.tennisexplorer.com/<slug>/<year>/<atp-men|wta-women>/).
# Rempli au fur et à mesure -- un tournoi absent de cette liste est
# simplement ignoré par sync_draws_daily.py (pas d'exception). Pour ajouter
# un tournoi : ouvrir sa page sur tennisexplorer.com et copier le segment
# d'URL entre le domaine et "/2026/...".
TOURNAMENT_SLUGS = {
    "australian open": "australian-open",
    "roland garros": "french-open", "french open": "french-open",
    "wimbledon": "wimbledon",
    "us open": "us-open",
    "indian wells": "indian-wells",
    "miami open": "miami",
    "monte carlo": "monte-carlo",
    "madrid open": "madrid",
    "italian open": "rome", "internazionali": "rome",
    "canadian open": "canada", "national bank open": "canada",
    "cincinnati": "cincinnati",
    "shanghai": "shanghai",
    "paris masters": "paris",
    "atp finals": "masters", "wta finals": "wta-finals",
}

_STANDARD_ROUND_CODES = ["R128", "R64", "R32", "R16", "QF", "SF", "F"]


def _slug_for_competition(comp_name: str) -> Optional[str]:
    low = (comp_name or "").strip().lower()
    for key, slug in TOURNAMENT_SLUGS.items():
        if key in low:
            return slug
    return None


def _extract_px(style: str, prop: str) -> Optional[int]:
    m = re.search(r"\b" + re.escape(prop) + r"\s*:\s*(-?\d+)\s*(?:px)?\s*;?", style or "")
    return int(m.group(1)) if m else None


def _clean_draw_name(text: str) -> str:
    """Retire les marqueurs de seed/wildcard/qualifier ('[1]', '[Q]',
    '[WC]', '[LL]'...) accolés au nom dans le tableau."""
    return re.sub(r"\s*\[[^\]]*\]\s*$", "", (text or "").strip()).strip()


async def fetch_draw(tour: str, comp_name: str, year: int) -> list[dict]:
    """Tableau du tournoi (onglet 'Tournament draw' de la page tennis-
    explorer du tournoi) -- positions en pixels (pas de tableau HTML
    classique). On regroupe les divs par décalage 'left' (= colonne = tour)
    puis par 'top' (= emplacement dans le tableau). Le VAINQUEUR d'un match
    du tour K est déduit STRUCTURELLEMENT : c'est celui des deux joueurs du
    tour K (positions 2j et 2j+1) dont le nom réapparaît à la position j du
    tour K+1 -- pas besoin de scraper un score pour ça. Le round est déduit
    du nombre de colonnes (pas du texte de l'en-tête, peu fiable). Retourne
    une liste de dicts {round, player1_name, player2_name, winner_name} --
    UNIQUEMENT pour les matchs déjà joués (une case du tour K+1 encore
    vide = match pas encore joué, ignoré).

    PARSING NON ENCORE VALIDÉ EN CONDITIONS RÉELLES au moment de l'écriture
    -- cf. scripts/check_scrape_html.py pour vérifier/ajuster si le
    résultat est vide ou faux."""
    slug = _slug_for_competition(comp_name)
    if not slug:
        return []
    html = await _get(f"{BASE_URL}/{slug}/{year}/{_TOUR_RANKING_SLUG.get(tour, 'atp-men')}/")
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    draw_div = soup.find(id="draw")
    if not draw_div:
        return []

    entries = []
    for div in draw_div.find_all("div", recursive=False):
        left = _extract_px(div.get("style", ""), "left")
        top = _extract_px(div.get("style", ""), "top")
        text = div.get_text(strip=True)
        if left is None or top is None:
            continue
        # Le tableau positionne aussi des divs de SCORE ("6-3, 7-6(2), 6-2")
        # au même décalage 'left' que les noms de joueurs -- si on les
        # laissait dans la liste des emplacements, ça décale tout
        # l'alignement joueur/tour suivant. Un nom de joueur (ou "bye", ou
        # un emplacement pas encore déterminé = texte vide) ne commence
        # jamais par un chiffre ; un score, si -- filtre ciblé plutôt que
        # d'exiger un lien (une "bye" n'a pas de lien mais doit rester).
        if text[:1].isdigit():
            continue
        entries.append((left, top, text))

    columns: dict[int, list[tuple[int, str]]] = {}
    for left, top, text in entries:
        columns.setdefault(left, []).append((top, text))

    round_columns = []
    for left in sorted(columns.keys()):
        items = sorted(columns[left], key=lambda x: x[0])
        slots = [(top, _clean_draw_name(text)) for top, text in items if top != 0]
        if slots:
            round_columns.append(slots)

    num_transitions = len(round_columns) - 1
    if num_transitions < 1:
        return []
    codes = _STANDARD_ROUND_CODES[-num_transitions:] if num_transitions <= len(_STANDARD_ROUND_CODES) else \
        ["R128"] * (num_transitions - len(_STANDARD_ROUND_CODES)) + _STANDARD_ROUND_CODES

    out: list[dict] = []
    for k in range(1, len(round_columns)):
        prev_slots = round_columns[k - 1]
        cur_slots = round_columns[k]
        round_code = codes[k - 1]
        for j, (_, winner_name) in enumerate(cur_slots):
            if not winner_name or 2 * j + 1 >= len(prev_slots):
                continue
            p1 = prev_slots[2 * j][1]
            p2 = prev_slots[2 * j + 1][1]
            if not p1 or not p2:
                continue
            if winner_name == p1 or winner_name == p2:
                out.append({
                    "round": round_code, "player1_name": p1, "player2_name": p2,
                    "winner_name": winner_name,
                })
    return out

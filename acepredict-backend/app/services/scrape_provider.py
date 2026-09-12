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


def _parse_ranking_page(html: str) -> list[dict]:
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
            if flag_img:
                country = (flag_img.get("alt") or flag_img.get("title") or "").strip() or None
            if not country:
                # Repli : certains flags sont un <span> avec une classe/texte
                # de code pays (ex. class="flag flag-fra") plutôt qu'un <img alt=...>.
                flag_span = tr.find(class_=re.compile(r"flag", re.I))
                if flag_span:
                    for cls in flag_span.get("class", []):
                        if cls != "flag" and len(cls.replace("flag-", "")) in (2, 3):
                            country = cls.replace("flag-", "").upper()
                            break
            points = None
            for cell in reversed(cells):
                txt = cell.get_text(strip=True).replace(",", "").replace("\xa0", "")
                if txt.isdigit() and len(txt) >= 3:
                    points = int(txt)
                    break
            out.append({"rank": rank, "name": name, "country": country, "points": points})
    return out


async def fetch_rankings(tour: str, pages: int = 10) -> list[dict]:
    """Classement ATP/WTA (page /ranking/<slug>/?page=N, 50 par page).
    Retourne une liste de dicts {rank, name, country, points} -- structure
    volontairement proche de ce que renvoyait LiveTennisAPI.get_rankings()
    pour rester un remplacement direct côté appelant.

    `pages` (10 par défaut = jusqu'au rang ~500) : couvre largement les
    joueurs susceptibles d'apparaître dans un tableau de Grand Chelem (128
    têtes de série + qualifiés, ces derniers pouvant être classés bien
    au-delà du top 100) -- avant ce correctif, seule la 1ère page (top 50)
    était récupérée, ce qui laissait des trous dans l'annuaire joueurs dès
    qu'un joueur classé entre ~50 et ~500 apparaissait ailleurs (analyse,
    tableau d'un tournoi...) sans jamais avoir reçu son vrai classement.
    Sans coût de quota (scraping) -- s'arrête plus tôt si une page ne
    renvoie aucune ligne (fin de liste atteinte)."""
    slug = _TOUR_RANKING_SLUG.get(tour)
    if not slug:
        return []
    out: list[dict] = []
    for page in range(1, pages + 1):
        html = await _get(f"{BASE_URL}/ranking/{slug}/", params={"page": page} if page > 1 else None)
        if not html:
            break
        page_rows = _parse_ranking_page(html)
        if not page_rows:
            break
        out.extend(page_rows)
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
# Taille du tableau (nb de joueurs) de la 1ere colonne -> round correspondant.
# Cette 1ere colonne (tirage initial) est TOUJOURS entierement peuplee des le
# debut du tournoi et NE CHANGE PLUS ensuite -- contrairement au nombre total
# de colonnes affichees par la page (qui, lui, grandit au fil du tournoi à
# mesure que les tours suivants sont determines). D'ou le bug corrige ici :
# `codes = _STANDARD_ROUND_CODES[-num_transitions:]` deduisait le round
# depuis la FIN de la liste de colonnes, donc le round attribue a une MEME
# colonne (donc au meme match) changeait selon le nombre de colonnes deja
# visibles au moment du scraping -- un match R128 scrape tot dans le tournoi
# (peu de colonnes encore visibles) pouvait ainsi etre etiquete "SF" par
# erreur, puis un scraping ulterieur (plus de colonnes visibles) le
# re-creait sous le bon nom faute de le reconnaitre comme deja connu
# (l'idempotence de sync_draws_daily comparait aussi le round) : doublons +
# rounds R16/QF/SF qui restaient vides pendant que R128 se remplissait de
# lignes en trop.
_DRAW_SIZE_TO_ROUND = {128: "R128", 64: "R64", 32: "R32", 16: "R16", 8: "QF", 4: "SF", 2: "F"}


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
        # La page place aussi un lien/widget "H2H" (face-à-face) au même
        # genre de décalage 'left' qu'une colonne de tour -- si on le
        # laissait passer, BeautifulSoup lui crée sa PROPRE "colonne" d'un
        # seul élément entre l'avant-dernier et le dernier tour réels, ce qui
        # décale ensuite le calcul du round de tous les tours suivants (cf.
        # scripts/check_draw_structure.py, colonne 'H2H' repérée en pratique).
        if text.strip().lower() == "h2h":
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

    # La page place aussi, avant la vraie 1ère colonne (le tirage initial,
    # TOUJOURS entièrement rempli de vrais noms), un élément décoratif isolé
    # à 'left' quasi nul (une seule "case" vide) -- observé en pratique via
    # scripts/check_draw_structure.py. Non filtré, il devient round_columns[0]
    # avec 1 seule entrée, ce qui fait échouer la détection du round de
    # départ (_DRAW_SIZE_TO_ROUND) et décale TOUS les tours d'un cran. On ne
    # retire que les colonnes de tête entièrement vides (jamais une colonne
    # de fin -- un tour final "pas encore déterminé" est lui légitimement
    # vide et doit être conservé).
    while round_columns and not any(name for _, name in round_columns[0]):
        round_columns.pop(0)

    num_transitions = len(round_columns) - 1
    if num_transitions < 1:
        return []
    # Round de depart deduit de la taille du tirage initial (1ere colonne),
    # stable quel que soit l'avancement du tournoi au moment du scraping --
    # cf. commentaire sur _DRAW_SIZE_TO_ROUND plus haut. Repli sur l'ancien
    # calcul (depuis la fin) uniquement si la taille de la 1ere colonne ne
    # correspond a aucune taille de tableau standard (ex: page mal parsee).
    first_col_size = len(round_columns[0])
    start_round = _DRAW_SIZE_TO_ROUND.get(first_col_size)
    if start_round is not None and start_round in _STANDARD_ROUND_CODES:
        start_idx = _STANDARD_ROUND_CODES.index(start_round)
        codes = _STANDARD_ROUND_CODES[start_idx:start_idx + num_transitions]
        # Le tableau contient plus de transitions que de rounds standards
        # connus a partir de ce point (ne devrait pas arriver) -- on comble
        # au pire avec le dernier code plutot que planter.
        while len(codes) < num_transitions:
            codes.append(_STANDARD_ROUND_CODES[-1])
    else:
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

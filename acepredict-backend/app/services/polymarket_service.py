"""
Probabilité de marché — remplace The Odds API (abandonnée : payante et peu
fiable en pratique) par l'API Gamma de Polymarket (https://polymarket.com),
un marché prédictif : le prix de chaque camp reflète directement la
probabilité que les traders lui attribuent, sans vig bookmaker à retirer.
API publique, SANS clé requise (cf. https://docs.polymarket.com).

Le marché intègre en temps réel des informations que notre modèle Elo ne
peut jamais connaître (blessure non annoncée, forfait probable, motivation,
petite forme cachée) : fusionner notre probabilité avec la sienne est,
statistiquement, le moyen le plus efficace de fiabiliser un pronostic sans
changer le moteur Elo lui-même — cf. services/prediction.py.

Couverture réelle et HONNÊTE : Polymarket propose des centaines de marchés
"vainqueur du match" par semaine sur le tennis (ATP/WTA/Challenger/ITF),
mais pas sur CHAQUE match qui existe (aucune source gratuite ne couvre 100%
des rencontres avec des cotes fiables) — dégradation gracieuse obligatoire,
comme les autres services optionnels de ce backend (Stripe/météo/
LiveTennisAPI/Anthropic) : si aucun marché correspondant n'est trouvé, ou en
cas d'ambiguïté, ou d'erreur réseau, get_market_probability() renvoie None
et l'analyse continue de fonctionner uniquement sur l'Elo + les autres
ajustements.

Découverte par TAG plutôt que recherche texte par paire de joueurs : une
recherche `/public-search?q=<joueur1> <joueur2>` par match, comme une V1 de
ce service le faisait, dépend du classement de pertinence interne de
Polymarket et rate une bonne partie des marchés réels (mauvais taux de
correspondance en pratique). On récupère à la place TOUTE la liste des
marchés tennis actifs en un seul appel (tag "tennis" de la Gamma API — même
méthode que les outils tiers de découverte Polymarket/tennis), mise en
cache _TENNIS_MARKETS_CACHE_TTL_SECONDS pour ne pas re-télécharger la liste
à chaque analyse, puis on matche localement — bien plus fiable, et un seul
appel réseau amorti sur toutes les analyses de la fenêtre de cache au lieu
d'un appel par analyse.

Approche "safety-first" sur le matching nom de joueur <-> marché : on ne
retourne un résultat QUE si les DEUX noms de joueurs sont retrouvés sans
ambiguïté dans un marché "vainqueur du match" à 2 issues (jamais de
double/triple, jamais un marché "set winner"/"total games" mal identifié
comme un moneyline). Mieux vaut ne rien retourner que fusionner avec le
mauvais marché.
"""
import json
import time
from typing import Optional

import httpx

from app.config import settings

TIMEOUT_SECONDS = 8.0

EVENTS_URL_PATH = "/events"
# Le "tag" tennis de la Gamma API — passé à la fois par slug et par id
# (l'un des deux suffit selon la version de l'API ; un paramètre non
# reconnu par l'API est simplement ignoré, donc passer les deux est sans
# risque et couvre le cas où l'un des deux formats change).
TENNIS_TAG_SLUG = "tennis"
TENNIS_TAG_ID = 864
# Volontairement large : un seul appel plutôt qu'une pagination complexe
# (moins de code, moins de points de défaillance) — au prix de ne pas
# forcément couvrir l'intégralité des marchés tennis actifs à un instant T
# si Polymarket en liste plus que cette limite simultanément.
EVENTS_FETCH_LIMIT = 500

_TENNIS_MARKETS_CACHE_TTL_SECONDS = 120
_tennis_markets_cache: Optional[tuple[float, list[dict]]] = None


def is_configured() -> bool:
    return bool(settings.polymarket_enabled)


def _surname(full_name: str) -> str:
    """Dernier "mot" du nom, en minuscules — suffisant et plus robuste que le
    nom complet pour matcher un market Polymarket (qui n'utilise pas
    forcément la même graphie/prénom complet que notre base Sackmann)."""
    parts = full_name.strip().split()
    return parts[-1].lower() if parts else full_name.strip().lower()


def _fetch_tennis_markets() -> list[dict]:
    """Renvoie tous les marchés (pas les events) actuellement tagués
    "tennis" et non clôturés, mis en cache. Liste vide en cas d'erreur
    réseau/JSON — jamais d'exception."""
    global _tennis_markets_cache
    now = time.monotonic()
    if _tennis_markets_cache and now - _tennis_markets_cache[0] < _TENNIS_MARKETS_CACHE_TTL_SECONDS:
        return _tennis_markets_cache[1]

    markets: list[dict] = []
    try:
        resp = httpx.get(
            f"{settings.polymarket_base_url}{EVENTS_URL_PATH}",
            params={
                "tag_slug": TENNIS_TAG_SLUG,
                "tag_id": TENNIS_TAG_ID,
                "closed": "false",
                "limit": EVENTS_FETCH_LIMIT,
            },
            timeout=TIMEOUT_SECONDS,
        )
        if resp.status_code == 200:
            data = resp.json()
            events = data if isinstance(data, list) else (data.get("events") or [])
            for event in events:
                markets.extend(event.get("markets") or [])
    except Exception:
        markets = []

    _tennis_markets_cache = (now, markets)
    return markets


def get_market_probability(player1_name: str, player2_name: str) -> Optional[dict]:
    """
    Retourne {"player1_prob": float, "player2_prob": float, "question": str}
    (probabilités normalisées, somme = 1.0) si un marché "vainqueur du match"
    correspondant sans ambiguïté aux deux joueurs a été trouvé, sinon None.
    Ne lève jamais d'exception (réseau, JSON malformé, etc.).
    """
    if not is_configured() or not player1_name or not player2_name:
        return None

    s1, s2 = _surname(player1_name), _surname(player2_name)
    if not s1 or not s2 or s1 == s2:
        return None

    candidates = []
    for market in _fetch_tennis_markets():
        match = _match_moneyline_market(market, s1, s2)
        if match:
            candidates.append(match)

    # Ambiguïté (plusieurs marchés candidats, ex: un marché "match" et un
    # marché "1er set" tous les deux matchés par erreur) -> on ne devine pas.
    if len(candidates) != 1:
        return None
    return candidates[0]


def _match_moneyline_market(market: dict, s1: str, s2: str) -> Optional[dict]:
    if market.get("closed") is True or market.get("active") is False:
        return None

    question = (market.get("question") or "").lower()
    if s1 not in question or s2 not in question:
        return None
    # Un market "vainqueur du match" à 2 issues nomme chaque camp d'après un
    # joueur (pas "Yes"/"No" générique, pas un marché à 3+ issues type "set
    # winner" ou "outright" à N joueurs) : on exige exactement 2 outcomes,
    # chacun contenant le surnom d'un des deux joueurs, un par outcome.
    try:
        outcomes = json.loads(market.get("outcomes") or "[]")
        prices = json.loads(market.get("outcomePrices") or "[]")
    except Exception:
        return None
    if len(outcomes) != 2 or len(prices) != 2:
        return None

    outcomes_lower = [str(o).lower() for o in outcomes]
    idx1 = _index_for_surname(outcomes_lower, s1)
    idx2 = _index_for_surname(outcomes_lower, s2)
    if idx1 is None or idx2 is None or idx1 == idx2:
        return None

    try:
        p1 = float(prices[idx1])
        p2 = float(prices[idx2])
    except (TypeError, ValueError):
        return None
    total = p1 + p2
    if total <= 0:
        return None

    return {
        "player1_prob": round(p1 / total, 4),
        "player2_prob": round(p2 / total, 4),
        "question": market.get("question") or "",
    }


def _index_for_surname(outcomes_lower: list[str], surname: str) -> Optional[int]:
    matches = [i for i, o in enumerate(outcomes_lower) if surname in o]
    return matches[0] if len(matches) == 1 else None

"""Projection de score d'un match ("scénario du match").

Deux briques, volontairement simples et documentées :

1. RÉPARTITION DES SCORES EN SETS -- déduite de la probabilité de victoire du
   match (celle de prediction.build_prediction). On cherche la probabilité s
   de gagner UN set qui redonne cette probabilité de match (modèle classique :
   sets indépendants, même s pour toute la rencontre), puis on en tire la loi
   de chaque score (2-0, 2-1 ; 3-0, 3-1, 3-2 en cinq sets). C'est une
   approximation mathématique, pas une mesure.

2. NOMBRE DE JEUX -- basé sur les VRAIES statistiques des joueurs : moyenne de
   jeux par set sur leurs derniers matchs en base (Match.score, import
   Sackmann), sur la surface du match si l'échantillon est assez grand.
   Sans historique exploitable, on retombe sur une moyenne générique.

Le tout est une projection ("scénario le plus probable"), jamais présentée
comme une certitude -- cf. la note renvoyée avec le résultat.
"""
import re
from math import comb
from typing import Optional

from sqlalchemy.orm import Session

from app import models

DEFAULT_GAMES_PER_SET = 9.6   # moyenne générique en l'absence d'historique
MIN_SETS_FOR_STATS = 12       # sous ce seuil, l'historique d'un joueur est ignoré
RECENT_MATCHES = 60
MIN_SURFACE_MATCHES = 8
GAMES_MARGIN = 3              # fourchette = attendu ± 3 jeux (écart-type réel ~4)

_SET_RE = re.compile(r"^(\d+)-(\d+)(?:\(\d+\))?$")
_INCOMPLETE = ("RET", "W/O", "WO", "DEF", "ABD", "UNP", "WALKOVER")


def _match_prob_from_set_prob(s: float, sets_to_win: int) -> float:
    n = sets_to_win
    return sum(comb(n - 1 + k, k) * (s ** n) * ((1 - s) ** k) for k in range(n))


def set_win_prob(match_prob: float, sets_to_win: int) -> float:
    """Probabilité de gagner un set telle que la probabilité de gagner le
    match soit `match_prob` (recherche par dichotomie, monotone sur [0.5, 1))."""
    p = min(0.999, max(0.5, match_prob))
    lo, hi = 0.5, 0.999
    for _ in range(60):
        mid = (lo + hi) / 2
        if _match_prob_from_set_prob(mid, sets_to_win) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def score_distribution(match_prob: float, sets_to_win: int) -> list[dict]:
    """Tous les scores possibles, du plus au moins probable. `favorite` = le
    vainqueur prédit ; `side` indique qui gagne le match dans ce scénario."""
    s = set_win_prob(match_prob, sets_to_win)
    n = sets_to_win
    out = []
    for k in range(n):
        c = comb(n - 1 + k, k)
        out.append({"side": "favorite", "score": f"{n}-{k}", "sets": n + k, "probability": c * (s ** n) * ((1 - s) ** k)})
        out.append({"side": "underdog", "score": f"{n}-{k}", "sets": n + k, "probability": c * ((1 - s) ** n) * (s ** k)})
    out.sort(key=lambda d: d["probability"], reverse=True)
    return out


def _games_per_set(db: Session, player_id, surface: Optional[str]) -> Optional[tuple[float, int]]:
    """(moyenne de jeux par set, nombre de sets) sur les derniers matchs du
    joueur, ou None si l'échantillon est trop petit."""
    rows = (
        db.query(models.Match)
        .filter((models.Match.player1_id == player_id) | (models.Match.player2_id == player_id))
        .filter(models.Match.score.isnot(None))
        .order_by(models.Match.tourney_date.desc())
        .limit(RECENT_MATCHES)
        .all()
    )

    def parse(rs):
        total_games = total_sets = 0
        for m in rs:
            txt = (m.score or "").upper()
            if any(tag in txt for tag in _INCOMPLETE):
                continue
            for tok in (m.score or "").split():
                mt = _SET_RE.match(tok)
                if mt:
                    total_games += int(mt.group(1)) + int(mt.group(2))
                    total_sets += 1
        return total_games, total_sets

    if surface:
        same = [m for m in rows if m.surface is not None and getattr(m.surface, "value", m.surface) == surface]
        if len(same) >= MIN_SURFACE_MATCHES:
            g, n = parse(same)
            if n >= MIN_SETS_FOR_STATS:
                return g / n, n
    g, n = parse(rows)
    if n >= MIN_SETS_FOR_STATS:
        return g / n, n
    return None


def build_score_projection(
    db: Optional[Session],
    winner: models.Player,
    loser: models.Player,
    win_probability: float,
    surface: Optional[str],
    best_of_5: bool,
) -> dict:
    n = 3 if best_of_5 else 2
    dist = score_distribution(win_probability, n)

    scenarios = []
    for d in dist:
        player = winner if d["side"] == "favorite" else loser
        scenarios.append({
            "winner_id": str(player.id),
            "winner_name": player.name,
            "side": d["side"],
            "score": d["score"],
            "probability": round(d["probability"], 4),
        })

    expected_sets = sum(d["sets"] * d["probability"] for d in dist)

    stats = []
    if db is not None:
        for p in (winner, loser):
            r = _games_per_set(db, p.id, surface)
            if r:
                stats.append(r)
    if stats:
        total_sets = sum(n_sets for _, n_sets in stats)
        gps = sum(g * n_sets for g, n_sets in stats) / total_sets
        source = "history"
    else:
        gps = DEFAULT_GAMES_PER_SET
        source = "default"

    expected_games = expected_sets * gps
    return {
        "best_of": 5 if best_of_5 else 3,
        "scenarios": scenarios[:4],
        "most_likely": scenarios[0],
        "total_games": {
            "expected": round(expected_games),
            "low": max(0, round(expected_games - GAMES_MARGIN)),
            "high": round(expected_games + GAMES_MARGIN),
            "games_per_set": round(gps, 2),
            "source": source,
            "players_with_history": len(stats),
        },
        "note": "Projection du modèle (probabilité de victoire + statistiques de jeux des joueurs), "
                "pas une certitude.",
    }

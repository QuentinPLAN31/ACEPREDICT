"""Garde-fou "calendrier impossible" pour les matchs à venir.

La source (LiveTennisAPI) publie parfois, pour les tournois à poules (ATP
Finals, WTA Finals...) ou pour les tours pas encore joués, TOUTES les
affiches possibles avec un horaire factice identique (ex. : 12 matchs du
Masters "le 15 nov. à 13:00", Alcaraz jouant 3 matchs en même temps).
Afficher ça ruine la crédibilité du site.

Règle : un joueur ne peut pas jouer deux matchs différents à moins de
MIN_GAP l'un de l'autre. Toutes les fixtures impliquées dans un tel conflit
sont écartées (on ne peut pas savoir laquelle est la vraie) -- elles
réapparaîtront d'elles-mêmes quand la source publiera le vrai programme.
"""
from datetime import timedelta

MIN_GAP = timedelta(hours=4)


def _pid(f, n):
    v = getattr(f, f"player{n}_id", None)
    return str(v) if v is not None else (getattr(f, f"player{n}_name_raw", None) or "").strip().lower() or None


def impossible_ids(fixtures) -> set:
    """Renvoie l'ensemble des id() des fixtures en conflit d'horaire."""
    by_player = {}
    for f in fixtures:
        if not getattr(f, "scheduled_time", None):
            continue
        for n in (1, 2):
            p = _pid(f, n)
            if p:
                by_player.setdefault(p, []).append(f)
    bad = set()
    for lst in by_player.values():
        lst.sort(key=lambda x: x.scheduled_time)
        for a, b in zip(lst, lst[1:]):
            pa = frozenset((_pid(a, 1), _pid(a, 2)))
            pb = frozenset((_pid(b, 1), _pid(b, 2)))
            if pa != pb and (b.scheduled_time - a.scheduled_time) < MIN_GAP:
                bad.add(id(a)); bad.add(id(b))
    return bad


def drop_impossible(fixtures):
    bad = impossible_ids(fixtures)
    return [f for f in fixtures if id(f) not in bad]

"""Normalisation de noms de joueurs pour détecter les doublons.

Cause typique d'un doublon (ex. "Alex de Minaur" affiché deux fois dans le
classement) : une source écrit "Alex de Minaur", une autre "Alex De Minaur",
"De Minaur Alex" ou "Alex Minaur" -- un match exact (ilike) les voit comme
deux joueurs différents et crée une 2e fiche. name_key() ramène toutes ces
variantes à la même clé : accents retirés, casse/ordre/traits d'union ignorés,
particules ("de", "van", "von"...) ignorées.
"""
import unicodedata

PARTICLES = frozenset({"de", "da", "di", "del", "della", "du", "des", "van", "von", "der", "den", "ten", "ter", "le", "la", "el", "al", "bin"})


def name_key(name: str) -> frozenset:
    if not name:
        return frozenset()
    txt = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    words = [w for w in txt.lower().replace("-", " ").replace(".", " ").split() if w]
    core = frozenset(w for w in words if w not in PARTICLES)
    return core or frozenset(words)

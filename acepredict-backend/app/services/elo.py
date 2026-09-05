"""
Moteur de rating Elo par surface — le cœur du service de prédiction (point 5).

Formule classique Elo appliquée au tennis (cf. FiveThirtyEight / Ultimate
Tennis Statistics) :

    P(A bat B) = 1 / (1 + 10 ** ((Elo_B - Elo_A) / 400))

Après chaque match :
    Elo_gagnant += K * (1 - P(gagnant gagne))
    Elo_perdant += K * (0 - P(perdant gagne))

K est fixe ici (simple et robuste pour un projet scolaire) ; une version
plus fine pondérerait K par le nombre de matchs déjà joués par le joueur
(K plus grand pour un joueur "neuf", plus petit pour un joueur établi) —
piste d'amélioration documentée dans ARCHITECTURE.md.
"""
from dataclasses import dataclass, field

STARTING_ELO = 1500.0
K_FACTOR = 32.0

SURFACES = ("hard", "clay", "grass", "carpet")


def expected_score(elo_a: float, elo_b: float) -> float:
    """Probabilité que le joueur A batte le joueur B, selon leurs Elo respectifs."""
    return 1.0 / (1.0 + 10 ** ((elo_b - elo_a) / 400.0))


def update_elo(elo_winner: float, elo_loser: float, k: float = K_FACTOR) -> tuple[float, float]:
    """Retourne (nouvel_elo_gagnant, nouvel_elo_perdant) après un match."""
    p_winner = expected_score(elo_winner, elo_loser)
    p_loser = 1.0 - p_winner
    new_winner = elo_winner + k * (1 - p_winner)
    new_loser = elo_loser + k * (0 - p_loser)
    return new_winner, new_loser


@dataclass
class PlayerRating:
    """Ratings courants d'un joueur, un par surface + un rating global."""
    player_key: str  # identifiant stable (ex: sackmann_id ou nom normalisé)
    overall: float = STARTING_ELO
    by_surface: dict[str, float] = field(
        default_factory=lambda: {s: STARTING_ELO for s in SURFACES}
    )

    def rating_for(self, surface: str | None) -> float:
        if surface and surface in self.by_surface:
            return self.by_surface[surface]
        return self.overall


class EloEngine:
    """
    Calcule les ratings Elo (global + par surface) à partir d'une séquence
    de matchs triés chronologiquement. Utilisé par scripts/compute_elo_ratings.py
    (job offline batch) ET par les tests.
    """

    def __init__(self, k: float = K_FACTOR):
        self.k = k
        self.ratings: dict[str, PlayerRating] = {}

    def _get(self, player_key: str) -> PlayerRating:
        if player_key not in self.ratings:
            self.ratings[player_key] = PlayerRating(player_key=player_key)
        return self.ratings[player_key]

    def process_match(self, winner_key: str, loser_key: str, surface: str | None = None):
        winner = self._get(winner_key)
        loser = self._get(loser_key)

        # Rating global
        new_w_overall, new_l_overall = update_elo(winner.overall, loser.overall, self.k)
        winner.overall, loser.overall = new_w_overall, new_l_overall

        # Rating par surface (si connue)
        if surface in SURFACES:
            new_w_surf, new_l_surf = update_elo(
                winner.by_surface[surface], loser.by_surface[surface], self.k
            )
            winner.by_surface[surface] = new_w_surf
            loser.by_surface[surface] = new_l_surf

    def process_matches(self, matches):
        """matches: itérable de dicts {winner_key, loser_key, surface}, triés par date croissante."""
        for m in matches:
            self.process_match(m["winner_key"], m["loser_key"], m.get("surface"))

    def predict(self, player_a_key: str, player_b_key: str, surface: str | None = None) -> dict:
        a = self._get(player_a_key)
        b = self._get(player_b_key)
        elo_a = a.rating_for(surface)
        elo_b = b.rating_for(surface)
        p_a = expected_score(elo_a, elo_b)
        winner_key = player_a_key if p_a >= 0.5 else player_b_key
        return {
            "player_a": player_a_key,
            "player_b": player_b_key,
            "surface": surface,
            "elo_a": round(elo_a, 1),
            "elo_b": round(elo_b, 1),
            "predicted_winner": winner_key,
            "win_probability": round(p_a if winner_key == player_a_key else 1 - p_a, 4),
        }

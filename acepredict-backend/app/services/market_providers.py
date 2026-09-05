"""
Interface commune pour une source de "probabilité de marché" (le prix
qu'un marché financier/prédictif attribue à chaque camp), utilisée par
services/prediction.py pour calibrer/comparer le modèle Elo interne.

Une seule implémentation aujourd'hui : Polymarket (cf. polymarket_service.py).
The Odds API (cotes de bookmakers, plan gratuit 500 crédits/mois) N'A PAS été
retenue ici : en usage réel sur ce projet, l'API s'est révélée peu fiable
(erreurs/indisponibilité) pour un site qui doit rester utilisable, alors que
Polymarket est publique, sans clé et sans quota à surveiller — cf. l'en-tête
de polymarket_service.py pour le détail. L'interface ci-dessous garde
volontairement la porte ouverte à un futur OddsApiProvider si besoin : il
suffirait d'implémenter MarketProvider et de le brancher dans
get_market_provider(), sans toucher à prediction.py.
"""
from typing import Optional

from app.services import polymarket_service


class MarketProvider:
    """Renvoie {player1_prob, player2_prob, question} (probabilités
    normalisées, somme = 1.0) ou None si aucun marché fiable n'a été trouvé —
    jamais d'exception."""

    def is_configured(self) -> bool:
        raise NotImplementedError

    def get_probability(self, player1_name: str, player2_name: str) -> Optional[dict]:
        raise NotImplementedError


class PolymarketProvider(MarketProvider):
    def is_configured(self) -> bool:
        return polymarket_service.is_configured()

    def get_probability(self, player1_name: str, player2_name: str) -> Optional[dict]:
        # Appel via le module (pas un import direct de la fonction) pour que
        # les tests qui patchent polymarket_service.get_market_probability
        # (patch.object) continuent de fonctionner sans changement.
        return polymarket_service.get_market_probability(player1_name, player2_name)


def get_market_provider() -> MarketProvider:
    return PolymarketProvider()

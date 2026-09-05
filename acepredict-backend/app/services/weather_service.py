"""
Service météo optionnel — enrichit une analyse avec les conditions
réelles/prévues du match (température, vent, humidité) quand une ville a été
précisée par l'utilisateur.

Point d'entrée stable (get_match_conditions/is_configured) au-dessus de deux
fournisseurs interchangeables définis dans services/weather_providers.py —
OpenWeatherMap (par défaut, sûr pour un usage commercial) et Open-Meteo
(sans clé mais réservé au non-commercial par sa licence, jamais choisi par
défaut). Voir weather_providers.py pour le détail des deux, et le README
("Sources de données & APIs") pour le tableau récapitulatif des licences.

Sans fournisseur configuré (pas de WEATHER_API_KEY, et WEATHER_PROVIDER pas
positionné sur "open-meteo"), ce service renvoie None partout et l'analyse
continue de fonctionner normalement — même pattern de dégradation gracieuse
que Stripe/LiveTennisAPI/Polymarket ailleurs dans ce backend.

Limites connues, assumées et documentées (honnêteté > fausse précision) :
  - Le plan gratuit OpenWeatherMap ne couvre que la météo actuelle et les
    prévisions à 5 jours ; Open-Meteo ne couvre que ~16 jours de prévision.
    Au-delà (ou pour une date passée), aucune donnée n'est retournée plutôt
    que d'inventer une valeur.
  - L'ajustement de probabilité appliqué dans services/prediction.py à
    partir de ces conditions est une heuristique de bon sens (le vent/la
    chaleur extrême rendent un match plus imprévisible), PAS un modèle
    statistique calibré sur des données historiques météo/résultats — on
    ne dispose pas du profil de jeu par joueur (gros serveur, grinder...)
    pour justifier un ajustement dirigé vers un joueur en particulier.
"""
from datetime import datetime
from typing import Optional

# Ré-exporté pour compatibilité : du code (et des tests) fait
# `weather_service.settings.weather_api_key` — settings est un singleton
# partagé (app.config.settings), donc le patcher ici ou dans
# weather_providers.py revient au même objet en mémoire.
from app.config import settings
from app.services.weather_providers import get_weather_provider


def is_configured() -> bool:
    return get_weather_provider().is_configured()


def get_match_conditions(
    city: Optional[str],
    match_date: Optional[datetime] = None,
    indoor: bool = False,
) -> Optional[dict]:
    """
    Retourne {indoor, temp_c, wind_kmh, humidity_pct, description} ou
    {indoor: True} si le match est en intérieur (météo extérieure non
    pertinente), ou None si aucune donnée n'est disponible (aucun
    fournisseur configuré, pas de ville fournie, date hors couverture, ou
    erreur réseau — jamais d'exception qui remonterait jusqu'à /analyses).
    """
    if indoor:
        return {"indoor": True}

    if not city:
        return None

    provider = get_weather_provider()
    if not provider.is_configured():
        return None

    try:
        data = provider.get_conditions(city, match_date)
    except Exception:
        return None
    if not data:
        return None
    return {"indoor": False, **data}

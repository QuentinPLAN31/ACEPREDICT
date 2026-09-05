"""
Fournisseurs météo interchangeables pour l'ajustement "conditions de jeu" de
la prédiction (cf. services/prediction.py :: _weather_dampening). Deux
sources, un rôle différent chacune (détail complet dans le README, section
"Sources de données & APIs") :

  - OpenWeatherMapProvider : fournisseur PAR DÉFAUT et recommandé en
    production. Plan gratuit permanent (60 req/min / 1000 req/jour), clé
    requise (WEATHER_API_KEY), aucune restriction connue sur l'usage
    commercial.
  - OpenMeteoProvider : gratuite et SANS clé (https://open-meteo.com/), mais
    l'offre gratuite est réservée par leurs conditions d'utilisation à un
    usage NON COMMERCIAL (cf. https://open-meteo.com/en/pricing). Elle reste
    disponible ici (utile en dev/démo/projet scolaire, ou en attendant une
    clé OpenWeatherMap) mais n'est JAMAIS choisie par défaut : il faut
    positionner WEATHER_PROVIDER=open-meteo explicitement pour l'activer —
    ne JAMAIS l'activer sur le site en production tant qu'il est monétisé
    (Stripe) sans souscrire à leur offre commerciale.

Interface commune WeatherProvider.get_conditions(city, match_date) -> dict
identique aux deux fournisseurs (mêmes clés en sortie : temp_c, wind_kmh,
humidity_pct, description), pour rester interchangeable sans toucher à
weather_service.py ni à prediction.py — dégradation gracieuse partout
(jamais d'exception, None si la donnée n'est pas disponible).

Cache TTL en mémoire par fournisseur (cf. cache_utils.py) : réduit fortement
le nombre d'appels sortants quand plusieurs analyses portent sur la même
ville/tranche horaire proche dans le temps — important pour respecter les
quotas gratuits des deux APIs.
"""
from datetime import datetime, timedelta
from typing import Optional

import httpx

from app.config import settings
from app.services.cache_utils import TTLCache

# 30 min : assez frais pour une météo de match (les prévisions ne changent
# pas d'une minute à l'autre) tout en réduisant fortement le nombre d'appels
# sortants sous charge (plusieurs analyses de la même ville/heure proche).
_CACHE_TTL_SECONDS = 1800


def _date_bucket(match_date: Optional[datetime]) -> str:
    """Regroupe les requêtes par tranche horaire pour que le cache serve les
    demandes voisines (résolution des prévisions météo, jamais à la minute)."""
    if not match_date:
        return "now"
    return match_date.strftime("%Y-%m-%dT%H")


class WeatherProvider:
    """Interface commune : renvoie {temp_c, wind_kmh, humidity_pct,
    description} ou None (pas de donnée dispo, jamais d'exception)."""

    def is_configured(self) -> bool:
        raise NotImplementedError

    def get_conditions(self, city: str, match_date: Optional[datetime]) -> Optional[dict]:
        raise NotImplementedError


def _parse_openweathermap_slot(d: dict) -> Optional[dict]:
    try:
        return {
            "temp_c": round(d["main"]["temp"], 1),
            "wind_kmh": round(d["wind"]["speed"] * 3.6, 1),
            "humidity_pct": d["main"]["humidity"],
            "description": d["weather"][0]["description"],
        }
    except (KeyError, IndexError, TypeError):
        return None


class OpenWeatherMapProvider(WeatherProvider):
    BASE_URL = "https://api.openweathermap.org/data/2.5"
    # Cache au niveau classe (partagé par toutes les instances, comme
    # get_weather_provider() en recrée une à chaque appel) plutôt qu'au
    # niveau module, pour rester symétrique avec OpenMeteoProvider ci-dessous.
    _cache = TTLCache(ttl_seconds=_CACHE_TTL_SECONDS)

    def is_configured(self) -> bool:
        return bool(settings.weather_api_key)

    def get_conditions(self, city: str, match_date: Optional[datetime]) -> Optional[dict]:
        if not self.is_configured() or not city:
            return None
        cache_key = (city.strip().lower(), _date_bucket(match_date))
        return self._cache.get_or_set_sync(cache_key, lambda: self._fetch(city, match_date))

    def _fetch(self, city: str, match_date: Optional[datetime]) -> Optional[dict]:
        try:
            if match_date and match_date > datetime.utcnow() + timedelta(hours=1):
                return self._fetch_forecast(city, match_date)
            return self._fetch_current(city)
        except Exception:
            return None

    def _fetch_current(self, city: str) -> Optional[dict]:
        resp = httpx.get(
            f"{self.BASE_URL}/weather",
            params={"q": city, "appid": settings.weather_api_key, "units": "metric", "lang": "fr"},
            timeout=5.0,
        )
        if resp.status_code != 200:
            return None
        return _parse_openweathermap_slot(resp.json())

    def _fetch_forecast(self, city: str, match_date: datetime) -> Optional[dict]:
        resp = httpx.get(
            f"{self.BASE_URL}/forecast",
            params={"q": city, "appid": settings.weather_api_key, "units": "metric", "lang": "fr"},
            timeout=5.0,
        )
        if resp.status_code != 200:
            return None
        slots = resp.json().get("list", [])
        if not slots:
            return None
        # Créneau prévisionnel (par pas de 3h) le plus proche de la date du
        # match. Au-delà de ~5 jours, OpenWeatherMap ne renvoie plus de
        # créneaux (plan gratuit) : on retombe naturellement sur None.
        best = min(slots, key=lambda s: abs(datetime.utcfromtimestamp(s["dt"]) - match_date))
        return _parse_openweathermap_slot(best)


# Sous-ensemble des codes météo WMO (utilisés par Open-Meteo) -> description
# FR courte — suffisant pour l'ajustement de prédiction (vent/chaleur), pas
# besoin de couvrir les ~100 codes officiels.
_WMO_DESCRIPTIONS = {
    0: "ciel dégagé", 1: "plutôt dégagé", 2: "partiellement nuageux", 3: "couvert",
    45: "brouillard", 48: "brouillard givrant",
    51: "bruine légère", 53: "bruine", 55: "bruine forte",
    61: "pluie légère", 63: "pluie", 65: "forte pluie",
    71: "neige légère", 73: "neige", 75: "forte neige",
    80: "averses légères", 81: "averses", 82: "averses violentes",
    95: "orage", 96: "orage avec grêle", 99: "orage avec grêle forte",
}


class OpenMeteoProvider(WeatherProvider):
    """
    Gratuite et sans clé -- mais réservée par sa licence à un usage NON
    COMMERCIAL (cf. le bandeau de licence en haut de ce fichier). Jamais
    choisie par défaut : voir get_weather_provider() / WEATHER_PROVIDER.
    """
    GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
    FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
    # Une ville ne change pas de coordonnées : cache long (24h).
    _geocode_cache = TTLCache(ttl_seconds=86400)
    _forecast_cache = TTLCache(ttl_seconds=_CACHE_TTL_SECONDS)

    def is_configured(self) -> bool:
        return True  # pas de clé requise

    def get_conditions(self, city: str, match_date: Optional[datetime]) -> Optional[dict]:
        if not city:
            return None
        coords = self._geocode_cache.get_or_set_sync(city.strip().lower(), lambda: self._geocode(city))
        if not coords:
            return None
        cache_key = (coords, _date_bucket(match_date))
        return self._forecast_cache.get_or_set_sync(cache_key, lambda: self._fetch(coords, match_date))

    def _geocode(self, city: str) -> Optional[tuple]:
        try:
            resp = httpx.get(self.GEOCODING_URL, params={"name": city, "count": 1, "language": "fr"}, timeout=5.0)
            if resp.status_code != 200:
                return None
            results = resp.json().get("results") or []
            if not results:
                return None
            return (results[0]["latitude"], results[0]["longitude"])
        except Exception:
            return None

    def _fetch(self, coords: tuple, match_date: Optional[datetime]) -> Optional[dict]:
        lat, lon = coords
        try:
            resp = httpx.get(
                self.FORECAST_URL,
                params={
                    "latitude": lat, "longitude": lon,
                    "current": "temperature_2m,wind_speed_10m,relative_humidity_2m,weather_code",
                    "hourly": "temperature_2m,wind_speed_10m,relative_humidity_2m,weather_code",
                    "timezone": "auto",
                },
                timeout=5.0,
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
        except Exception:
            return None

        if match_date and match_date > datetime.utcnow() + timedelta(hours=1):
            return self._parse_hourly(data, match_date)
        return self._parse_current(data)

    @staticmethod
    def _parse_current(data: dict) -> Optional[dict]:
        try:
            cur = data["current"]
            return {
                "temp_c": round(cur["temperature_2m"], 1),
                "wind_kmh": round(cur["wind_speed_10m"], 1),
                "humidity_pct": cur["relative_humidity_2m"],
                "description": _WMO_DESCRIPTIONS.get(cur.get("weather_code"), "conditions inconnues"),
            }
        except (KeyError, TypeError):
            return None

    @staticmethod
    def _parse_hourly(data: dict, match_date: datetime) -> Optional[dict]:
        try:
            hourly = data["hourly"]
            times = [datetime.fromisoformat(t) for t in hourly["time"]]
            if not times:
                return None
            idx = min(range(len(times)), key=lambda i: abs(times[i] - match_date))
            return {
                "temp_c": round(hourly["temperature_2m"][idx], 1),
                "wind_kmh": round(hourly["wind_speed_10m"][idx], 1),
                "humidity_pct": hourly["relative_humidity_2m"][idx],
                "description": _WMO_DESCRIPTIONS.get(hourly["weather_code"][idx], "conditions inconnues"),
            }
        except (KeyError, IndexError, TypeError, ValueError):
            return None


def get_weather_provider() -> WeatherProvider:
    if settings.weather_provider == "open-meteo":
        return OpenMeteoProvider()
    return OpenWeatherMapProvider()

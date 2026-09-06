"""
Service de prédiction — orchestration : lit les Elo stockés en base
(app.models.Player.elo_*), calcule la probabilité de victoire via
services/elo.py, l'ajuste selon le head-to-head, la fatigue récente et les
conditions de match, puis génère un commentaire en langage naturel
(services/ai_narrative.py) qui explique ces chiffres.

Chaque ajustement (head-to-head, fatigue, météo) est une heuristique de bon
sens, capée et documentée dans son propre bloc `detail`, PAS un modèle
statistique calibré sur des données historiques — cf. ARCHITECTURE.md
section 5 "pistes d'évolution" pour les limites assumées et les pistes
(gradient boosting sur ces mêmes features, une fois assez de données
réelles accumulées pour calibrer correctement des poids).

IMPORTANT (cf. README "Synchronisation des données") : cette fonction ne
fait plus AUCUN appel réseau elle-même. `weather` et `market` sont fournis
en paramètre, déjà résolus par l'appelant (routers/analyses.py) à partir de
la ligne Fixture correspondante — dénormalisée en base par le job horaire
(scripts/sync_hourly.py). Avant ce refactor, build_prediction() appelait
directement weather_service.get_match_conditions() et
market_providers.get_market_provider().get_probability() à chaque requête
utilisateur ; c'était exactement l'appel "en direct depuis le front" que la
consigne d'origine interdit — le site n'interroge plus désormais que la
base locale, jamais une API externe au moment d'une requête utilisateur.
"""
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app import models
from app.services.elo import expected_score
from app.services import ai_narrative

MODEL_VERSION = "elo-h2h-fatigue-tournament-weather-market-v5"

# Probabilité de marché (services/polymarket_service.py) : fusion pondérée
# avec la probabilité issue de l'Elo + ajustements ci-dessus. Poids
# volontairement significatif (contrairement aux ajustements h2h/fatigue/
# météo/tournoi, resserrés vers 50/50 et jamais capables de changer le
# favori prédit) car le marché est, statistiquement, le meilleur prédicteur
# disponible — il intègre des informations (blessure non annoncée, forme
# cachée, motivation) que ce backend ne peut connaître par ailleurs. Peut
# donc, seul parmi tous les ajustements, faire basculer le favori prédit
# si le marché penche franchement pour l'autre joueur.
MARKET_BLEND_WEIGHT = 0.40

# Seuils d'ajustement météo : resserre la probabilité vers 50/50 quand les
# conditions rendent le match plus imprévisible. Volontairement conservateur
# (facteurs proches de 1.0) — voir weather_service.py pour la justification
# de cette approche (dampening plutôt qu'un biais dirigé vers un joueur).
WIND_STRONG_KMH = 30
WIND_MODERATE_KMH = 15
TEMP_EXTREME_HIGH_C = 32
TEMP_EXTREME_LOW_C = 5
# Mots-clés (description renvoyée par OpenWeatherMap/Open-Meteo, en anglais)
# identifiant une pluie ou un orage en cours/prévu — cf. _weather_dampening.
# Volontairement générique (même dégradation pour les deux joueurs) : on ne
# dispose d'aucune donnée historique par joueur (style de jeu, statistiques
# par temps de pluie) qui justifierait de diriger l'ajustement vers l'un des
# deux plutôt que l'autre — cf. weather_service.py.
RAIN_KEYWORDS = ("rain", "drizzle", "shower", "thunderstorm")
RAIN_DAMPENING_FACTOR = 0.90

FORM_MATCHES_COUNT = 5

# Head-to-head : n'ajuste la probabilité que s'il y a au moins ce nombre de
# confrontations passées (sinon 1-0 sur un seul match passé ferait basculer
# le pronostic sur une taille d'échantillon non significative). Ajustement
# capé à +/- H2H_MAX_ADJUSTMENT points de probabilité, quel que soit l'écart
# historique (ex: 8-0 ne doit pas peser plus que ça face à l'Elo actuel).
H2H_MIN_SAMPLE = 3
H2H_MAX_ADJUSTMENT = 0.06

# Fatigue : nombre de matchs joués dans cette fenêtre glissante avant la date
# du match analysé. Si l'écart de charge entre les deux joueurs est net et
# que le modèle favorise justement le joueur le plus chargé, on resserre sa
# probabilité vers 50/50 par prudence — même esprit que l'ajustement météo.
FATIGUE_WINDOW_DAYS = 14
FATIGUE_LOAD_GAP_TRIGGER = 2
FATIGUE_FACTOR = 0.95

# Format et niveau du tournoi : à Elo égal, un match en 5 sets gagnants
# (Grand Chelem messieurs) laisse statistiquement moins de place à la
# surprise qu'un format 3 sets — l'avantage du favori se creuse sur la
# distance (plus de sets = plus d'occasions pour le mieux classé de confirmer
# sa supériorité). À l'inverse, un tournoi ATP/WTA Tour "normal" (250/500,
# hors Masters 1000/Grand Chelem/Finals) est statistiquement plus sujet aux
# upsets (calendrier chargé, motivation variable des têtes de série,
# conditions moins homogènes). Heuristique capée, même esprit que les
# ajustements h2h/fatigue/météo ci-dessus — PAS un modèle calibré sur des
# taux d'upset réels par catégorie (cf. ARCHITECTURE.md pistes d'évolution).
TOURNEY_BO5_SHARPEN_FACTOR = 1.08
TOURNEY_LOWER_TIER_DAMPEN_FACTOR = 0.95

GRAND_SLAM_NAMES = ["australian open", "roland garros", "french open", "wimbledon", "us open"]
TOP_TIER_TOURNAMENT_NAMES = GRAND_SLAM_NAMES + [
    "indian wells", "miami open", "monte-carlo", "monte carlo", "madrid open",
    "italian open", "internazionali", "rome",
    "canadian open", "rogers cup", "national bank open",
    "cincinnati", "western & southern",
    "shanghai masters", "paris masters", "rolex paris masters", "bercy",
    "qatar", "dubai", "wuhan", "beijing",
    "atp finals", "nitto atp finals", "wta finals",
]


def _name_matches_any(name: str, needles: list[str]) -> bool:
    n = name.lower()
    return any(needle in n for needle in needles)


def _tournament_context_and_adjustment(
    probability: float, tournament_name: Optional[str], player1_tour,
) -> tuple[float, Optional[dict], Optional[dict]]:
    """Retourne (probabilité éventuellement ajustée, détail de l'ajustement ou
    None, contexte du tournoi ou None). N'ajuste rien si aucun nom de tournoi
    n'a été transmis (analyse manuelle sans match live sélectionné)."""
    if not tournament_name:
        return probability, None, None

    is_grand_slam = _name_matches_any(tournament_name, GRAND_SLAM_NAMES)
    # Le format 5 sets ne s'applique qu'au tableau messieurs en Grand Chelem.
    is_bo5 = is_grand_slam and player1_tour == models.TourEnum.atp
    is_top_tier = is_grand_slam or _name_matches_any(tournament_name, TOP_TIER_TOURNAMENT_NAMES)

    context = {
        "name": tournament_name,
        "format": "Bo5 (5 sets gagnants)" if is_bo5 else "Bo3 (3 sets gagnants)",
        "tier": "Grand Chelem" if is_grand_slam else ("Masters 1000 / WTA 1000 / Finals" if is_top_tier else "ATP/WTA Tour"),
    }

    factor = 1.0
    reasons = []
    if is_bo5:
        factor *= TOURNEY_BO5_SHARPEN_FACTOR
        reasons.append("format 5 sets (Grand Chelem messieurs) : l'avantage du favori se creuse sur la distance")
    elif not is_top_tier:
        factor *= TOURNEY_LOWER_TIER_DAMPEN_FACTOR
        reasons.append("tournoi ATP/WTA Tour standard, hors Masters/Grand Chelem/Finals : plus sujet aux surprises")

    if abs(factor - 1.0) < 0.001:
        return probability, None, context

    before = probability
    adjusted = min(0.99, max(0.5, 0.5 + (probability - 0.5) * factor))
    adjustment = {
        "note": "Contexte du tournoi (" + "; ".join(reasons) + ") — probabilité ajustée en conséquence "
                "(heuristique, pas un modèle calibré sur des taux d'upset réels par catégorie).",
        "probability_before_tournament": round(before, 4),
    }
    return adjusted, adjustment, context


def _apply_market_blend(
    probability: float, winner: models.Player, player1: models.Player, player2: models.Player,
    market: Optional[dict],
) -> tuple[float, models.Player, Optional[dict]]:
    """Fusionne la probabilité modèle avec la probabilité de marché Polymarket
    (si un marché a été trouvé sans ambiguïté, cf. polymarket_service.py).
    Seul ajustement capable de changer le favori prédit — cf. commentaire
    sur MARKET_BLEND_WEIGHT plus haut."""
    if not market:
        return probability, winner, None

    market_p1, market_p2 = market["player1_prob"], market["player2_prob"]
    market_prob_for_winner = market_p1 if winner.id == player1.id else market_p2

    before = probability
    blended = probability * (1 - MARKET_BLEND_WEIGHT) + market_prob_for_winner * MARKET_BLEND_WEIGHT

    if blended >= 0.5:
        new_winner, new_probability = winner, min(0.99, max(0.5, blended))
    else:
        new_winner = player2 if winner.id == player1.id else player1
        new_probability = min(0.99, max(0.5, 1 - blended))

    flipped = new_winner.id != winner.id
    note = (
        f"Le marché prédictif Polymarket donne {round(market_prob_for_winner * 100, 1)}% à {winner.name} "
        f"(contre {round(before * 100, 1)}% pour le modèle seul) — probabilité fusionnée avec un poids "
        f"marché de {int(MARKET_BLEND_WEIGHT * 100)}%."
    )
    if flipped:
        note += f" Le marché penche pour l'autre joueur : {new_winner.name} devient le favori prédit."

    detail_entry = {
        "note": note,
        "probability_before_market": round(before, 4),
        "market_player1_prob": round(market_p1, 4),
        "market_player2_prob": round(market_p2, 4),
        "market_question": market.get("question", ""),
        "winner_flipped": flipped,
    }
    return new_probability, new_winner, detail_entry


def _recent_form(db: Optional[Session], player_id) -> Optional[dict]:
    """Forme récente calculée sur les vrais matchs importés depuis les CSV
    Jeff Sackmann (cf. scripts/ingest_sackmann.py et scripts/sync_daily.py),
    PAS une estimation. None si aucun historique n'est disponible (base
    vide/démo, ou db=None en test)."""
    if db is None:
        return None
    matches = (
        db.query(models.Match)
        .filter(or_(models.Match.player1_id == player_id, models.Match.player2_id == player_id))
        .filter(models.Match.winner_id.isnot(None))
        .order_by(models.Match.tourney_date.desc())
        .limit(FORM_MATCHES_COUNT)
        .all()
    )
    if not matches:
        return None

    results = ["V" if m.winner_id == player_id else "D" for m in matches]
    wins = results.count("V")
    losses = len(results) - wins

    if len(results) < 3:
        label = "Historique récent limité"
    elif wins >= 4:
        label = "En grande forme"
    elif wins == 3:
        label = "Forme correcte"
    elif wins == 2:
        label = "Forme irrégulière"
    else:
        label = "Forme fragile"

    return {"results": results, "wins": wins, "losses": losses, "label": label}


def _head_to_head(db: Optional[Session], p1_id, p2_id) -> Optional[dict]:
    """Bilan des confrontations directes entre les deux joueurs (peu importe
    qui était "player1"/"player2" à l'époque), sur tout l'historique connu.
    None si aucune confrontation recensée en base."""
    if db is None:
        return None
    matches = (
        db.query(models.Match)
        .filter(
            or_(
                and_(models.Match.player1_id == p1_id, models.Match.player2_id == p2_id),
                and_(models.Match.player1_id == p2_id, models.Match.player2_id == p1_id),
            )
        )
        .filter(models.Match.winner_id.isnot(None))
        .order_by(models.Match.tourney_date.desc())
        .all()
    )
    if not matches:
        return None

    wins1 = sum(1 for m in matches if m.winner_id == p1_id)
    wins2 = len(matches) - wins1
    recent_meetings = [
        {
            "date": m.tourney_date.date().isoformat() if m.tourney_date else None,
            "winner_id": m.winner_id,
            "surface": m.surface.value if m.surface else None,
            "round": m.round,
            "score": m.score,
        }
        for m in matches[:5]
    ]
    return {
        "total": len(matches),
        "wins_player1": wins1,
        "wins_player2": wins2,
        "recent_meetings": recent_meetings,
    }


def _fatigue(db: Optional[Session], player_id, reference_date: Optional[datetime]) -> Optional[dict]:
    """Charge de matchs récente : nombre de matchs joués dans les
    FATIGUE_WINDOW_DAYS jours avant la date du match analysé (ou avant
    aujourd'hui si aucune date n'est précisée), et jours de repos depuis le
    dernier match. None si aucun match récent en base pour ce joueur."""
    if db is None:
        return None
    ref = reference_date or datetime.utcnow()
    window_start = ref - timedelta(days=FATIGUE_WINDOW_DAYS)
    recent_matches = (
        db.query(models.Match)
        .filter(
            or_(models.Match.player1_id == player_id, models.Match.player2_id == player_id),
            models.Match.winner_id.isnot(None),
            models.Match.tourney_date.isnot(None),
            models.Match.tourney_date >= window_start,
            models.Match.tourney_date <= ref,
        )
        .order_by(models.Match.tourney_date.desc())
        .all()
    )
    if not recent_matches:
        return {"matches_last_14_days": 0, "days_since_last_match": None}

    days_since_last = (ref - recent_matches[0].tourney_date).days
    return {"matches_last_14_days": len(recent_matches), "days_since_last_match": days_since_last}


def _weather_dampening(weather: dict) -> tuple[float, list[str]]:
    factor = 1.0
    notes = []

    wind = weather.get("wind_kmh")
    if wind is not None:
        if wind >= WIND_STRONG_KMH:
            factor *= 0.85
            notes.append(f"vent fort ({wind} km/h)")
        elif wind >= WIND_MODERATE_KMH:
            factor *= 0.93
            notes.append(f"vent modéré ({wind} km/h)")

    temp = weather.get("temp_c")
    if temp is not None and (temp >= TEMP_EXTREME_HIGH_C or temp <= TEMP_EXTREME_LOW_C):
        factor *= 0.95
        notes.append(f"température extrême ({temp}°C)")

    description = (weather.get("description") or "").lower()
    if any(kw in description for kw in RAIN_KEYWORDS):
        factor *= RAIN_DAMPENING_FACTOR
        notes.append(f"pluie ({description})")

    return factor, notes


def build_prediction(
    db: Session,
    player1: models.Player,
    player2: models.Player,
    surface: Optional[str] = None,
    match_city: Optional[str] = None,
    match_date: Optional[datetime] = None,
    tournament_name: Optional[str] = None,
    weather: Optional[dict] = None,
    market: Optional[dict] = None,
) -> dict:
    """
    match_city n'est plus utilisé ici pour aller chercher la météo (cf.
    docstring du module) — conservé pour compatibilité de signature/logging
    côté appelant. `weather` ({indoor, temp_c, wind_kmh, humidity_pct,
    description} ou {"indoor": True} ou None) et `market`
    ({player1_prob, player2_prob, question} ou None) doivent être fournis
    déjà résolus par l'appelant, dans le référentiel (player1, player2) de
    CET appel (cf. routers/analyses.py::_market_from_fixture pour la
    ré-orientation depuis l'ordre stocké sur la Fixture)."""
    surface_field = f"elo_{surface}" if surface in ("hard", "clay", "grass") else "elo_overall"
    elo_a = getattr(player1, surface_field, player1.elo_overall)
    elo_b = getattr(player2, surface_field, player2.elo_overall)

    p_a = expected_score(elo_a, elo_b)
    if p_a >= 0.5:
        winner, probability = player1, p_a
    else:
        winner, probability = player2, 1 - p_a

    detail = {
        "elo_player1": round(elo_a, 1),
        "elo_player2": round(elo_b, 1),
        "elo_diff": round(elo_a - elo_b, 1),
        "surface_used": surface or "overall",
        "method": "elo-logistic",
    }

    # Forme récente (vrais matchs en base) — affichée gratuitement, comme le
    # reste du "teaser" avant la partie verrouillée de l'analyse (probabilité
    # exacte + détail Elo/météo, cf. AnalysisOut côté frontend).
    form1 = _recent_form(db, player1.id)
    form2 = _recent_form(db, player2.id)
    if form1:
        detail["form_player1"] = form1
    if form2:
        detail["form_player2"] = form2

    # Matchup droitier/gaucher : fait purement informatif (donnée réelle en
    # base, Player.hand), pas d'ajustement de probabilité -- on ne dispose
    # d'aucune donnée de performance par joueur en fonction de la main
    # adverse pour justifier de diriger le pronostic. Sert surtout de
    # matière première pour le commentaire de Claude (cf. ai_narrative.py),
    # qui peut légitimement noter qu'un droitier au revers à une main
    # affronte un gaucher, sans avoir à l'inventer.
    hand1, hand2 = getattr(player1, "hand", None), getattr(player2, "hand", None)
    if hand1 and hand2 and hand1.upper() != hand2.upper():
        left_name = player1.name if hand1.upper() == "L" else player2.name
        right_name = player2.name if hand1.upper() == "L" else player1.name
        detail["style_matchup"] = {
            "type": "droitier_vs_gaucher",
            "left_handed_player": left_name,
            "right_handed_player": right_name,
            "note": f"{left_name} (gaucher) affronte {right_name} (droitier) -- "
                    "les effets et angles de balle changent par rapport à un match "
                    "entre deux droitiers, sans que ça favorise mécaniquement l'un ou l'autre.",
        }

    # Style de jeu (cf. scripts/seed_playing_styles.py) : note rédigée à la main,
    # présente seulement pour les joueurs suffisamment établis -- purement
    # informatif pour Claude (jamais d'ajustement de probabilité dessus, on ne
    # calibre rien sur du texte qualitatif).
    if getattr(player1, "playing_style", None):
        detail["style_player1"] = player1.playing_style
    if getattr(player2, "playing_style", None):
        detail["style_player2"] = player2.playing_style

    # Head-to-head : bilan des confrontations directes, ajustement seulement
    # si l'échantillon est assez grand (H2H_MIN_SAMPLE) pour être significatif.
    h2h = _head_to_head(db, player1.id, player2.id)
    if h2h:
        detail["h2h"] = h2h
        if h2h["total"] >= H2H_MIN_SAMPLE and h2h["wins_player1"] != h2h["wins_player2"]:
            leader_is_p1 = h2h["wins_player1"] > h2h["wins_player2"]
            leader_name = player1.name if leader_is_p1 else player2.name
            leader_wins = max(h2h["wins_player1"], h2h["wins_player2"])
            trailer_wins = min(h2h["wins_player1"], h2h["wins_player2"])
            margin = (leader_wins - trailer_wins) / h2h["total"]
            leader_is_predicted_winner = (winner.id == player1.id) == leader_is_p1
            signed_adjustment = margin if leader_is_predicted_winner else -margin
            adjustment = max(-H2H_MAX_ADJUSTMENT, min(H2H_MAX_ADJUSTMENT, signed_adjustment * H2H_MAX_ADJUSTMENT))
            if abs(adjustment) > 0.001:
                before = probability
                probability = min(0.99, max(0.5, probability + adjustment))
                detail["h2h_adjustment"] = {
                    "note": f"{leader_name} mène {leader_wins}-{trailer_wins} en confrontations directes "
                            "— probabilité légèrement ajustée en conséquence (heuristique, pas un modèle calibré).",
                    "probability_before_h2h": round(before, 4),
                }

    # Fatigue : si l'écart de charge récente est net ET que le modèle favorise
    # justement le joueur le plus chargé, on resserre sa probabilité par
    # prudence — même esprit que l'ajustement météo ci-dessous.
    fatigue1 = _fatigue(db, player1.id, match_date)
    fatigue2 = _fatigue(db, player2.id, match_date)
    if fatigue1:
        detail["fatigue_player1"] = fatigue1
    if fatigue2:
        detail["fatigue_player2"] = fatigue2
    if fatigue1 and fatigue2:
        load1, load2 = fatigue1["matches_last_14_days"], fatigue2["matches_last_14_days"]
        if abs(load1 - load2) >= FATIGUE_LOAD_GAP_TRIGGER:
            more_loaded_is_p1 = load1 > load2
            winner_is_more_loaded = (winner.id == player1.id) == more_loaded_is_p1
            if winner_is_more_loaded:
                more_loaded_name = player1.name if more_loaded_is_p1 else player2.name
                before = probability
                probability = 0.5 + (probability - 0.5) * FATIGUE_FACTOR
                detail["fatigue_adjustment"] = {
                    "note": f"{more_loaded_name} a enchaîné {max(load1, load2)} match(s) sur les 14 derniers "
                            f"jours contre {min(load1, load2)} pour l'adversaire — probabilité resserrée par "
                            "prudence (heuristique, pas un modèle calibré sur la fatigue réelle).",
                    "probability_before_fatigue": round(before, 4),
                }

    # Format et niveau du tournoi (Bo3/Bo5, Grand Chelem/Masters vs Tour
    # standard) — seulement si un nom de tournoi a été transmis (match live
    # sélectionné par l'utilisateur, cf. routers/analyses.py).
    probability, tournament_adjustment, tournament_context = _tournament_context_and_adjustment(
        probability, tournament_name, getattr(player1, "tour", None)
    )
    if tournament_context:
        detail["tournament_context"] = tournament_context
    if tournament_adjustment:
        detail["tournament_adjustment"] = tournament_adjustment

    # Conditions de match (optionnel — fourni par l'appelant, cf. docstring
    # de build_prediction : plus aucun appel météo live ici).
    if weather is not None:
        detail["weather"] = weather
        if not weather.get("indoor"):
            factor, notes = _weather_dampening(weather)
            if factor < 1.0:
                adjusted = round(0.5 + (probability - 0.5) * factor, 4)
                detail["weather_adjustment"] = {
                    "note": "Conditions difficiles (" + "; ".join(notes) + ") — probabilité resserrée "
                            "vers 50/50 (heuristique de bon sens, pas un modèle statistique calibré).",
                    "probability_before_weather": round(probability, 4),
                }
                probability = adjusted

    # Probabilité de marché (optionnel — fourni par l'appelant, cf. docstring
    # de build_prediction : plus aucun appel Polymarket live ici) : seul
    # ajustement pouvant changer le favori prédit (cf. MARKET_BLEND_WEIGHT).
    probability, winner, market_adjustment = _apply_market_blend(probability, winner, player1, player2, market)
    if market_adjustment:
        detail["market_adjustment"] = market_adjustment

    # Commentaire d'analyse en langage naturel (optionnel — cf. ai_narrative.py) :
    # explique les chiffres ci-dessus, n'influence jamais la probabilité elle-même.
    detail["ai_narrative"] = ai_narrative.generate_narrative({
        **detail,
        "player1_name": player1.name,
        "player2_name": player2.name,
        "winner_name": winner.name,
        "win_probability": probability,
    })

    return {
        "predicted_winner_id": winner.id,
        "win_probability": round(probability, 4),
        "model_version": MODEL_VERSION,
        "detail": detail,
    }

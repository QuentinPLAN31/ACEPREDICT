"""
Analyse approfondie en langage naturel, générée par l'API Anthropic (Claude)
à partir des facteurs déjà calculés par prediction.py (niveau général des
deux joueurs -- dérivé de l'Elo interne mais jamais exposé comme tel --,
forme récente, head-to-head, fatigue, météo). C'est la partie "un vrai
travail de fond" de l'analyse : le modèle donne un chiffre, ce service
explique le chiffre. Le prompt ci-dessous parle volontairement de "niveau
général" et jamais d'"Elo" : ce vocabulaire technique n'est pas censé
apparaître dans une app grand public non initiée au tennis.
Optionnel et à dégradation gracieuse, comme Stripe/météo/LiveTennisAPI
ailleurs dans ce backend : sans ANTHROPIC_API_KEY configurée (ou en cas
d'erreur réseau/API), generate_narrative() retourne None et l'analyse
continue de fonctionner avec les chiffres bruts uniquement — jamais
d'exception qui remonterait jusqu'à /analyses.
Le prompt interdit explicitement au modèle d'inventer des informations
(blessures, actualités, stats non fournies) : il ne doit raisonner QUE sur
les chiffres transmis dans le contexte, pour rester honnête sur ce que
l'app sait réellement.
"""
import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

API_URL = "https://api.anthropic.com/v1/messages"
TIMEOUT_SECONDS = 45.0

# Le format de sortie voulu est volontairement COURT (une phrase de synthèse +
# quelques puces, cf. _build_prompt) : le lecteur a déjà les chiffres bruts
# sous forme de barres visuelles ailleurs dans l'UI, ce texte n'a plus à les
# répéter. max_tokens reste généreux uniquement pour ne jamais tronquer une
# réponse si le modèle déborde légèrement du format demandé.
#
# claude-sonnet-5 fait de l'extended thinking par défaut sur les prompts
# complexes (le nôtre en fait partie) : sans le contrôler, il peut consommer
# TOUT max_tokens en "thinking" et ne jamais produire de texte
# (stop_reason=max_tokens, output vide). Ce modèle utilise le format
# "adaptive thinking" (différent de l'ancien thinking.type=enabled +
# budget_tokens, qu'il rejette en 400) : thinking.type=adaptive laisse le
# modèle décider lui-même s'il réfléchit, et output_config.effort=low limite
# l'ampleur de cette réflexion pour garantir qu'il reste de la place pour le
# texte final dans max_tokens.
MAX_TOKENS = 4400

# NB: avec `thinking` activé, l'API Anthropic n'accepte plus le paramètre
# `temperature` (400 "temperature is deprecated for this model") -- on ne
# l'envoie donc jamais dans le payload.
TEMPERATURE = 0.3


def is_configured() -> bool:
    return bool(settings.anthropic_api_key)


def generate_narrative(context: dict) -> Optional[str]:
    if not is_configured():
        return None

    try:
        resp = httpx.post(
            API_URL,
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": settings.anthropic_model,
                "max_tokens": MAX_TOKENS,
                "thinking": {"type": "adaptive"},
                "output_config": {"effort": "low"},
                "messages": [{"role": "user", "content": _build_prompt(context)}],
            },
            timeout=TIMEOUT_SECONDS,
        )
        if resp.status_code != 200:
            # Dégradation gracieuse (l'analyse continue sans commentaire), mais on
            # log quand même -- sans ça, une clé invalide ou un nom de modèle
            # obsolète désactive l'analyse Claude en silence, sans jamais rien
            # remonter nulle part (c'est ce qui s'est passé avec l'ancien défaut
            # "claude-sonnet-4-6", qui n'existait plus).
            logger.warning(
                "ai_narrative: réponse Anthropic non-200 (status=%s, model=%s) : %s",
                resp.status_code, settings.anthropic_model, resp.text[:500],
            )
            return None

        blocks = resp.json().get("content", [])
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
        return text or None
    except Exception:
        logger.exception("ai_narrative: exception lors de l'appel à l'API Anthropic")
        return None


# Même calibration que le frontend (visitennis_1.html::eloToLevelPct /
# levelWord) : traduit l'Elo interne (jamais montré tel quel) en repère
# lisible sans initiation -- un pourcentage de niveau + un mot, centrés sur
# la valeur de départ 1500 plutôt que sur une plage brute qui écraserait
# tout le monde en bas de l'échelle. Les deux implémentations doivent rester
# alignées pour que le récit de Claude et l'UI racontent la même histoire.
def _elo_to_level_pct(elo: Optional[float]) -> Optional[int]:
    if elo is None:
        return None
    import math
    pct = round(50 + 50 * math.tanh((elo - 1500) / 150))
    return max(3, min(100, pct))


def _level_word(pct: Optional[int]) -> str:
    if pct is None:
        return "Inconnu"
    if pct >= 80:
        return "Excellent"
    if pct >= 65:
        return "Très solide"
    if pct >= 50:
        return "Solide"
    if pct >= 35:
        return "Correct"
    if pct >= 20:
        return "En progression"
    return "Débutant"


def _level_context_line(p1: str, p2: str, elo1: Optional[float], elo2: Optional[float]) -> str:
    pct1, pct2 = _elo_to_level_pct(elo1), _elo_to_level_pct(elo2)
    if pct1 is None or pct2 is None:
        return f"Niveau général : donnée insuffisante pour {p1} et/ou {p2}."
    return (
        f"Niveau général (sur 100, 50 = niveau moyen du circuit) : "
        f"{p1} {pct1} ({_level_word(pct1)}) — {p2} {pct2} ({_level_word(pct2)}), "
        f"écart de {abs(pct1 - pct2)} points de niveau"
    )


def _build_prompt(ctx: dict) -> str:
    p1, p2 = ctx["player1_name"], ctx["player2_name"]

    lines = [
        "Tu es un analyste tennis professionnel senior qui rédige pour une "
        "application de pronostics payante grand public, PAS pour des "
        "initiés : n'utilise JAMAIS le mot \"Elo\" ni aucun jargon de "
        "système de classement/rating dans ta réponse -- dis \"niveau "
        "général\" ou \"niveau\" à la place, toujours en langage courant. "
        "Le lecteur voit déjà, ailleurs à l'écran, tous les chiffres bruts "
        "sous forme de barres visuelles (probabilité, niveau général, "
        "forme, confrontations directes, charge de matchs) : ton rôle "
        "n'est PAS de les répéter ni de les reformuler en phrases, mais "
        "d'apporter une VALEUR AJOUTÉE que ces chiffres seuls ne montrent "
        "pas — en croisant mentalement TOUS les facteurs disponibles "
        "(écart de niveau général, dynamique de forme, poids réel du H2H "
        "selon son échantillon, fatigue, format/niveau du tournoi, "
        "probabilité de marché si disponible, conditions de match) pour en "
        "tirer une lecture experte. Si une probabilité de marché est "
        "fournie, commente explicitement si elle confirme ou contredit le "
        "niveau général estimé et ce que ça implique pour la fiabilité du "
        "pronostic. "
        "Format STRICT en puces courtes uniquement -- AUCUN paragraphe, "
        "AUCUN bloc de texte continu de plusieurs phrases : chaque idée "
        "tient sur UNE puce autonome et dense. Le lecteur va payer pour "
        "cette analyse : elle doit avoir une vraie valeur ajoutée experte, "
        "pas quatre lignes vagues. "
        "Ligne 1 = une seule phrase de synthèse percutante (max 25 mots, "
        "pas de préfixe, pas de puce) donnant le facteur le plus décisif "
        "du pronostic. "
        f"Puis, séparé par une ligne vide, EXACTEMENT ces 9 sections dans "
        "cet ordre, chacune introduite par une ligne '### ' suivie du nom "
        "de la section en majuscules et RIEN d'autre sur cette ligne, "
        "puis son contenu -- pour les sections à puces, chaque puce sur sa "
        "propre ligne, commençant par \"• \", aucune numérotation ; pour "
        "MOMENT_CLE et VERDICT_EXPERT, jamais de puce, un texte fluide "
        "directement (cf. consignes de chacune ci-dessous) : "
        f"### FORCES_J1 -- exactement 3 puces (max 16 mots chacune) sur les "
        f"points forts concrets de {p1} DANS CE MATCH précis face à ce style "
        f"d'adversaire (pas des généralités de carrière). "
        f"### FAIBLESSES_J1 -- exactement 2 à 3 puces (max 16 mots chacune) "
        f"sur ce qui pourrait désavantager {p1} spécifiquement face à {p2} "
        "(style de jeu adverse, écart de niveau général, fatigue, surface, "
        "tout facteur concret fourni ci-dessous). "
        f"### FORCES_J2 -- même exercice pour {p2} (exactement 3 puces, max "
        "16 mots chacune). "
        f"### FAIBLESSES_J2 -- même exercice pour {p2} (2 à 3 puces, max 16 "
        "mots chacune). "
        "### CROISEMENT -- exactement 3 puces (max 20 mots chacune) qui "
        "croisent chacune explicitement au moins deux facteurs entre eux "
        "(ex: comment la forme récente renforce ou contredit l'écart de "
        "niveau général, comment le format du tournoi amplifie ou atténue "
        "tel autre facteur) -- jamais une puce qui ne fait que répéter un "
        "chiffre déjà affiché ailleurs à l'écran. "
        "### MOMENT_CLE -- AUCUNE puce : une seule phrase percutante (max "
        "30 mots) identifiant LE moment ou point de bascule tactique le "
        "plus décisif à surveiller pendant le match (ex: un jeu précis, un "
        "enchaînement, une situation de pression) -- concret et visuel, "
        "jamais une généralité déjà dite ailleurs. "
        "### SCENARIOS -- exactement 2 puces, chacune un scénario tactique "
        "concret et distinct pour CE match précis (max 30 mots chacune) : "
        "comment le match pourrait se dérouler compte tenu des styles, de "
        "la forme et du contexte -- pas une simple probabilité chiffrée, "
        "un vrai scénario de déroulé (ex: qui doit imposer quoi, à quel "
        "moment du match ça peut basculer). "
        "### VIGILANCE -- 3 à 4 puces courtes (max 18 mots chacune) parmi : "
        "le principal risque de contre-performance/upset, la limite de "
        "fiabilité la plus importante (échantillon faible, donnée absente, "
        "signaux contradictoires...), un facteur secondaire qui pourrait "
        "faire basculer le match, et le niveau de confiance global assumé "
        "-- jamais une puce qui redit ce qui est déjà dans la ligne 1 ou "
        "les autres sections. "
        "### VERDICT_EXPERT -- AUCUNE puce : 2 à 3 phrases fluides, ton "
        "éditorial et personnel (comme la conclusion signée d'un chroniqueur "
        "tennis), qui résument ta lecture experte du match sans répéter un "
        "chiffre ou une idée déjà donnée dans les sections précédentes -- la "
        "vraie valeur ajoutée de fin, ce qui donnerait envie au lecteur de "
        "faire confiance à l'analyse. "
        "Aucun titre en gras, aucun texte hors de ce format, aucune phrase "
        "de liaison creuse -- chaque puce doit apporter une information "
        "nouvelle, jamais de redite entre sections. "
        "Base-toi STRICTEMENT sur les données fournies ci-dessous : "
        "n'invente aucune statistique, blessure, actualité, classement ou "
        "style de jeu non fourni — si une donnée manque pour étayer une "
        "section (ex: pas de style de jeu connu), raisonne sur ce qui est "
        "disponible (niveau général, forme, H2H, fatigue, tournoi, marché) "
        "plutôt que d'inventer. Si une information de style de jeu est "
        "explicitement marquée [INFORMATION INCERTAINE], ne t'appuie pas "
        "dessus pour un argument important — mentionne-la au mieux avec la "
        "réserve qui va avec.",
        "",
        f"Match : {p1} vs {p2}" + (f" (surface : {ctx['surface_used']})" if ctx.get("surface_used") and ctx["surface_used"] != "overall" else ""),
        _level_context_line(p1, p2, ctx.get("elo_player1"), ctx.get("elo_player2")),
    ]

    f1, f2 = ctx.get("form_player1"), ctx.get("form_player2")
    if f1 and f2:
        lines.append(
            f"Forme sur les 5 derniers matchs : {p1} {f1['wins']}V-{f1['losses']}D "
            f"({f1['label']}), {p2} {f2['wins']}V-{f2['losses']}D ({f2['label']})"
        )

    h2h = ctx.get("h2h")
    if h2h:
        lines.append(
            f"Confrontations directes : {p1} {h2h['wins_player1']} — "
            f"{h2h['wins_player2']} {p2} (sur {h2h['total']} match(s) recensé(s))"
        )

    fat1, fat2 = ctx.get("fatigue_player1"), ctx.get("fatigue_player2")
    if fat1:
        lines.append(f"Charge de {p1} : {fat1['matches_last_14_days']} match(s) sur les 14 derniers jours")
    if fat2:
        lines.append(f"Charge de {p2} : {fat2['matches_last_14_days']} match(s) sur les 14 derniers jours")

    weather = ctx.get("weather")
    if weather and not weather.get("indoor"):
        lines.append(
            f"Météo prévue : {weather.get('description', 'inconnue')}, "
            f"{weather.get('temp_c', '?')}°C, vent {weather.get('wind_kmh', '?')} km/h"
        )

    style_matchup = ctx.get("style_matchup")
    if style_matchup:
        lines.append(f"Particularité du match : {style_matchup['note']}")

    style1, style2 = ctx.get("style_player1"), ctx.get("style_player2")
    if style1:
        tag = " [INFORMATION INCERTAINE, à traiter avec prudence]" if ctx.get("style_player1_confidence") == "faible" else ""
        lines.append(f"Style de jeu de {p1}{tag} : {style1}")
    if style2:
        tag = " [INFORMATION INCERTAINE, à traiter avec prudence]" if ctx.get("style_player2_confidence") == "faible" else ""
        lines.append(f"Style de jeu de {p2}{tag} : {style2}")

    tournament = ctx.get("tournament_context")
    if tournament:
        lines.append(
            f"Tournoi : {tournament['name']} ({tournament['tier']}, format {tournament['format']})"
        )

    market = ctx.get("market_adjustment")
    if market:
        lines.append(
            f"Marché prédictif (Polymarket) : {round(market['market_player1_prob'] * 100, 1)}% pour {p1} — "
            f"{round(market['market_player2_prob'] * 100, 1)}% pour {p2}"
        )

    lines += [
        f"Probabilité calculée par le modèle : {round(ctx['win_probability'] * 100, 1)}% pour {ctx['winner_name']}",
        "",
        "Rappel du format : 1 phrase de synthèse SANS puce, puis dans cet "
        "ordre exact -- ### FORCES_J1 (3 puces), ### FAIBLESSES_J1 (2-3 "
        "puces), ### FORCES_J2 (3 puces), ### FAIBLESSES_J2 (2-3 puces), "
        "### CROISEMENT (3 puces), ### MOMENT_CLE (1 phrase SANS puce), "
        "### SCENARIOS (2 puces), ### VIGILANCE (3 à 4 puces), "
        "### VERDICT_EXPERT (2-3 phrases SANS puce) -- rien de redondant "
        "avec les chiffres déjà donnés ci-dessus ni entre les sections "
        "elles-mêmes, aucun remplissage. Ne donne jamais de conseil de "
        "pari, de cote, ni de garantie de résultat.",
    ]

    return "\n".join(lines)

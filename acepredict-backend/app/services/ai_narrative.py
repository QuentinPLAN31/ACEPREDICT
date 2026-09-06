"""
Analyse approfondie en langage naturel, générée par l'API Anthropic (Claude)
à partir des facteurs déjà calculés par prediction.py (Elo, forme récente,
head-to-head, fatigue, météo). C'est la partie "un vrai travail de fond" de
l'analyse : le modèle Elo donne un chiffre, ce service explique le chiffre.
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
# complexes (le nôtre en fait partie) : sans budget explicite, il peut
# consommer TOUT max_tokens en "thinking" et ne jamais produire de texte
# (stop_reason=max_tokens, output vide). On active donc `thinking` avec un
# budget plafonné et strictement inférieur à max_tokens, pour garantir qu'il
# reste toujours de la place pour le texte final.
MAX_TOKENS = 2000
THINKING_BUDGET = 700

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
                "thinking": {"type": "enabled", "budget_tokens": THINKING_BUDGET},
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


def _build_prompt(ctx: dict) -> str:
    p1, p2 = ctx["player1_name"], ctx["player2_name"]

    lines = [
        "Tu es un analyste tennis professionnel senior qui rédige pour une "
        "application de pronostics payante. Le lecteur voit déjà, ailleurs à "
        "l'écran, tous les chiffres bruts sous forme de barres visuelles "
        "(probabilité, Elo, forme, confrontations directes, charge de "
        "matchs) : ton rôle n'est PAS de les répéter ni de les reformuler en "
        "phrases, mais d'apporter une VALEUR AJOUTÉE que ces chiffres seuls "
        "ne montrent pas — en croisant mentalement TOUS les facteurs "
        "disponibles (écart Elo, dynamique de forme, poids réel du H2H selon "
        "son échantillon, fatigue, format/niveau du tournoi, probabilité de "
        "marché si disponible, conditions de match) pour en tirer une "
        "lecture experte. Si une probabilité de marché est fournie, "
        "commente explicitement si elle confirme ou contredit le modèle "
        "Elo et ce que ça implique pour la fiabilité du pronostic. Format "
        "STRICT, dense mais "
        "sans aucun remplissage — chaque phrase doit apporter une "
        "information nouvelle, zéro phrase de liaison creuse : "
        "ligne 1 = une seule phrase de synthèse percutante (max 25 mots, pas "
        "de préfixe) donnant le facteur le plus décisif du pronostic ; "
        "puis, séparé par une ligne vide, TOUJOURS deux paragraphes de 3 à "
        "4 phrases chacun (jamais un seul, jamais de remplissage) : le "
        "premier croise explicitement au moins deux facteurs entre eux "
        "(ex: comment la forme récente renforce ou contredit l'écart Elo, "
        "comment le format du tournoi amplifie ou atténue tel autre "
        "facteur) — jamais une simple reformulation d'un chiffre isolé ; "
        "le second propose une lecture complémentaire et distincte (un "
        "scénario tactique concret probable, OU une mise en perspective "
        "de la fiabilité réelle du pronostic au vu de l'échantillon "
        "disponible) — jamais une redite du premier paragraphe ; "
        "puis, séparé par une ligne vide, chacune sur sa propre ligne "
        "commençant par \"• \", 3 à 4 puces courtes (max 18 mots chacune) "
        "parmi : le principal risque de contre-performance/upset, la "
        "limite de fiabilité la plus importante (échantillon faible, "
        "donnée absente, signaux contradictoires...), un facteur "
        "secondaire qui pourrait faire basculer le match, et le niveau de "
        "confiance global assumé — jamais une puce qui redit ce qui est "
        "déjà dans la ligne 1 ou les paragraphes. Aucun titre, aucun gras. "
        "Base-toi STRICTEMENT sur les données fournies ci-dessous : "
        "n'invente aucune statistique, blessure, actualité, classement ou "
        "style de jeu non fourni — si une donnée manque, dis-le plutôt que "
        "de l'inventer. Si une information de style de jeu est explicitement "
        "marquée [INFORMATION INCERTAINE], ne t'appuie pas dessus pour un "
        "argument important — mentionne-la au mieux avec la réserve qui va avec.",
        "",
        f"Match : {p1} vs {p2}" + (f" (surface : {ctx['surface_used']})" if ctx.get("surface_used") and ctx["surface_used"] != "overall" else ""),
        f"Elo : {p1} {ctx['elo_player1']} — {p2} {ctx['elo_player2']} (écart {ctx['elo_diff']})",
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
        "Rappel du format : 1 phrase de synthèse, puis TOUJOURS 2 paragraphes "
        "de 3-4 phrases qui croisent vraiment les facteurs entre eux, puis "
        "3 à 4 puces — rien "
        "de redondant avec les chiffres déjà donnés ci-dessus, aucun "
        "remplissage. Ne donne jamais de conseil de pari, de cote, ni de "
        "garantie de résultat.",
    ]

    return "\n".join(lines)

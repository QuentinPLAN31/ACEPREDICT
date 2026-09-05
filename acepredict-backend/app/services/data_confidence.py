"""
Calcul du niveau de confiance (data_confidence) attribué à un joueur, cf.
models.DataConfidenceEnum et README "Synchronisation des données". Fonction
pure, réutilisée par :
  - scripts/sync_daily.py : recalculée pour tous les joueurs après chaque
    import Sackmann (le nombre de matchs connus change).
  - scripts/sync_hourly.py : calculée pour un joueur tout juste créé par
    auto-discovery (0 match connu, has_bio_data selon ce qui a été trouvé
    via la source secondaire).

Seuils volontairement simples et documentés plutôt qu'un score composite
opaque — honnêteté > fausse précision, comme le reste de ce backend :

  - insufficient : aucun match connu, aucune fiche bio trouvée — on ne sait
    rien de ce joueur au-delà de son nom. La prédiction reste calculable
    (Elo par défaut 1500) mais n'a AUCUNE valeur informative.
  - low : aucun match connu, mais une fiche bio existe (classement, pays,
    main... trouvés via une source secondaire lors de l'auto-discovery). Le
    joueur est identifié, mais l'Elo interne reste à sa valeur de départ
    1500 (aucun résultat historique) : toujours peu fiable.
  - medium : un historique de matchs existe mais reste réduit
    (< HIGH_MATCH_THRESHOLD) — l'Elo a bougé mais reste bruité par un petit
    échantillon.
  - high : historique substantiel (>= HIGH_MATCH_THRESHOLD matchs connus) —
    l'Elo est jugé suffisamment stabilisé pour être exploité normalement.
"""
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import DataConfidenceEnum

# Nombre de matchs à partir duquel l'Elo est jugé suffisamment stabilisé
# pour ne plus avertir l'utilisateur. Choix pragmatique (pas calibré
# statistiquement) : quelques dizaines de matchs suffisent en pratique pour
# qu'un rating Elo commence à refléter le niveau réel plutôt que le bruit
# des premiers résultats.
HIGH_MATCH_THRESHOLD = 15

# Libellés FR courts, réutilisés côté API (routers/players.py) et donc par
# le frontend, pour ne pas dupliquer ce texte à plusieurs endroits.
_LABELS = {
    DataConfidenceEnum.high: "Fiable",
    DataConfidenceEnum.medium: "Historique limité",
    DataConfidenceEnum.low: "Peu de données",
    DataConfidenceEnum.insufficient: "Données insuffisantes",
}
_DESCRIPTIONS = {
    DataConfidenceEnum.high: "Historique de matchs substantiel : la probabilité calculée est jugée fiable.",
    DataConfidenceEnum.medium: "Peu de matchs connus pour ce joueur : la probabilité peut être moins précise.",
    DataConfidenceEnum.low: "Aucun historique de matchs connu (joueur identifié via une source secondaire) : "
                             "la probabilité repose sur un Elo par défaut, à prendre avec prudence.",
    DataConfidenceEnum.insufficient: "Aucune donnée exploitable pour ce joueur au-delà de son nom : "
                                      "la probabilité affichée n'a qu'une valeur indicative très limitée.",
}


def compute_confidence(matches_played: int, has_bio_data: bool = False) -> DataConfidenceEnum:
    """
    matches_played : nombre de matchs historiques connus pour ce joueur
        (table Match — cf. Player.id en tant que player1_id/player2_id).
    has_bio_data : True si une fiche a été trouvée via une source secondaire
        lors de l'auto-discovery (cf. scripts/sync_hourly.py), même sans
        historique de matchs — ex: classement/pays connus via LiveTennisAPI.
    """
    if matches_played <= 0:
        return DataConfidenceEnum.low if has_bio_data else DataConfidenceEnum.insufficient
    if matches_played < HIGH_MATCH_THRESHOLD:
        return DataConfidenceEnum.medium
    return DataConfidenceEnum.high


def has_bio_signal(player) -> bool:
    """Heuristique : le joueur a au moins une donnée biographique connue
    (classement, pays, main, taille) au-delà de son simple nom -- utilisée
    pour distinguer "low" de "insufficient" quand aucun match n'est connu.
    Duck-typée (pas d'import de app.models ici) pour rester appelable aussi
    bien depuis scripts/sync_daily.py que scripts/sync_hourly.py."""
    return bool(
        getattr(player, "current_rank", None) is not None
        or getattr(player, "country", None)
        or getattr(player, "hand", None)
        or getattr(player, "height_cm", None)
    )


def label(confidence: DataConfidenceEnum) -> str:
    return _LABELS.get(confidence, str(confidence))


def description(confidence: DataConfidenceEnum) -> str:
    return _DESCRIPTIONS.get(confidence, "")


def recompute_all(db: Session) -> int:
    """Recalcule data_confidence pour TOUS les joueurs à partir du nombre de
    matchs connus en base (table Match) — appelé par scripts/sync_daily.py
    après chaque ingestion Sackmann. Recalcul complet plutôt qu'incrémental
    (plus simple, correct par construction, coût négligeable au volume de ce
    projet plutôt que de suivre "quels joueurs ont été touchés" ligne par
    ligne). Renvoie le nombre de joueurs dont le niveau a changé."""
    from app import models  # import tardif : évite tout risque de cycle avec app.models

    p1_counts = dict(
        db.query(models.Match.player1_id, func.count(models.Match.id))
        .group_by(models.Match.player1_id).all()
    )
    p2_counts = dict(
        db.query(models.Match.player2_id, func.count(models.Match.id))
        .group_by(models.Match.player2_id).all()
    )

    changed = 0
    for player in db.query(models.Player).all():
        matches_played = p1_counts.get(player.id, 0) + p2_counts.get(player.id, 0)
        new_confidence = compute_confidence(matches_played, has_bio_data=has_bio_signal(player))
        if player.data_confidence != new_confidence:
            player.data_confidence = new_confidence
            changed += 1
    db.commit()
    return changed

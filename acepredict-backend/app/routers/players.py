"""
Endpoints joueurs : classement (page "Classement" de l'app), recherche, détail,
et statistiques de performance (page "Profil joueur" du frontend).
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db

router = APIRouter(prefix="/players", tags=["players"])


@router.get("", response_model=list[schemas.PlayerOut])
def list_players(
    tour: Optional[str] = Query(None, description="atp | wta"),
    surface: Optional[str] = Query(None, description="hard | clay | grass — trie par elo de cette surface"),
    q: Optional[str] = Query(None, description="recherche par nom"),
    limit: int = 50,
    db: Session = Depends(get_db),
):
    query = db.query(models.Player)
    if tour:
        query = query.filter(models.Player.tour == tour)
    if q:
        query = query.filter(models.Player.name.ilike(f"%{q}%"))

    order_col = {
        "hard": models.Player.elo_hard,
        "clay": models.Player.elo_clay,
        "grass": models.Player.elo_grass,
    }.get(surface, models.Player.elo_overall)

    return query.order_by(order_col.desc()).limit(limit).all()


@router.get("/{player_id}", response_model=schemas.PlayerOut)
def get_player(player_id: str, db: Session = Depends(get_db)):
    player = db.query(models.Player).filter(models.Player.id == player_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Joueur introuvable")
    return player


@router.get("/{player_id}/stats")
def get_player_stats(player_id: str, limit_recent: int = 10, db: Session = Depends(get_db)):
    """
    Statistiques de performance dérivées de l'historique de matchs (table
    Match, import Sackmann) : bilan carrière, série en cours, dernière
    victoire/défaite, forme récente, titres, taux d'ace/double-fautes.

    A l'import (scripts/ingest_sackmann.py), player1_id est TOUJOURS le
    vainqueur du match et player2_id le perdant (pas d'assignation neutre) —
    donc winner_id reste la seule source fiable pour déterminer victoire/
    défaite ci-dessous, jamais player1_id/player2_id seuls. Les clés
    stats["w_ace"/"w_df"] appartiennent donc toujours au camp player1
    (= vainqueur de CE match), stats["l_ace"/"l_df"] au camp player2.

    Dégradation gracieuse : quand aucun match n'a de stats["w_ace"/...]
    renseigné (cas du petit jeu de données d'exemple), serve_stats est None
    plutôt qu'une fausse moyenne à 0 — le frontend masque alors ce bloc.
    """
    player = db.query(models.Player).filter(models.Player.id == player_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Joueur introuvable")

    matches = (
        db.query(models.Match)
        .filter(
            or_(models.Match.player1_id == player_id, models.Match.player2_id == player_id),
            models.Match.winner_id.isnot(None),
        )
        .order_by(models.Match.tourney_date.desc())
        .all()
    )

    opponent_ids = {(m.player2_id if m.player1_id == player_id else m.player1_id) for m in matches}
    competition_ids = {m.competition_id for m in matches if m.competition_id}
    opponents = (
        {p.id: p for p in db.query(models.Player).filter(models.Player.id.in_(opponent_ids)).all()}
        if opponent_ids else {}
    )
    competitions = (
        {c.id: c for c in db.query(models.Competition).filter(models.Competition.id.in_(competition_ids)).all()}
        if competition_ids else {}
    )

    def _summary(m: models.Match) -> dict:
        opponent_id = m.player2_id if m.player1_id == player_id else m.player1_id
        opponent = opponents.get(opponent_id)
        comp = competitions.get(m.competition_id) if m.competition_id else None
        return {
            "opponent_name": opponent.name if opponent else "Adversaire inconnu",
            "tournament": comp.name if comp else None,
            "round": m.round,
            "surface": m.surface.value if m.surface else None,
            "score": m.score,
            "date": m.tourney_date,
            "result": "W" if m.winner_id == player_id else "L",
        }

    wins = [m for m in matches if m.winner_id == player_id]
    losses_count = len(matches) - len(wins)

    # Série en cours : on part du match le plus récent et on compte tant que
    # le résultat (W ou L) reste identique.
    streak_type, streak_count = None, 0
    for m in matches:
        result = "W" if m.winner_id == player_id else "L"
        if streak_type is None:
            streak_type, streak_count = result, 1
        elif result == streak_type:
            streak_count += 1
        else:
            break

    last_win = next((_summary(m) for m in matches if m.winner_id == player_id), None)
    last_loss = next((_summary(m) for m in matches if m.winner_id != player_id), None)
    recent_form = [_summary(m) for m in matches[:limit_recent]]

    # Titres : victoires en finale ("F") — approximation raisonnable (une
    # finale gagnée = un titre) sans nécessiter de champ dédié en base.
    title_matches = [m for m in wins if (m.round or "").upper() == "F"]
    titles = sorted(
        (
            {
                "tournament": competitions[m.competition_id].name if m.competition_id in competitions else "Tournoi",
                "season": competitions[m.competition_id].season if m.competition_id in competitions else None,
                "date": m.tourney_date,
            }
            for m in title_matches
        ),
        key=lambda t: t["date"] or datetime.min,
        reverse=True,
    )

    ace_values: list[int] = []
    df_values: list[int] = []
    for m in matches:
        stats = m.stats or {}
        is_winner_side = m.winner_id == player_id
        ace_raw = stats.get("w_ace") if is_winner_side else stats.get("l_ace")
        df_raw = stats.get("w_df") if is_winner_side else stats.get("l_df")
        for raw, bucket in ((ace_raw, ace_values), (df_raw, df_values)):
            try:
                if raw not in (None, ""):
                    bucket.append(int(raw))
            except (TypeError, ValueError):
                pass

    serve_stats = None
    if ace_values:
        serve_stats = {
            "avg_aces_per_match": round(sum(ace_values) / len(ace_values), 1),
            "avg_double_faults_per_match": round(sum(df_values) / len(df_values), 1) if df_values else None,
            "matches_with_data": len(ace_values),
        }

    return {
        "matches_played": len(matches),
        "wins": len(wins),
        "losses": losses_count,
        "win_rate": round(len(wins) / len(matches), 4) if matches else None,
        "current_streak": {"type": streak_type, "count": streak_count} if streak_type else None,
        "titles_count": len(title_matches),
        "titles": titles[:10],
        "last_win": last_win,
        "last_loss": last_loss,
        "recent_form": recent_form,
        "serve_stats": serve_stats,
    }

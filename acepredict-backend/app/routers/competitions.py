"""
Endpoints compétitions : liste (page "Compétitions"), détail avec tabs
Classement / Matchs / Joueurs / Nations (page comp-detail du frontend).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db

router = APIRouter(prefix="/competitions", tags=["competitions"])


@router.get("", response_model=list[schemas.CompetitionOut])
def list_competitions(db: Session = Depends(get_db)):
    return db.query(models.Competition).all()


@router.get("/{competition_id}", response_model=schemas.CompetitionOut)
def get_competition(competition_id: str, db: Session = Depends(get_db)):
    comp = db.query(models.Competition).filter(models.Competition.id == competition_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Compétition introuvable")
    return comp


@router.get("/{competition_id}/matches")
def get_competition_matches(competition_id: str, db: Session = Depends(get_db)):
    """Alimente les onglets 'Matchs', 'Tableau du tournoi', 'Joueurs' et
    'Nations' de la page de détail compétition -- tous dérivés côté frontend
    de cette même liste de matchs réellement joués (table Match, importée
    depuis les CSV Sackmann par scripts/sync_daily.py). Noms et pays des
    joueurs dénormalisés ici (même logique que routers/matches.py et
    routers/analyses.py) pour éviter un aller-retour par joueur côté
    frontend."""
    matches = (
        db.query(models.Match)
        .filter(models.Match.competition_id == competition_id)
        .order_by(models.Match.tourney_date.desc())
        .all()
    )
    if not matches:
        return []

    player_ids = {m.player1_id for m in matches} | {m.player2_id for m in matches}
    players = {p.id: p for p in db.query(models.Player).filter(models.Player.id.in_(player_ids)).all()}

    return [
        {
            "id": m.id,
            "round": m.round,
            "player1_id": m.player1_id,
            "player1_name": players[m.player1_id].name if m.player1_id in players else "?",
            "player1_country": players[m.player1_id].country if m.player1_id in players else None,
            "player2_id": m.player2_id,
            "player2_name": players[m.player2_id].name if m.player2_id in players else "?",
            "player2_country": players[m.player2_id].country if m.player2_id in players else None,
            "winner_id": m.winner_id,
            "score": m.score,
            "date": m.tourney_date,
        }
        for m in matches
    ]


@router.get("/{competition_id}/ranking")
def get_competition_ranking(competition_id: str, tour: str = "atp", db: Session = Depends(get_db)):
    """Alimente le sous-onglet 'Classement ATP' — classement Elo trié."""
    players = (
        db.query(models.Player)
        .filter(models.Player.tour == tour)
        .order_by(models.Player.elo_overall.desc())
        .limit(32)
        .all()
    )
    return [schemas.PlayerOut.model_validate(p) for p in players]

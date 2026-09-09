"""
Endpoints compétitions : liste (page "Compétitions"), détail avec tabs
Classement / Matchs / Joueurs / Nations (page comp-detail du frontend).
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app import models, schemas
from app.database import get_db

router = APIRouter(prefix="/competitions", tags=["competitions"])


@router.get("", response_model=list[schemas.CompetitionOut])
def list_competitions(include_past: bool = False, db: Session = Depends(get_db)):
    """Par défaut, ne montre que les compétitions de l'année en cours (season
    == année courante) ou sans saison connue -- les éditions passées d'années
    antérieures (import historique Sackmann, cf. scripts/ingest_sackmann.py)
    sont masquées pour ne pas polluer la page avec des tournois déjà clos
    depuis longtemps. include_past=true les réaffiche toutes (ex : usage
    interne/debug)."""
    query = db.query(models.Competition)
    if not include_past:
        current_year = datetime.utcnow().year
        query = query.filter(
            (models.Competition.season == None) | (models.Competition.season >= current_year)  # noqa: E711
        )
    return query.all()


@router.get("/{competition_id}", response_model=schemas.CompetitionOut)
def get_competition(competition_id: str, db: Session = Depends(get_db)):
    comp = db.query(models.Competition).filter(models.Competition.id == competition_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Compétition introuvable")
    return comp


@router.get("/{competition_id}/matches")
def get_competition_matches(competition_id: str, db: Session = Depends(get_db)):
    """Alimente les onglets 'Matchs', 'Tableau du tournoi', 'Joueurs' et
    'Nations' de la page de détail compétition -- combine deux sources :
    1) les matchs réellement joués (table Match, import historique
       Sackmann par scripts/sync_daily.py) ;
    2) les matchs à venir / en cours (table Fixture, synchronisée
       HORAIREMENT par scripts/sync_hourly.py -- cf. routers/matches.py),
       rattachés à cette compétition par correspondance de nom de tournoi
       (Fixture n'a pas de FK vers Competition, seulement un nom de
       tournoi libre côté source externe). Sans ce rapprochement, un
       tournoi en cours / à venir (donc sans encore aucune ligne Match)
       apparaissait vide sur cette page alors que ses matchs étaient déjà
       visibles ailleurs (calendrier 'Matchs à venir'). Noms et pays des
       joueurs dénormalisés ici (même logique que routers/matches.py et
       routers/analyses.py) pour éviter un aller-retour par joueur côté
       frontend."""
    comp = db.query(models.Competition).filter(models.Competition.id == competition_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Compétition introuvable")

    matches = (
        db.query(models.Match)
        .filter(models.Match.competition_id == competition_id)
        .order_by(models.Match.tourney_date.desc())
        .all()
    )

    player_ids = {m.player1_id for m in matches} | {m.player2_id for m in matches}
    players = {p.id: p for p in db.query(models.Player).filter(models.Player.id.in_(player_ids)).all()}

    results = [
        {
            "id": m.id,
            "round": m.round,
            "player1_id": m.player1_id,
            "player1_name": players[m.player1_id].name if m.player1_id in players else "?",
            "player1_country": players[m.player1_id].country if m.player1_id in players else None,
            "player1_ranking": players[m.player1_id].current_rank if m.player1_id in players else None,
            "player2_id": m.player2_id,
            "player2_name": players[m.player2_id].name if m.player2_id in players else "?",
            "player2_country": players[m.player2_id].country if m.player2_id in players else None,
            "player2_ranking": players[m.player2_id].current_rank if m.player2_id in players else None,
            "winner_id": m.winner_id,
            "score": m.score,
            "date": m.tourney_date,
        }
        for m in matches
    ]

    # Rapprochement par nom (insensible à la casse, sous-chaîne dans les
    # deux sens pour absorber les variantes -- ex. "US Open" / "US Open
    # (New York)"). Filtré par tour quand connu pour éviter tout mélange
    # ATP/WTA sur un nom de tournoi partagé.
    comp_name = (comp.name or "").strip().lower()
    if comp_name:
        fixtures_q = db.query(models.Fixture).options(
            joinedload(models.Fixture.player1), joinedload(models.Fixture.player2)
        )
        if comp.tour:
            fixtures_q = fixtures_q.filter(models.Fixture.tour == comp.tour)
        fixtures = fixtures_q.order_by(models.Fixture.scheduled_time.asc()).all()

        for f in fixtures:
            fname = (f.tournament_name or "").strip().lower()
            if not fname:
                continue
            if comp_name not in fname and fname not in comp_name:
                continue
            p1, p2 = f.player1, f.player2
            results.append({
                "id": f.id,
                "round": f.round,
                "player1_id": p1.id if p1 else None,
                "player1_name": p1.name if p1 else (f.player1_name_raw or "?"),
                "player1_country": p1.country if p1 else None,
                "player1_ranking": p1.current_rank if p1 else None,
                "player2_id": p2.id if p2 else None,
                "player2_name": p2.name if p2 else (f.player2_name_raw or "?"),
                "player2_country": p2.country if p2 else None,
                "player2_ranking": p2.current_rank if p2 else None,
                "winner_id": None,
                "score": None,
                "date": f.scheduled_time,
            })

    return results


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

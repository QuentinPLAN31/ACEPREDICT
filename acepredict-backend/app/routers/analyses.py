"""
Endpoint de prédiction — c'est le bouton "Passer Premium" / onglet "Analyse"
du frontend : consomme un crédit de quota, calcule la prédiction Elo,
persiste l'Analysis pour l'historique utilisateur.

Cf. README "Synchronisation des données" : ce routeur ne fait plus AUCUN
appel réseau externe. Météo et cotes de marché ne sont plus récupérées ici
en direct (comme avant ce refactor) mais LUES sur la ligne Fixture
correspondante — déjà dénormalisées en base par le job horaire
(scripts/sync_hourly.py). Sans Fixture correspondante (ex : analyse "libre"
entre deux joueurs sans match programmé connu), l'analyse tourne quand même,
juste sans ces deux enrichissements — jamais bloquant.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.deps import require_quota, get_current_user
from app.services import data_confidence
from app.services.prediction import build_prediction

router = APIRouter(prefix="/analyses", tags=["analyses"])


def _find_matching_fixture(
    db: Session, player1_id: str, player2_id: str, tournament_name: Optional[str] = None,
) -> Optional[models.Fixture]:
    """Cherche la Fixture (synchronisée par scripts/sync_hourly.py) qui
    correspond à ces deux joueurs, peu importe l'ordre dans lequel ils sont
    stockés sur la ligne. S'il y en a plusieurs (rare — même paire sur deux
    tournois différents), on privilégie celle dont le nom de tournoi
    correspond à celui transmis par l'utilisateur, sinon la plus proche dans
    le temps."""
    fixtures = (
        db.query(models.Fixture)
        .filter(
            or_(
                and_(models.Fixture.player1_id == player1_id, models.Fixture.player2_id == player2_id),
                and_(models.Fixture.player1_id == player2_id, models.Fixture.player2_id == player1_id),
            )
        )
        .order_by(models.Fixture.scheduled_time.asc())
        .all()
    )
    if not fixtures:
        return None
    if tournament_name:
        needle = tournament_name.strip().lower()
        for f in fixtures:
            if f.tournament_name and f.tournament_name.strip().lower() == needle:
                return f
    return fixtures[0]


def _weather_from_fixture(fixture: Optional[models.Fixture]) -> Optional[dict]:
    """Reconstruit le dict {indoor, temp_c, wind_kmh, humidity_pct,
    description} attendu par prediction.py à partir des champs dénormalisés
    sur la Fixture (jamais d'appel météo ici). weather_synced_at à None veut
    dire "jamais vérifié" (pas de ville connue, match pas encore synchronisé) —
    distinct de "vérifié, rien trouvé" (cf. models.Fixture)."""
    if not fixture:
        return None
    if fixture.indoor:
        return {"indoor": True}
    if fixture.weather_synced_at is None:
        return None
    return {
        "indoor": False,
        "temp_c": fixture.weather_temp_c,
        "wind_kmh": fixture.weather_wind_kmh,
        "humidity_pct": fixture.weather_humidity_pct,
        "description": fixture.weather_description,
    }


def _market_from_fixture(fixture: Optional[models.Fixture], player1_id: str) -> Optional[dict]:
    """Reconstruit le dict {player1_prob, player2_prob, question} attendu
    par prediction.py, dans le référentiel (player1, player2) DE CETTE
    ANALYSE — qui peut être l'inverse de l'ordre stocké sur la Fixture (les
    deux joueurs d'un même match peuvent être passés dans n'importe quel
    ordre par le frontend). Jamais d'appel marché ici."""
    if not fixture or fixture.market_synced_at is None:
        return None
    p1_prob, p2_prob = fixture.market_player1_prob, fixture.market_player2_prob
    if p1_prob is None or p2_prob is None:
        return None
    if str(fixture.player1_id) == str(player1_id):
        return {"player1_prob": p1_prob, "player2_prob": p2_prob, "question": fixture.market_question}
    return {"player1_prob": p2_prob, "player2_prob": p1_prob, "question": fixture.market_question}


@router.post("", response_model=schemas.AnalysisOut)
def create_analysis(
    payload: schemas.AnalysisRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_quota),
):
    p1 = db.query(models.Player).filter(models.Player.id == payload.player1_id).first()
    p2 = db.query(models.Player).filter(models.Player.id == payload.player2_id).first()
    if not p1 or not p2:
        raise HTTPException(status_code=404, detail="Un des deux joueurs est introuvable")

    fixture = _find_matching_fixture(db, p1.id, p2.id, payload.tournament_name)

    result = build_prediction(
        db, p1, p2,
        surface=payload.surface,
        match_city=payload.match_city,
        match_date=payload.match_date,
        tournament_name=payload.tournament_name,
        weather=_weather_from_fixture(fixture),
        market=_market_from_fixture(fixture, p1.id),
    )

    analysis = models.Analysis(
        user_id=current_user.id,
        player1_id=p1.id,
        player2_id=p2.id,
        competition_id=payload.competition_id,
        surface=payload.surface,
        predicted_winner_id=result["predicted_winner_id"],
        win_probability=result["win_probability"],
        model_version=result["model_version"],
        detail=result["detail"],
    )
    db.add(analysis)

    # Décrément du quota (point 4 : gating par plan)
    current_user.quota.analyses_used += 1

    db.commit()
    db.refresh(analysis)

    # data_confidence n'est pas persisté sur Analysis : il est recalculé en
    # continu par les jobs de sync (cf. services/data_confidence.py) et lu
    # en direct sur les fiches joueurs, pour toujours refléter le niveau de
    # fiabilité ACTUEL, pas celui au moment de cette analyse.
    return {
        "id": analysis.id,
        "player1_id": analysis.player1_id,
        "player2_id": analysis.player2_id,
        "predicted_winner_id": analysis.predicted_winner_id,
        "win_probability": analysis.win_probability,
        "model_version": analysis.model_version,
        "detail": analysis.detail,
        "created_at": analysis.created_at,
        "player1_data_confidence": data_confidence.label(p1.data_confidence),
        "player2_data_confidence": data_confidence.label(p2.data_confidence),
    }


@router.get("/history", response_model=list[schemas.AnalysisHistoryOut])
def analysis_history(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # Historique = page "Historique" du frontend. Pas de gating quota pour la lecture.
    # Enrichi avec les noms de joueurs pour que le frontend n'ait pas besoin
    # d'un aller-retour supplémentaire vers /players pour chaque ligne.
    rows = (
        db.query(models.Analysis)
        .filter(models.Analysis.user_id == current_user.id)
        .order_by(models.Analysis.created_at.desc())
        .all()
    )
    if not rows:
        return []

    player_ids = {a.player1_id for a in rows} | {a.player2_id for a in rows} | {a.predicted_winner_id for a in rows}
    players = db.query(models.Player).filter(models.Player.id.in_(player_ids)).all()
    names = {p.id: p.name for p in players}
    confidences = {p.id: data_confidence.label(p.data_confidence) for p in players}

    return [
        schemas.AnalysisHistoryOut(
            id=a.id,
            player1_id=a.player1_id,
            player1_name=names.get(a.player1_id, "?"),
            player2_id=a.player2_id,
            player2_name=names.get(a.player2_id, "?"),
            predicted_winner_id=a.predicted_winner_id,
            predicted_winner_name=names.get(a.predicted_winner_id, "?"),
            win_probability=a.win_probability,
            model_version=a.model_version,
            detail=a.detail,
            created_at=a.created_at,
            player1_data_confidence=confidences.get(a.player1_id),
            player2_data_confidence=confidences.get(a.player2_id),
        )
        for a in rows
    ]

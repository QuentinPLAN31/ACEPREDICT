"""
Calendrier de matchs à venir — sert exclusivement la base locale (table
Fixture), synchronisée HORAIREMENT par scripts/sync_hourly.py (cf. README
"Synchronisation des données"). Plus AUCUN appel direct à une API externe
depuis une requête utilisateur ici : la fraîcheur des données dépend du
dernier passage du job horaire (au pire ~1h), jamais d'un appel réseau au
moment où quelqu'un ouvre la page.

Public comme /players (pas de gating quota — ce n'est pas une analyse).

Le calendrier remonte tous les niveaux de circuit vus par LiveTennisAPI
(ATP/WTA jusqu'à Challenger/ITF). Avant ce refactor, un match entre deux
joueurs de tournois mineurs (hors de notre base) était marqué "non
analysable" pour griser le bouton côté frontend. Ce n'est plus vrai depuis
l'auto-discovery du job horaire (cf. scripts/sync_hourly.py) : les deux
joueurs d'une Fixture sont TOUJOURS déjà en base (créés à la volée sinon),
donc toujours analysables au sens strict. Ce qui varie désormais, c'est la
FIABILITÉ de la prédiction obtenue : `player{1,2}_data_confidence` porte
cette information pour que le frontend avertisse plutôt que de bloquer
(cf. services/data_confidence.py, et la consigne d'origine : "adapter
l'affichage de la prédiction en conséquence plutôt que de bloquer
l'analyse").
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app import models, schemas
from app.database import get_db
from app.services import data_confidence

router = APIRouter(prefix="/matches", tags=["matches"])


def _annotate_analyzable(db: Session, matches: list[dict]) -> list[dict]:
    """Ajoute `analyzable` à chaque ligne : True si les deux noms de joueurs
    correspondent (insensible à la casse) à un Player existant en base.
    Conservé pour compatibilité frontend — depuis que ce routeur ne lit que
    la table Fixture (cf. en-tête du fichier), ses deux joueurs y sont
    toujours déjà résolus, donc ce champ vaut désormais True en pratique ;
    l'information utile ("peu fiable" vs "pas analysable") est portée par
    player{1,2}_data_confidence. Une seule requête groupée, quelle que soit
    la taille de la liste."""
    names = set()
    for m in matches:
        if m.get("player1_name"):
            names.add(m["player1_name"].strip().lower())
        if m.get("player2_name"):
            names.add(m["player2_name"].strip().lower())
    known = set()
    if names:
        rows = db.query(models.Player.name).filter(func.lower(models.Player.name).in_(names)).all()
        known = {(r[0] or "").strip().lower() for r in rows}

    annotated = []
    for m in matches:
        n1 = (m.get("player1_name") or "").strip().lower()
        n2 = (m.get("player2_name") or "").strip().lower()
        annotated.append({**m, "analyzable": bool(n1 and n2 and n1 in known and n2 in known)})
    return annotated


@router.get("/upcoming", response_model=list[schemas.UpcomingMatchOut])
def upcoming_matches(
    player1_id: str,
    player2_id: str,
    db: Session = Depends(get_db),
):
    p1 = db.query(models.Player).filter(models.Player.id == player1_id).first()
    p2 = db.query(models.Player).filter(models.Player.id == player2_id).first()
    if not p1 or not p2:
        raise HTTPException(status_code=404, detail="Un des deux joueurs est introuvable")

    fixtures = (
        db.query(models.Fixture)
        .filter(
            or_(
                (models.Fixture.player1_id == p1.id) & (models.Fixture.player2_id == p2.id),
                (models.Fixture.player1_id == p2.id) & (models.Fixture.player2_id == p1.id),
            )
        )
        .order_by(models.Fixture.scheduled_time.asc())
        .all()
    )

    return [
        {
            "scheduled_time": f.scheduled_time,
            "tournament": f.tournament_name,
            "surface": f.surface.value if f.surface else None,
            "indoor": f.indoor,
            "round": f.round,
            "city": f.city,
        }
        for f in fixtures
    ]


@router.get("/upcoming-list", response_model=list[schemas.UpcomingMatchListItem])
def upcoming_matches_list(
    tour: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    limit = max(1, min(limit, 200))

    query = db.query(models.Fixture).options(
        joinedload(models.Fixture.player1), joinedload(models.Fixture.player2)
    )
    if tour:
        query = query.filter(models.Fixture.tour == tour.strip().lower())
    fixtures = query.order_by(models.Fixture.scheduled_time.asc()).limit(limit).all()

    matches = []
    for f in fixtures:
        p1, p2 = f.player1, f.player2
        matches.append({
            "scheduled_time": f.scheduled_time,
            "tournament": f.tournament_name,
            "tournament_id": f.tournament_id_external,
            "tour": f.tour.value if f.tour else None,
            "surface": f.surface.value if f.surface else None,
            "indoor": f.indoor,
            "round": f.round,
            "player1_id": str(p1.id) if p1 else None,
            "player1_name": p1.name if p1 else f.player1_name_raw,
            "player1_country": p1.country if p1 else None,
            "player1_ranking": p1.current_rank if p1 else None,
            "player1_data_confidence": data_confidence.label(p1.data_confidence) if p1 else None,
            "player2_id": str(p2.id) if p2 else None,
            "player2_name": p2.name if p2 else f.player2_name_raw,
            "player2_country": p2.country if p2 else None,
            "player2_ranking": p2.current_rank if p2 else None,
            "player2_data_confidence": data_confidence.label(p2.data_confidence) if p2 else None,
        })

    return _annotate_analyzable(db, matches)

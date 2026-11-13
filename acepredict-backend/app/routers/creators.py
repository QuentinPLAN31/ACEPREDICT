"""
Programme créateurs (cf. services/creator_service.py).

Public :
  POST /creators/click            {"code": "nom"} -- compteur de clics du lien
  GET  /creators/stats/{slug}?k=  -- stats du créateur (page /createur)
Admin (en-tête X-Admin-Token = ADMIN_TOKEN) :
  POST /creators/admin            créer un créateur -> lien + lien de stats
  GET  /creators/admin/summary?month=YYYY-MM   récap de tous les créateurs
  POST /creators/admin/{slug}/paid?month=YYYY-MM   marquer le mois versé
"""
import secrets
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.database import get_db
from app.services import creator_service as cs

router = APIRouter(prefix="/creators", tags=["creators"])


def _month(month: Optional[str]) -> str:
    if not month:
        return datetime.utcnow().strftime("%Y-%m")
    try:
        datetime.strptime(month, "%Y-%m")
    except ValueError:
        raise HTTPException(status_code=400, detail="month attendu au format YYYY-MM")
    return month


def require_admin(x_admin_token: str = Header(default="")):
    if not settings.admin_token:
        raise HTTPException(status_code=503, detail="ADMIN_TOKEN non configuré")
    if not secrets.compare_digest(x_admin_token, settings.admin_token):
        raise HTTPException(status_code=401, detail="Jeton admin invalide")


class ClickIn(BaseModel):
    code: str


@router.post("/click")
def click(payload: ClickIn, db: Session = Depends(get_db)):
    creator = cs.get_active_creator(db, payload.code)
    if creator:
        creator.clicks = (creator.clicks or 0) + 1
        db.commit()
    return {"ok": bool(creator)}


@router.get("/stats/{slug}")
def creator_stats(slug: str, k: str = "", month: Optional[str] = None, db: Session = Depends(get_db)):
    creator = cs.get_active_creator(db, slug)
    if not creator or not k or not secrets.compare_digest(k, creator.dashboard_key):
        raise HTTPException(status_code=404, detail="Créateur introuvable")
    return {
        **cs.creator_month(db, creator, _month(month)),
        "link": f"{settings.frontend_base_url}/?via={creator.slug}",
        "grid_eur": {p: c / 100 for p, c in cs.COMMISSION_CENTS.items()},
    }


class CreatorIn(BaseModel):
    slug: str
    name: str
    contact: Optional[str] = None


@router.post("/admin", dependencies=[Depends(require_admin)])
def create_creator(payload: CreatorIn, db: Session = Depends(get_db)):
    slug = cs.normalize_slug(payload.slug)
    if not slug:
        raise HTTPException(status_code=400, detail="slug : 2-40 caractères a-z, 0-9, - ou _")
    if db.query(models.Creator).filter(models.Creator.slug == slug).first():
        raise HTTPException(status_code=409, detail="Ce slug existe déjà")
    creator = models.Creator(slug=slug, name=payload.name, contact=payload.contact,
                             dashboard_key=cs.new_dashboard_key())
    db.add(creator)
    db.commit()
    base = settings.frontend_base_url
    return {
        "slug": slug,
        "link": f"{base}/?via={slug}",
        "dashboard": f"{base}/createur?c={slug}&k={creator.dashboard_key}",
    }


@router.get("/admin/summary", dependencies=[Depends(require_admin)])
def summary(month: Optional[str] = None, db: Session = Depends(get_db)):
    m = _month(month)
    creators = db.query(models.Creator).order_by(models.Creator.created_at).all()
    rows = [cs.creator_month(db, c, m) for c in creators]
    return {
        "month": m,
        "creators": rows,
        "total_eur": round(sum(r["total_eur"] for r in rows), 2),
        "payable_eur": round(sum(r["payable_eur"] for r in rows), 2),
    }


@router.post("/admin/{slug}/paid", dependencies=[Depends(require_admin)])
def mark_paid(slug: str, month: Optional[str] = None, db: Session = Depends(get_db)):
    creator = db.query(models.Creator).filter(models.Creator.slug == cs.normalize_slug(slug)).first()
    if not creator:
        raise HTTPException(status_code=404, detail="Créateur introuvable")
    n = cs.mark_month_paid(db, creator, _month(month))
    db.commit()
    return {"marked_paid": n}

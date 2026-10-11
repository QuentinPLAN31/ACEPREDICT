"""
Pages SEO publiques (HTML rendu côté serveur). Servies sous /seo/... par le
backend ; Vercel les expose sous /fr/pronostic/<slug>, /fr/pronostics,
/fr/bilan, /fr/tournoi/<slug>, /sitemap.xml (cf. vercel.json).
"""
from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.database import get_db
from app.services import seo_extra, seo_pages, seo_render

router = APIRouter(prefix="/seo", tags=["seo"], include_in_schema=False)

CACHE = {"Cache-Control": "public, s-maxage=300, stale-while-revalidate=3600"}


def _not_found() -> HTMLResponse:
    return HTMLResponse(seo_render.not_found_page(), status_code=404,
                        headers={"X-Robots-Tag": "noindex"})


@router.get("/fr/pronostic/{slug}")
def match_page(slug: str, db: Session = Depends(get_db)):
    pg = db.query(models.MatchPage).filter(models.MatchPage.slug == slug).first()
    if not pg:
        return _not_found()
    return HTMLResponse(seo_pages.render_page(db, pg), headers=CACHE)


@router.get("/fr/pronostics")
def hub(db: Session = Depends(get_db)):
    return HTMLResponse(seo_pages.render_hub(db), headers=CACHE)


@router.get("/fr/bilan")
def bilan(db: Session = Depends(get_db)):
    return HTMLResponse(seo_pages.render_bilan(db), headers=CACHE)


@router.get("/fr/tournoi/{slug}")
def tournoi(slug: str, db: Session = Depends(get_db)):
    html_ = seo_pages.render_tournoi(db, slug)
    if html_ is None:
        return _not_found()
    return HTMLResponse(html_, headers=CACHE)


@router.get("/fr/tournois")
def tournois(db: Session = Depends(get_db)):
    return HTMLResponse(seo_extra.render_tournois(db), headers=CACHE)


@router.get("/fr/joueurs")
def joueurs(db: Session = Depends(get_db)):
    return HTMLResponse(seo_extra.render_joueurs(db), headers=CACHE)


@router.get("/fr/joueur/{slug}")
def joueur(slug: str, db: Session = Depends(get_db)):
    html_ = seo_extra.render_player(db, slug)
    return HTMLResponse(html_, headers=CACHE) if html_ else _not_found()


@router.get("/fr/pronostics/{when}")
def jour(when: str, db: Session = Depends(get_db)):
    html_ = seo_extra.render_day(db, when)
    return HTMLResponse(html_, headers={"Cache-Control": "public, s-maxage=120, stale-while-revalidate=600"}) if html_ else _not_found()


@router.get("/sitemap.xml")
def sitemap(db: Session = Depends(get_db)):
    return Response(seo_pages.render_sitemap(db), media_type="application/xml", headers=CACHE)


@router.get("/indexnow-key.txt")
def indexnow_key():
    if not settings.indexnow_key:
        return PlainTextResponse("", status_code=404)
    return PlainTextResponse(settings.indexnow_key)

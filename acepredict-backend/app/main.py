"""
Point d'entrée FastAPI — AcePredict backend.
Lancer en dev : uvicorn app.main:app --reload
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import auth, players, competitions, analyses, users, billing, matches, referrals

app = FastAPI(
    title="AcePredict API",
    description="Backend de prédiction tennis (Elo par surface) pour l'app AcePredict.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(players.router)
app.include_router(competitions.router)
app.include_router(analyses.router)
app.include_router(users.router)
app.include_router(billing.router)
app.include_router(matches.router)
app.include_router(referrals.router)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok", "env": settings.env}

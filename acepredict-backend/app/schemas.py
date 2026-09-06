"""
Schémas Pydantic (validation entrée/sortie API).
"""
from datetime import datetime
from typing import Optional, Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


# ---- auth ----

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: Optional[str] = None
    ref_code: Optional[str] = None  # code de parrainage de l'inviteur, si venu par un lien ?ref=


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: str
    email: EmailStr
    full_name: Optional[str] = None
    plan: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8)


class MessageOut(BaseModel):
    message: str


# ---- players / competitions ----

class PlayerOut(BaseModel):
    id: str
    name: str
    country: Optional[str] = None
    tour: str
    elo_overall: float
    elo_hard: float
    elo_clay: float
    elo_grass: float
    hand: Optional[str] = None  # R / L
    current_rank: Optional[int] = None
    # Note de style de jeu rédigée à la main (cf. scripts/seed_playing_styles.py) --
    # None si ce joueur n'est pas encore couvert (rang trop bas / trop récent),
    # jamais de contenu généré à la volée pour combler.
    playing_style: Optional[str] = None
    # "haute" ou "faible" (cf. models.py::Player.playing_style_confidence) --
    # le frontend affiche un avertissement quand faible.
    playing_style_confidence: Optional[str] = None
    # Libellé FR (cf. services/data_confidence.py::label) -- converti depuis
    # Player.data_confidence par le validator ci-dessous, pour que le
    # frontend affiche directement le même texte partout (recherche,
    # profil, résultat d'analyse) sans dupliquer la table de libellés.
    data_confidence: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("data_confidence", mode="before")
    @classmethod
    def _confidence_to_label(cls, v):
        if v is None:
            return None
        from app.services.data_confidence import label
        return label(v)


class CompetitionOut(BaseModel):
    id: str
    name: str
    category: str
    tour: str
    location: Optional[str] = None
    surface: Optional[str] = None
    season: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


# ---- analyses / predictions ----

class AnalysisRequest(BaseModel):
    player1_id: str
    player2_id: str
    competition_id: Optional[str] = None
    surface: Optional[str] = None  # hard | clay | grass | carpet
    match_city: Optional[str] = None  # ville où se joue le match (pour la météo, optionnel)
    match_date: Optional[datetime] = None  # date/heure du match (pour la météo, optionnel)
    # Nom du tournoi tel que renvoyé par le calendrier live (services/livetennis_client.py),
    # ex: "US Open", "Indian Wells" — sert à déduire le format (Bo3/Bo5) et le
    # niveau du tournoi (Grand Chelem/Masters/Tour), cf. services/prediction.py.
    # Optionnel : sans ce champ, cet ajustement est simplement ignoré.
    tournament_name: Optional[str] = None


class AnalysisOut(BaseModel):
    model_config = ConfigDict(protected_namespaces=(), from_attributes=True)

    id: str
    player1_id: str
    player2_id: str
    predicted_winner_id: str
    win_probability: float
    model_version: str
    detail: Optional[dict[str, Any]] = None
    created_at: datetime
    # Libellé FR (cf. services/data_confidence.py::label), calculé au moment
    # de l'analyse à partir de Player.data_confidence -- permet au frontend
    # d'afficher un avertissement de fiabilité à côté du résultat plutôt que
    # de bloquer l'analyse (cf. README "Synchronisation des données").
    player1_data_confidence: Optional[str] = None
    player2_data_confidence: Optional[str] = None


class AnalysisHistoryOut(BaseModel):
    """Comme AnalysisOut, mais enrichi des noms de joueurs (évite un aller-retour
    supplémentaire du frontend vers /players pour afficher l'historique)."""
    model_config = ConfigDict(protected_namespaces=())

    id: str
    player1_id: str
    player1_name: str
    player2_id: str
    player2_name: str
    predicted_winner_id: str
    predicted_winner_name: str
    win_probability: float
    model_version: str
    detail: Optional[dict[str, Any]] = None
    created_at: datetime
    player1_data_confidence: Optional[str] = None
    player2_data_confidence: Optional[str] = None


# ---- calendrier live (prochains matchs proposés à l'utilisateur) ----

class UpcomingMatchOut(BaseModel):
    scheduled_time: Optional[datetime] = None
    tournament: Optional[str] = None
    surface: Optional[str] = None
    indoor: Optional[bool] = None
    round: Optional[str] = None
    city: Optional[str] = None


class UpcomingMatchListItem(BaseModel):
    """Ligne de la page "Matchs à venir" — liste large (tous joueurs), pas
    seulement les deux joueurs d'une analyse en cours (cf. UpcomingMatchOut)."""
    scheduled_time: Optional[datetime] = None
    tournament: Optional[str] = None
    tournament_id: Optional[str] = None
    tour: Optional[str] = None
    surface: Optional[str] = None
    indoor: Optional[bool] = None
    round: Optional[str] = None
    player1_id: Optional[str] = None
    player1_name: Optional[str] = None
    player1_country: Optional[str] = None
    player1_ranking: Optional[int] = None
    # Libellé FR (cf. services/data_confidence.py::label) — "Fiable", "Peu de
    # données", "Données insuffisantes"... Permet au frontend d'afficher un
    # avertissement à côté de la prédiction plutôt que de bloquer l'analyse
    # (cf. README "Synchronisation des données").
    player1_data_confidence: Optional[str] = None
    player2_id: Optional[str] = None
    player2_name: Optional[str] = None
    player2_country: Optional[str] = None
    player2_ranking: Optional[int] = None
    player2_data_confidence: Optional[str] = None
    # Depuis que ce calendrier est servi par la table Fixture (auto-discovery
    # au moment du sync horaire, cf. scripts/sync_hourly.py), les deux joueurs
    # d'une fixture sont TOUJOURS déjà en base (créés à la volée s'ils
    # étaient inconnus) : ce champ reste à True en pratique. Conservé pour ne
    # pas casser un frontend qui le lirait encore — remplacé par les champs
    # data_confidence ci-dessus, qui portent l'information utile désormais
    # ("analysable mais peu fiable" plutôt que "pas analysable").
    analyzable: Optional[bool] = None


# ---- billing ----

class CheckoutSessionRequest(BaseModel):
    plan: str  # starter | pro | lifetime


class CheckoutSessionOut(BaseModel):
    checkout_url: str

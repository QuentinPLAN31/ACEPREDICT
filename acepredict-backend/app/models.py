"""
Schéma relationnel (SQLAlchemy ORM).
Voir ARCHITECTURE.md section 3 pour le détail des choix de modélisation.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, ForeignKey,
    Text, Enum, UniqueConstraint, Index, JSON
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.database import Base

# UUID stocké comme chaîne (portable Postgres/SQLite — utile pour les tests
# sans dépendre d'un serveur Postgres). En prod Postgres, c'est une colonne
# texte de 36 caractères, indexable comme une UUID classique.
UUIDType = String(36)

# JSON générique, avec le type binaire JSONB natif quand le dialecte est
# Postgres (indexable/performant), et un JSON standard ailleurs (ex: SQLite
# pour les tests).
JSONType = JSON().with_variant(JSONB, "postgresql")


def gen_uuid():
    return str(uuid.uuid4())


class PlanEnum(str, enum.Enum):
    free = "free"
    starter = "starter"
    pro = "pro"
    lifetime = "lifetime"


class SurfaceEnum(str, enum.Enum):
    hard = "hard"
    clay = "clay"
    grass = "grass"
    carpet = "carpet"


class TourEnum(str, enum.Enum):
    atp = "atp"
    wta = "wta"


class DataConfidenceEnum(str, enum.Enum):
    """Fiabilité des données disponibles pour un joueur, cf. services/
    data_confidence.py — affichée sur le frontend pour adapter la
    présentation d'une prédiction (avertissement) plutôt que de bloquer
    l'analyse quand un joueur a peu ou pas d'historique connu."""
    high = "high"          # historique de matchs substantiel (Sackmann)
    medium = "medium"      # historique de matchs limité
    low = "low"            # pas d'historique, mais fiche bio trouvée (auto-discovery)
    insufficient = "insufficient"  # aucune donnée exploitable au-delà du nom


# ---------------------------------------------------------------- users ----

class User(Base):
    __tablename__ = "users"

    id = Column(UUIDType, primary_key=True, default=gen_uuid)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)

    plan = Column(Enum(PlanEnum), nullable=False, default=PlanEnum.free)
    stripe_customer_id = Column(String, nullable=True, unique=True)

    # Programme de parrainage (page "Invite et gagne") — code court unique
    # généré à l'inscription, cf. services/referral_service.py.
    referral_code = Column(String, nullable=True, unique=True, index=True)

    # Réinitialisation de mot de passe (page "Mot de passe oublié ?") — on ne
    # stocke jamais le token brut, seulement son hash SHA-256, comme pour un
    # token de session classique. Nullable : la grande majorité des users
    # n'ont jamais demandé de réinitialisation.
    reset_token_hash = Column(String, nullable=True, index=True)
    reset_token_expires_at = Column(DateTime, nullable=True)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    subscriptions = relationship("Subscription", back_populates="user")
    analyses = relationship("Analysis", back_populates="user")
    quota = relationship("UsageQuota", back_populates="user", uselist=False)


class Subscription(Base):
    """Historique des abonnements Stripe rattachés à un user (point 6)."""
    __tablename__ = "subscriptions"

    id = Column(UUIDType, primary_key=True, default=gen_uuid)
    user_id = Column(UUIDType, ForeignKey("users.id"), nullable=False)

    stripe_subscription_id = Column(String, unique=True, nullable=True)
    stripe_price_id = Column(String, nullable=True)
    plan = Column(Enum(PlanEnum), nullable=False)
    status = Column(String, nullable=False, default="active")  # active, canceled, past_due...
    current_period_end = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="subscriptions")


class Referral(Base):
    """
    Une relation de parrainage (page "Invite et gagne") : referrer_id a
    invité referred_user_id via son lien. status passe de "registered"
    (inscrit via le lien) à "subscribed" (a pris un plan payant) — c'est ce
    dernier événement qui déclenche la récompense en analyses bonus (cf.
    routers/billing.py, webhook checkout.session.completed).
    unique sur referred_user_id : un compte n'est parrainé qu'une fois, par
    le premier lien utilisé à l'inscription.
    """
    __tablename__ = "referrals"

    id = Column(UUIDType, primary_key=True, default=gen_uuid)
    referrer_id = Column(UUIDType, ForeignKey("users.id"), nullable=False)
    referred_user_id = Column(UUIDType, ForeignKey("users.id"), nullable=False, unique=True)

    status = Column(String, nullable=False, default="registered")  # registered | subscribed
    bonus_analyses_granted = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    subscribed_at = Column(DateTime, nullable=True)

    __table_args__ = (Index("ix_referrals_referrer", "referrer_id"),)


class UsageQuota(Base):
    """Compteur d'analyses consommées sur la période en cours (gating par plan)."""
    __tablename__ = "usage_quotas"

    id = Column(UUIDType, primary_key=True, default=gen_uuid)
    user_id = Column(UUIDType, ForeignKey("users.id"), unique=True, nullable=False)

    period_start = Column(DateTime, default=datetime.utcnow)
    period_end = Column(DateTime, nullable=True)
    analyses_used = Column(Integer, default=0)
    analyses_limit = Column(Integer, default=5)  # ex: plan free = 5/mois

    user = relationship("User", back_populates="quota")


# -------------------------------------------------------------- players ----

class Player(Base):
    """
    Un joueur ATP/WTA. sackmann_id permet de relier aux CSV Jeff Sackmann
    (colonne winner_id/loser_id des fichiers atp_matches_*.csv).
    """
    __tablename__ = "players"

    id = Column(UUIDType, primary_key=True, default=gen_uuid)
    sackmann_id = Column(Integer, unique=True, nullable=True, index=True)

    name = Column(String, nullable=False, index=True)
    country = Column(String, nullable=True)
    tour = Column(Enum(TourEnum), nullable=False, default=TourEnum.atp)
    hand = Column(String, nullable=True)  # R / L
    birthdate = Column(DateTime, nullable=True)
    height_cm = Column(Integer, nullable=True)

    # Elo courants, dénormalisés pour lecture rapide (recalculés par le job Elo).
    elo_overall = Column(Float, default=1500.0)
    elo_hard = Column(Float, default=1500.0)
    elo_clay = Column(Float, default=1500.0)
    elo_grass = Column(Float, default=1500.0)

    # Fiabilité des données disponibles (cf. services/data_confidence.py),
    # recalculée par scripts/sync_daily.py (historique Sackmann) et à la
    # création par auto-discovery (scripts/sync_hourly.py, cf. Fixture
    # ci-dessous). insufficient par défaut : un joueur nouvellement créé n'a
    # encore aucune donnée tant que le calcul n'a pas tourné.
    data_confidence = Column(Enum(DataConfidenceEnum), nullable=False, default=DataConfidenceEnum.insufficient)

    # Classement ATP/WTA courant, dénormalisé — mis à jour par le job horaire
    # (scripts/sync_hourly.py) depuis LiveTennisAPI. Distinct de l'Elo interne
    # (calculé par nous à partir de Sackmann) : c'est le classement officiel
    # du circuit, affiché tel quel côté frontend.
    current_rank = Column(Integer, nullable=True)
    current_rank_synced_at = Column(DateTime, nullable=True)

    # Note de style de jeu (cf. scripts/seed_playing_styles.py) : texte court,
    # factuel et qualitatif (coup dominant, main, tendance de jeu...), rédigé
    # à la main pour les joueurs suffisamment établis/médiatisés pour être
    # fiable -- PAS généré à la volée par un modèle sur des joueurs inconnus,
    # pour ne jamais inventer un style qu'on ne connaît pas vraiment. NULL =
    # pas encore couvert (rang trop bas / joueur trop récent) : le frontend
    # masque simplement le bloc, jamais de contenu inventé pour combler.
    playing_style = Column(Text, nullable=True)
    playing_style_updated_at = Column(DateTime, nullable=True)

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (Index("ix_players_name_tour", "name", "tour"),)


class EloHistory(Base):
    """Historique des ratings Elo (une ligne par match joué, pour tracer la courbe)."""
    __tablename__ = "elo_history"

    id = Column(UUIDType, primary_key=True, default=gen_uuid)
    player_id = Column(UUIDType, ForeignKey("players.id"), nullable=False)
    surface = Column(Enum(SurfaceEnum), nullable=False)
    rating_after = Column(Float, nullable=False)
    match_id = Column(UUIDType, ForeignKey("matches.id"), nullable=True)
    recorded_at = Column(DateTime, default=datetime.utcnow)


# -------------------------------------------------------- competitions ----

class Competition(Base):
    """Une compétition (Grand Chelem, Masters 1000, ATP/WTA Tour...)."""
    __tablename__ = "competitions"

    id = Column(UUIDType, primary_key=True, default=gen_uuid)
    name = Column(String, nullable=False)  # ex: "Roland-Garros"
    category = Column(String, nullable=False)  # grand_slam, masters_1000, atp_tour, wta_tour, finals
    tour = Column(Enum(TourEnum), nullable=False, default=TourEnum.atp)
    location = Column(String, nullable=True)
    surface = Column(Enum(SurfaceEnum), nullable=True)
    season = Column(Integer, nullable=True)

    __table_args__ = (UniqueConstraint("name", "season", "tour", name="uq_competition_name_season_tour"),)


class Match(Base):
    """
    Un match historique JOUÉ, importé depuis les CSV Sackmann (tour, qual/
    challenger, futures/ITF — cf. scripts/ingest_sackmann.py et
    scripts/sync_daily.py). winner_id toujours renseigné (un match sans
    vainqueur connu est un Fixture, pas un Match — cf. ci-dessous).
    """
    __tablename__ = "matches"

    id = Column(UUIDType, primary_key=True, default=gen_uuid)
    competition_id = Column(UUIDType, ForeignKey("competitions.id"), nullable=True)

    tourney_date = Column(DateTime, nullable=True)
    round = Column(String, nullable=True)  # F, SF, QF, R16, R32...
    surface = Column(Enum(SurfaceEnum), nullable=True)

    player1_id = Column(UUIDType, ForeignKey("players.id"), nullable=False)
    player2_id = Column(UUIDType, ForeignKey("players.id"), nullable=False)
    winner_id = Column(UUIDType, ForeignKey("players.id"), nullable=True)  # null = pas encore joué

    score = Column(String, nullable=True)  # "6-4 3-6 7-6(4)"
    stats = Column(JSONType, nullable=True)  # aces, doubles fautes, break points... (souple, évite N colonnes)

    source = Column(String, default="sackmann")  # sackmann | manual
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (Index("ix_matches_players", "player1_id", "player2_id"),)


class Fixture(Base):
    """
    Un match À VENIR (pas encore joué), synchronisé HORAIREMENT depuis
    LiveTennisAPI par scripts/sync_hourly.py — cf. README "Synchronisation
    des données". Remplace les appels live à livetennis_client.py depuis les
    routers : le site ne lit plus que cette table (routers/matches.py), plus
    aucun appel externe n'est déclenché par une requête utilisateur.

    Cotes de marché (Polymarket) et météo (OpenWeatherMap/Open-Meteo) sont
    dénormalisées directement sur la ligne plutôt que dans des tables à part :
    un Fixture = au plus un lookup marché + un lookup météo, inutile de
    normaliser pour ce volume. *_synced_at distincts de synced_at (l'horaire
    général) car un lookup peut légitimement échouer (aucun marché trouvé,
    météo indisponible) sans que cela invalide le reste de la ligne — un
    champ *_prob/*_c à NULL avec un *_synced_at récent veut dire "vérifié,
    rien trouvé", pas "jamais vérifié".

    external_id (identifiant du match côté LiveTennisAPI) sert de clé
    d'upsert idempotente pour le job horaire — un même Fixture est mis à jour
    en place plutôt que dupliqué à chaque sync.
    """
    __tablename__ = "fixtures"

    id = Column(UUIDType, primary_key=True, default=gen_uuid)
    external_id = Column(String, nullable=True, unique=True, index=True)
    source = Column(String, default="livetennisapi")

    player1_id = Column(UUIDType, ForeignKey("players.id"), nullable=False)
    player2_id = Column(UUIDType, ForeignKey("players.id"), nullable=False)
    # Noms bruts renvoyés par la source, conservés pour audit/débogage du
    # matching nom -> Player (indépendamment d'un futur renommage en base).
    player1_name_raw = Column(String, nullable=True)
    player2_name_raw = Column(String, nullable=True)

    tour = Column(Enum(TourEnum), nullable=True)
    surface = Column(Enum(SurfaceEnum), nullable=True)
    indoor = Column(Boolean, nullable=True)
    round = Column(String, nullable=True)
    tournament_name = Column(String, nullable=True)
    tournament_id_external = Column(String, nullable=True)
    city = Column(String, nullable=True)
    scheduled_time = Column(DateTime, nullable=True)

    # Cotes de marché dénormalisées (cf. services/market_providers.py),
    # rafraîchies par le job horaire.
    market_player1_prob = Column(Float, nullable=True)
    market_player2_prob = Column(Float, nullable=True)
    market_question = Column(String, nullable=True)
    market_synced_at = Column(DateTime, nullable=True)

    # Météo dénormalisée (cf. services/weather_providers.py), idem.
    weather_temp_c = Column(Float, nullable=True)
    weather_wind_kmh = Column(Float, nullable=True)
    weather_humidity_pct = Column(Integer, nullable=True)
    weather_description = Column(String, nullable=True)
    weather_synced_at = Column(DateTime, nullable=True)

    synced_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Lecture directe des fiches joueurs (nom courant, pays, classement,
    # data_confidence...) sans requête séparée -- utilisé par
    # routers/matches.py qui ne lit plus que cette table (cf. son en-tête).
    player1 = relationship("Player", foreign_keys=[player1_id])
    player2 = relationship("Player", foreign_keys=[player2_id])

    __table_args__ = (
        Index("ix_fixtures_players", "player1_id", "player2_id"),
        Index("ix_fixtures_scheduled_time", "scheduled_time"),
        Index("ix_fixtures_tour", "tour"),
    )


# ----------------------------------------------------------- analyses -----

class Analysis(Base):
    """
    Une prédiction générée pour un user (feature "Analyse" premium de l'app).
    """
    __tablename__ = "analyses"

    id = Column(UUIDType, primary_key=True, default=gen_uuid)
    user_id = Column(UUIDType, ForeignKey("users.id"), nullable=False)

    player1_id = Column(UUIDType, ForeignKey("players.id"), nullable=False)
    player2_id = Column(UUIDType, ForeignKey("players.id"), nullable=False)
    competition_id = Column(UUIDType, ForeignKey("competitions.id"), nullable=True)
    surface = Column(Enum(SurfaceEnum), nullable=True)

    predicted_winner_id = Column(UUIDType, ForeignKey("players.id"), nullable=False)
    win_probability = Column(Float, nullable=False)  # probabilité du gagnant prédit, 0-1
    model_version = Column(String, default="elo-v1")
    detail = Column(JSONType, nullable=True)  # facteurs explicatifs (form, h2h, elo_diff...)

    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="analyses")

    __table_args__ = (Index("ix_analyses_user_created", "user_id", "created_at"),)

"""synchronisation automatique des données (data_confidence, current_rank, fixtures)

Revision ID: d8e5a2f6c410
Revises: c7d4f9a12e3b
Create Date: 2026-09-03 00:00:00

Support du système de sync (cf. README "Synchronisation des données") :
  - players.data_confidence (nouvel enum) + players.current_rank /
    current_rank_synced_at, alimentés respectivement par
    scripts/sync_daily.py (Sackmann) et scripts/sync_hourly.py (LiveTennisAPI).
  - table fixtures : matchs à venir synchronisés HORAIREMENT, remplace les
    appels live à livetennis_client.py depuis les routers (cf.
    routers/matches.py) — cotes de marché et météo dénormalisées dessus.

Écrite à la main (pas d'autogenerate — pas de Postgres disponible dans cet
environnement de build) mais reflète exactement app/models.py. A valider avec
`alembic upgrade head` sur une vraie base avant mise en prod.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "d8e5a2f6c410"
down_revision = "c7d4f9a12e3b"
branch_labels = None
depends_on = None

data_confidence_enum = postgresql.ENUM(
    "high", "medium", "low", "insufficient", name="dataconfidenceenum", create_type=False,
)
# Réutilisés tels quels (déjà créés par la migration initiale) pour les
# colonnes de fixtures -- create_type=False partout, on ne les recrée pas.
tour_enum = postgresql.ENUM("atp", "wta", name="tourenum", create_type=False)
surface_enum = postgresql.ENUM("hard", "clay", "grass", "carpet", name="surfaceenum", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    data_confidence_enum.create(bind, checkfirst=True)

    op.add_column(
        "players",
        sa.Column("data_confidence", data_confidence_enum, nullable=False, server_default="insufficient"),
    )
    op.add_column("players", sa.Column("current_rank", sa.Integer, nullable=True))
    op.add_column("players", sa.Column("current_rank_synced_at", sa.DateTime, nullable=True))

    op.create_table(
        "fixtures",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("external_id", sa.String, nullable=True, unique=True),
        sa.Column("source", sa.String, server_default="livetennisapi"),
        sa.Column("player1_id", sa.String(36), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("player2_id", sa.String(36), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("player1_name_raw", sa.String, nullable=True),
        sa.Column("player2_name_raw", sa.String, nullable=True),
        sa.Column("tour", tour_enum, nullable=True),
        sa.Column("surface", surface_enum, nullable=True),
        sa.Column("indoor", sa.Boolean, nullable=True),
        sa.Column("round", sa.String, nullable=True),
        sa.Column("tournament_name", sa.String, nullable=True),
        sa.Column("tournament_id_external", sa.String, nullable=True),
        sa.Column("city", sa.String, nullable=True),
        sa.Column("scheduled_time", sa.DateTime, nullable=True),
        sa.Column("market_player1_prob", sa.Float, nullable=True),
        sa.Column("market_player2_prob", sa.Float, nullable=True),
        sa.Column("market_question", sa.String, nullable=True),
        sa.Column("market_synced_at", sa.DateTime, nullable=True),
        sa.Column("weather_temp_c", sa.Float, nullable=True),
        sa.Column("weather_wind_kmh", sa.Float, nullable=True),
        sa.Column("weather_humidity_pct", sa.Integer, nullable=True),
        sa.Column("weather_description", sa.String, nullable=True),
        sa.Column("weather_synced_at", sa.DateTime, nullable=True),
        sa.Column("synced_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_fixtures_external_id", "fixtures", ["external_id"], unique=True)
    op.create_index("ix_fixtures_players", "fixtures", ["player1_id", "player2_id"])
    op.create_index("ix_fixtures_scheduled_time", "fixtures", ["scheduled_time"])
    op.create_index("ix_fixtures_tour", "fixtures", ["tour"])


def downgrade() -> None:
    op.drop_table("fixtures")
    op.drop_column("players", "current_rank_synced_at")
    op.drop_column("players", "current_rank")
    op.drop_column("players", "data_confidence")

    bind = op.get_bind()
    data_confidence_enum.drop(bind, checkfirst=True)

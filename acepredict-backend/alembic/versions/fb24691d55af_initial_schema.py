"""initial schema

Revision ID: fb24691d55af
Revises:
Create Date: 2026-08-30 00:00:00

Écrite à la main (pas d'autogenerate — pas de Postgres disponible dans cet
environnement de build) mais reflète exactement app/models.py. A valider avec
`alembic upgrade head` sur une vraie base avant mise en prod.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "fb24691d55af"
down_revision = None
branch_labels = None
depends_on = None

# create_type=False : ces types sont utilisés dans PLUSIEURS tables (ex. plan_enum
# dans users ET subscriptions). On les crée une seule fois explicitement dans
# upgrade() ; sans create_type=False, SQLAlchemy retente de créer le type à
# chaque CREATE TABLE qui l'utilise et plante sur "already exists".
plan_enum = postgresql.ENUM("free", "starter", "pro", "lifetime", name="planenum", create_type=False)
surface_enum = postgresql.ENUM("hard", "clay", "grass", "carpet", name="surfaceenum", create_type=False)
tour_enum = postgresql.ENUM("atp", "wta", name="tourenum", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    plan_enum.create(bind, checkfirst=True)
    surface_enum.create(bind, checkfirst=True)
    tour_enum.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String, nullable=False, unique=True),
        sa.Column("hashed_password", sa.String, nullable=False),
        sa.Column("full_name", sa.String, nullable=True),
        sa.Column("plan", plan_enum, nullable=False, server_default="free"),
        sa.Column("stripe_customer_id", sa.String, nullable=True, unique=True),
        sa.Column("is_active", sa.Boolean, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "players",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("sackmann_id", sa.Integer, nullable=True, unique=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("country", sa.String, nullable=True),
        sa.Column("tour", tour_enum, nullable=False, server_default="atp"),
        sa.Column("hand", sa.String, nullable=True),
        sa.Column("birthdate", sa.DateTime, nullable=True),
        sa.Column("height_cm", sa.Integer, nullable=True),
        sa.Column("elo_overall", sa.Float, server_default="1500"),
        sa.Column("elo_hard", sa.Float, server_default="1500"),
        sa.Column("elo_clay", sa.Float, server_default="1500"),
        sa.Column("elo_grass", sa.Float, server_default="1500"),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_players_name_tour", "players", ["name", "tour"])

    op.create_table(
        "competitions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("category", sa.String, nullable=False),
        sa.Column("tour", tour_enum, nullable=False, server_default="atp"),
        sa.Column("location", sa.String, nullable=True),
        sa.Column("surface", surface_enum, nullable=True),
        sa.Column("season", sa.Integer, nullable=True),
        sa.UniqueConstraint("name", "season", "tour", name="uq_competition_name_season_tour"),
    )

    op.create_table(
        "matches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("competition_id", sa.String(36), sa.ForeignKey("competitions.id"), nullable=True),
        sa.Column("tourney_date", sa.DateTime, nullable=True),
        sa.Column("round", sa.String, nullable=True),
        sa.Column("surface", surface_enum, nullable=True),
        sa.Column("player1_id", sa.String(36), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("player2_id", sa.String(36), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("winner_id", sa.String(36), sa.ForeignKey("players.id"), nullable=True),
        sa.Column("score", sa.String, nullable=True),
        sa.Column("stats", sa.JSON().with_variant(postgresql.JSONB, "postgresql"), nullable=True),
        sa.Column("source", sa.String, server_default="sackmann"),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_matches_players", "matches", ["player1_id", "player2_id"])

    op.create_table(
        "elo_history",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("player_id", sa.String(36), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("surface", surface_enum, nullable=False),
        sa.Column("rating_after", sa.Float, nullable=False),
        sa.Column("match_id", sa.String(36), sa.ForeignKey("matches.id"), nullable=True),
        sa.Column("recorded_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("stripe_subscription_id", sa.String, nullable=True, unique=True),
        sa.Column("stripe_price_id", sa.String, nullable=True),
        sa.Column("plan", plan_enum, nullable=False),
        sa.Column("status", sa.String, nullable=False, server_default="active"),
        sa.Column("current_period_end", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "usage_quotas",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("period_start", sa.DateTime, nullable=True),
        sa.Column("period_end", sa.DateTime, nullable=True),
        sa.Column("analyses_used", sa.Integer, server_default="0"),
        sa.Column("analyses_limit", sa.Integer, server_default="5"),
    )

    op.create_table(
        "analyses",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("player1_id", sa.String(36), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("player2_id", sa.String(36), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("competition_id", sa.String(36), sa.ForeignKey("competitions.id"), nullable=True),
        sa.Column("surface", surface_enum, nullable=True),
        sa.Column("predicted_winner_id", sa.String(36), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("win_probability", sa.Float, nullable=False),
        sa.Column("model_version", sa.String, server_default="elo-v1"),
        sa.Column("detail", sa.JSON().with_variant(postgresql.JSONB, "postgresql"), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_analyses_user_created", "analyses", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_table("analyses")
    op.drop_table("usage_quotas")
    op.drop_table("subscriptions")
    op.drop_table("elo_history")
    op.drop_table("matches")
    op.drop_table("competitions")
    op.drop_table("players")
    op.drop_table("users")

    bind = op.get_bind()
    plan_enum.drop(bind, checkfirst=True)
    surface_enum.drop(bind, checkfirst=True)
    tour_enum.drop(bind, checkfirst=True)

"""ajoute match_pages (pages SEO par match, pronostic fige + resultat)

Revision ID: a5c7d9e2f1b3
Revises: a9b4c6e1f2d3
Create Date: 2026-10-11 00:00:00

Ecrite a la main : a valider avec `alembic upgrade head` sur la base reelle.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a5c7d9e2f1b3"
down_revision = "a9b4c6e1f2d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "match_pages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("match_key", sa.String(), nullable=False),
        sa.Column("player1_id", sa.String(36), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("player2_id", sa.String(36), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("tour", sa.String(), nullable=True),
        sa.Column("tournament_name", sa.String(), nullable=True),
        sa.Column("tournament_slug", sa.String(), nullable=True),
        sa.Column("round", sa.String(), nullable=True),
        sa.Column("scheduled_time", sa.DateTime(), nullable=True),
        sa.Column("snapshot", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("modified_at", sa.DateTime(), nullable=True),
        sa.Column("result_winner_id", sa.String(36), sa.ForeignKey("players.id"), nullable=True),
        sa.Column("result_score", sa.String(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_match_pages_slug", "match_pages", ["slug"], unique=True)
    op.create_index("ix_match_pages_match_key", "match_pages", ["match_key"], unique=True)
    op.create_index("ix_match_pages_tournament_slug", "match_pages", ["tournament_slug"])
    op.create_index("ix_match_pages_scheduled_time", "match_pages", ["scheduled_time"])
    op.create_index("ix_match_pages_finished_at", "match_pages", ["finished_at"])


def downgrade() -> None:
    op.drop_table("match_pages")

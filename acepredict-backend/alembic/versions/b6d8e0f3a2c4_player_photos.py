"""ajoute player_photos (cache des miniatures pour les pages SEO)

Revision ID: b6d8e0f3a2c4
Revises: a5c7d9e2f1b3
Create Date: 2026-10-11 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "b6d8e0f3a2c4"
down_revision = "a5c7d9e2f1b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "player_photos",
        sa.Column("player_id", sa.String(36), sa.ForeignKey("players.id"), primary_key=True),
        sa.Column("url", sa.String(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("player_photos")

"""ajoute players.playing_style (note de style de jeu, rédigée à la main)

Revision ID: f4a8d1c92b6e
Revises: d8e5a2f6c410
Create Date: 2026-09-06 00:00:00

Ajoute players.playing_style et players.playing_style_updated_at. Rempli
uniquement par scripts/seed_playing_styles.py, à la main, pour les joueurs
suffisamment établis pour qu'on soit sûr de ne rien inventer -- jamais
généré à la volée pour un joueur inconnu (cf. models.py::Player).
"""
from alembic import op
import sqlalchemy as sa

revision = "f4a8d1c92b6e"
down_revision = "d8e5a2f6c410"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("players", sa.Column("playing_style", sa.Text, nullable=True))
    op.add_column("players", sa.Column("playing_style_confidence", sa.String, nullable=True))
    op.add_column("players", sa.Column("playing_style_updated_at", sa.DateTime, nullable=True))


def downgrade() -> None:
    op.drop_column("players", "playing_style_updated_at")
    op.drop_column("players", "playing_style_confidence")
    op.drop_column("players", "playing_style")

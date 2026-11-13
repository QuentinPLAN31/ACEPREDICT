"""colonnes lisibles : users.referent, creator_conversions.referent / user_email

Revision ID: d3a7b9e1f2c6
Revises: c8f2a4d6e9b1
Create Date: 2026-11-13 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "d3a7b9e1f2c6"
down_revision = "c8f2a4d6e9b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("referent", sa.String(), nullable=True))
    op.create_index("ix_users_referent", "users", ["referent"])
    op.add_column("creator_conversions", sa.Column("referent", sa.String(), nullable=True))
    op.add_column("creator_conversions", sa.Column("user_email", sa.String(), nullable=True))
    op.create_index("ix_creator_conversions_referent", "creator_conversions", ["referent"])
    # Remplit les lignes deja rattachees a un createur.
    op.execute("UPDATE users SET referent = (SELECT slug FROM creators WHERE creators.id = users.creator_id) WHERE creator_id IS NOT NULL")
    op.execute("UPDATE creator_conversions SET referent = (SELECT slug FROM creators WHERE creators.id = creator_conversions.creator_id)")
    op.execute("UPDATE creator_conversions SET user_email = (SELECT email FROM users WHERE users.id = creator_conversions.user_id)")


def downgrade() -> None:
    op.drop_index("ix_creator_conversions_referent", table_name="creator_conversions")
    op.drop_column("creator_conversions", "user_email")
    op.drop_column("creator_conversions", "referent")
    op.drop_index("ix_users_referent", table_name="users")
    op.drop_column("users", "referent")

"""connexion / inscription avec Google

Revision ID: e1f9b3c8a2d5
Revises: b2e6f7a91c04
Create Date: 2026-09-18 00:00:00

Ajoute users.google_id (identifiant "sub" du jeton Google, unique) et rend
users.hashed_password nullable : un compte créé via Google n'a pas de mot de
passe local tant qu'il n'en définit pas un explicitement (non géré ici -- il
peut toujours se connecter avec le bouton Google).
"""
from alembic import op
import sqlalchemy as sa

revision = "e1f9b3c8a2d5"
down_revision = "b2e6f7a91c04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("google_id", sa.String(), nullable=True))
    op.create_index("ix_users_google_id", "users", ["google_id"], unique=True)
    op.alter_column("users", "hashed_password", existing_type=sa.String(), nullable=True)


def downgrade() -> None:
    op.alter_column("users", "hashed_password", existing_type=sa.String(), nullable=False)
    op.drop_index("ix_users_google_id", table_name="users")
    op.drop_column("users", "google_id")

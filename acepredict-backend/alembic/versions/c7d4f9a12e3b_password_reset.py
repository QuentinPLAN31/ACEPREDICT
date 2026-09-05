"""réinitialisation de mot de passe ("Mot de passe oublié ?")

Revision ID: c7d4f9a12e3b
Revises: a1c3e7f2b901
Create Date: 2026-09-01 00:00:00

Ajoute users.reset_token_hash / users.reset_token_expires_at : le hash SHA-256
d'un token à usage unique envoyé par e-mail (cf. services/email_service.py et
routers/auth.py /auth/forgot-password, /auth/reset-password). Le token brut
n'est jamais stocké en base, seulement son hash — comme un mot de passe.
"""
from alembic import op
import sqlalchemy as sa

revision = "c7d4f9a12e3b"
down_revision = "a1c3e7f2b901"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("reset_token_hash", sa.String, nullable=True))
    op.add_column("users", sa.Column("reset_token_expires_at", sa.DateTime, nullable=True))
    op.create_index("ix_users_reset_token_hash", "users", ["reset_token_hash"])


def downgrade() -> None:
    op.drop_index("ix_users_reset_token_hash", table_name="users")
    op.drop_column("users", "reset_token_expires_at")
    op.drop_column("users", "reset_token_hash")

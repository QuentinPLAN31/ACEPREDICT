"""ajoute users.device_id (anti-abus "un compte par appareil" a l'inscription)

Revision ID: a9b4c6e1f2d3
Revises: c3f8a5d21b7e
Create Date: 2026-10-03 00:00:00

Contexte : empecher qu'un meme appareil cree plusieurs comptes gratuits pour
contourner les quotas d'essai. Le frontend genere un identifiant d'appareil
(localStorage, cf. visitennis_1.html) envoye a l'inscription (/auth/register
et /auth/google) ; routers/auth.py refuse la creation d'un nouveau compte si
un utilisateur existe deja avec le meme device_id. Colonne nullable (comptes
crees avant cette fonctionnalite) et non unique en base : le controle
d'unicite applicatif permet un message d'erreur clair plutot qu'une erreur
d'integrite SQL brute.

Ecrite a la main (pas d'autogenerate -- pas de Postgres disponible dans cet
environnement de build), a valider avec `alembic upgrade head` sur une vraie
base avant mise en prod (cf. migrations precedentes du projet).
"""
from alembic import op
import sqlalchemy as sa

revision = "a9b4c6e1f2d3"
down_revision = "c3f8a5d21b7e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("device_id", sa.String(), nullable=True))
    op.create_index("ix_users_device_id", "users", ["device_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_users_device_id", table_name="users")
    op.drop_column("users", "device_id")

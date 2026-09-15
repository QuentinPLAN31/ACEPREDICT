"""ajoute usage_quotas.bonus_analyses (packs achetes a l'unite, separes du reset periodique)

Revision ID: b2e6f7a91c04
Revises: f4a8d1c92b6e
Create Date: 2026-09-15 00:00:00

Contexte : app/deps.py::require_quota reset désormais analyses_limit à la
valeur de base du plan à chaque nouvelle période (jour pour Starter, mois
pour les autres -- avant ce correctif, aucun reset n'existait, cf. commit
associé). Sans cette colonne, un pack ponctuel de 5 analyses acheté
(routers/billing.py, plan="pack5") aurait été ajouté à analyses_limit puis
effacé au reset suivant. bonus_analyses est donc un compteur séparé, jamais
remis à zéro par le reset périodique, ajouté au total autorisé.

Écrite à la main (pas d'autogenerate — pas de Postgres disponible dans cet
environnement de build), à valider avec `alembic upgrade head` sur une vraie
base avant mise en prod (cf. migrations précédentes du projet).
"""
from alembic import op
import sqlalchemy as sa

revision = "b2e6f7a91c04"
down_revision = "f4a8d1c92b6e"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "usage_quotas",
        sa.Column("bonus_analyses", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade():
    op.drop_column("usage_quotas", "bonus_analyses")

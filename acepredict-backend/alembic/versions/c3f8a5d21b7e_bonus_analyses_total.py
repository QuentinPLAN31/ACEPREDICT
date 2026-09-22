"""ajoute usage_quotas.bonus_analyses_total (total cumule de packs ponctuels achetes)

Revision ID: c3f8a5d21b7e
Revises: e1f9b3c8a2d5
Create Date: 2026-09-22 00:00:00

Contexte : bonus_analyses (cf. migration b2e6f7a91c04) stocke le SOLDE
restant d'un pack ponctuel, décrémenté à chaque analyse consommée dessus
(routers/analyses.py). Pour afficher une vraie jauge "curseur ponctuel"
(X consommées / Y achetées) sur la page Compte, il faut aussi le total
CUMULE jamais acheté, qui ne redescend jamais -- sinon impossible de
calculer une progression, seulement un solde restant. bonus_analyses_total
est incrémenté en même temps que bonus_analyses à chaque achat de pack
(routers/billing.py::stripe_webhook), mais jamais décrémenté.

Écrite à la main (pas d'autogenerate — pas de Postgres disponible dans cet
environnement de build), à valider avec `alembic upgrade head` sur une vraie
base avant mise en prod (cf. migrations précédentes du projet).
"""
from alembic import op
import sqlalchemy as sa

revision = "c3f8a5d21b7e"
down_revision = "e1f9b3c8a2d5"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "usage_quotas",
        sa.Column("bonus_analyses_total", sa.Integer(), nullable=False, server_default="0"),
    )
    # Backfill : pour les comptes qui ont déjà un solde bonus_analyses avant
    # cette migration (packs achetés avant l'ajout de cette colonne), on ne
    # connaît pas leur total historique exact -- on initialise au solde
    # actuel comme meilleure approximation (mieux qu'un total à 0 qui
    # afficherait une jauge à 100% "consommée" à tort pour un solde non nul).
    op.execute("UPDATE usage_quotas SET bonus_analyses_total = bonus_analyses WHERE bonus_analyses > 0")


def downgrade():
    op.drop_column("usage_quotas", "bonus_analyses_total")

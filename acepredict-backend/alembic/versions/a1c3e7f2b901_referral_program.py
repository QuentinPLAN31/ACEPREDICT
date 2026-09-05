"""programme de parrainage (page "Invite et gagne")

Revision ID: a1c3e7f2b901
Revises: fb24691d55af
Create Date: 2026-08-31 00:00:00

Ajoute users.referral_code (code court unique, généré à l'inscription — cf.
services/referral_service.py) et la table referrals (une ligne par filleul,
cf. models.Referral). Écrite à la main comme la migration initiale (pas
d'autogenerate — pas de Postgres disponible dans cet environnement de build) ;
à valider avec `alembic upgrade head` sur une vraie base avant mise en prod.
"""
from alembic import op
import sqlalchemy as sa

revision = "a1c3e7f2b901"
down_revision = "fb24691d55af"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("referral_code", sa.String, nullable=True))
    op.create_unique_constraint("uq_users_referral_code", "users", ["referral_code"])
    op.create_index("ix_users_referral_code", "users", ["referral_code"])

    op.create_table(
        "referrals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("referrer_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("referred_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("status", sa.String, nullable=False, server_default="registered"),
        sa.Column("bonus_analyses_granted", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("subscribed_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_referrals_referrer", "referrals", ["referrer_id"])


def downgrade() -> None:
    op.drop_table("referrals")
    op.drop_index("ix_users_referral_code", table_name="users")
    op.drop_constraint("uq_users_referral_code", "users", type_="unique")
    op.drop_column("users", "referral_code")

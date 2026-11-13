"""programme créateurs : creators, creator_conversions, users.creator_id

Revision ID: c8f2a4d6e9b1
Revises: b6d8e0f3a2c4
Create Date: 2026-11-13 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "c8f2a4d6e9b1"
down_revision = "b6d8e0f3a2c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "creators",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("contact", sa.String(), nullable=True),
        sa.Column("dashboard_key", sa.String(), nullable=False),
        sa.Column("clicks", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=True, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_creators_slug", "creators", ["slug"], unique=True)

    op.create_table(
        "creator_conversions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("creator_id", sa.String(36), sa.ForeignKey("creators.id"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("product", sa.String(), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=True),
        sa.Column("commission_cents", sa.Integer(), nullable=False),
        sa.Column("stripe_session_id", sa.String(), nullable=True),
        sa.Column("stripe_payment_intent", sa.String(), nullable=True),
        sa.Column("stripe_customer_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_creator_conversions_creator_id", "creator_conversions", ["creator_id"])
    op.create_index("ix_creator_conversions_stripe_payment_intent", "creator_conversions", ["stripe_payment_intent"])
    op.create_index("ix_creator_conversions_stripe_customer_id", "creator_conversions", ["stripe_customer_id"])

    op.add_column("users", sa.Column("creator_id", sa.String(36), sa.ForeignKey("creators.id"), nullable=True))
    op.add_column("users", sa.Column("creator_attributed_at", sa.DateTime(), nullable=True))
    op.create_index("ix_users_creator_id", "users", ["creator_id"])


def downgrade() -> None:
    op.drop_index("ix_users_creator_id", table_name="users")
    op.drop_column("users", "creator_attributed_at")
    op.drop_column("users", "creator_id")
    op.drop_table("creator_conversions")
    op.drop_table("creators")

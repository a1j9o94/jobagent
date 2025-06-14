"""Initial database schema

Revision ID: 925341dafe91
Revises:
Create Date: 2025-06-05 22:29:09.125583

"""

from typing import Sequence, Union

from alembic import op
import sqlmodel.sql.sqltypes
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "925341dafe91"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "company",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("website", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "profile",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("headline", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "skill",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "credential",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("site_hostname", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("username", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("encrypted_password", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["profile.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_credential_site_hostname"),
        "credential",
        ["site_hostname"],
        unique=False,
    )
    op.create_table(
        "role",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("posting_url", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("unique_hash", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "SOURCED", "RANKED", "APPLYING", "APPLIED", "IGNORED", name="rolestatus"
            ),
            nullable=False,
        ),
        sa.Column("rank_score", sa.Float(), nullable=True),
        sa.Column("rank_rationale", sa.Text(), nullable=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["company.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_role_unique_hash"), "role", ["unique_hash"], unique=True)
    op.create_table(
        "userpreference",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("key", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("value", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("last_updated", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["profile.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_userpreference_key"), "userpreference", ["key"], unique=False
    )
    op.create_table(
        "application",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("celery_task_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "DRAFT",
                "NEEDS_USER_INFO",
                "READY_TO_SUBMIT",
                "SUBMITTING",
                "SUBMITTED",
                "ERROR",
                "REJECTED",
                "INTERVIEW",
                "OFFER",
                "CLOSED",
                name="applicationstatus",
            ),
            nullable=False,
        ),
        sa.Column("resume_s3_url", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column(
            "cover_letter_s3_url", sqlmodel.sql.sqltypes.AutoString(), nullable=True
        ),
        sa.Column("custom_answers", sa.JSON(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["profile.id"],
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["role.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_application_celery_task_id"),
        "application",
        ["celery_task_id"],
        unique=False,
    )
    op.create_table(
        "roleskilllink",
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("skill_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["role.id"],
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"],
            ["skill.id"],
        ),
        sa.PrimaryKeyConstraint("role_id", "skill_id"),
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("roleskilllink")
    op.drop_index(op.f("ix_application_celery_task_id"), table_name="application")
    op.drop_table("application")
    op.drop_index(op.f("ix_userpreference_key"), table_name="userpreference")
    op.drop_table("userpreference")
    op.drop_index(op.f("ix_role_unique_hash"), table_name="role")
    op.drop_table("role")
    op.drop_index(op.f("ix_credential_site_hostname"), table_name="credential")
    op.drop_table("credential")
    op.drop_table("skill")
    op.drop_table("profile")
    op.drop_table("company")
    # ### end Alembic commands ###

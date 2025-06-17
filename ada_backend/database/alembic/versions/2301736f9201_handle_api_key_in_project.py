"""handle api key in project

Revision ID: 2301736f9201
Revises: 3502295460f2
Create Date: 2025-06-11 09:53:52.566127

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from ada_backend.database.models import OrgSecretType


# revision identifiers, used by Alembic.
revision: str = "2301736f9201"
down_revision: Union[str, None] = "3502295460f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


enum_name = "org_secret_type"


def upgrade() -> None:
    op.drop_constraint(op.f("basic_parameters_organization_secret_id_fkey"), "basic_parameters", type_="foreignkey")
    op.create_foreign_key(
        "basic_parameters_organization_secret_id_fkey",
        "basic_parameters",
        "organization_secrets",
        ["organization_secret_id"],
        ["id"],
        ondelete="CASCADE",
    )
    org_secret_type_enum = sa.Enum("llm_api_key", "password", name=enum_name)
    org_secret_type_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "organization_secrets",
        sa.Column(
            "secret_type",
            org_secret_type_enum,
            nullable=False,
            server_default=OrgSecretType.LLM_API_KEY.value,
        ),
    )
    op.execute("ALTER TYPE parameter_type ADD VALUE IF NOT EXISTS 'secrets'")
    op.execute("ALTER TYPE parameter_type ADD VALUE IF NOT EXISTS 'llm_api_key'")


def downgrade() -> None:
    op.drop_column("organization_secrets", "secret_type")
    sa.Enum(name=enum_name).drop(op.get_bind(), checkfirst=True)
    op.drop_constraint("basic_parameters_organization_secret_id_fkey", "basic_parameters", type_="foreignkey")
    op.create_foreign_key(
        op.f("basic_parameters_organization_secret_id_fkey"),
        "basic_parameters",
        "organization_secrets",
        ["organization_secret_id"],
        ["id"],
    )
    op.execute(
        """
        DELETE FROM basic_parameters
        WHERE parameter_definition_id IN (
            SELECT id FROM component_parameter_definitions
            WHERE type = 'llm_api_key'
        )
    """
    )
    op.execute(
        """
        DELETE FROM component_parameter_definitions
        WHERE type = 'llm_api_key'
    """
    )

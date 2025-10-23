"""migrate api input to start component

Revision ID: 20003587e42q
Revises: f9c9976e066e
Create Date: 2025-01-03 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20003587e42q"
down_revision: Union[str, None] = "558db5695d27"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Update component name and description from "API Input" to "Start" in the components table
    op.execute(
        """
        UPDATE components 
        SET name = 'Start', 
            description = 'Start node that receives initial workflow input and configures triggers'
        WHERE name = 'API Input'
        """
    )

    # Update component instance names and refs from "API Input" to "Start"
    op.execute(
        """
        UPDATE component_instances 
        SET name = 'Start' 
        WHERE name = 'API Input'
        """
    )

    op.execute(
        """
        UPDATE component_instances 
        SET ref = 'Start' 
        WHERE ref = 'API Input'
        """
    )

    # Remove Trigger category association for the Input/Start component
    op.execute(
        """
        DELETE FROM component_categories 
        WHERE component_id IN (
            SELECT id FROM components WHERE name IN ('API Input', 'Start')
        )
        AND category_id IN (
            SELECT id FROM categories WHERE name = 'Trigger'
        )
        """
    )


def downgrade() -> None:
    # Revert component name and description from "Start" back to "API Input" in the components table
    op.execute(
        """
        UPDATE components 
        SET name = 'API Input',
            description = 'This block is triggered by an API call'
        WHERE name = 'Start'
        """
    )

    # Revert component instance names and refs from "Start" back to "API Input"
    op.execute(
        """
        UPDATE component_instances 
        SET name = 'API Input' 
        WHERE name = 'Start'
        """
    )

    op.execute(
        """
        UPDATE component_instances 
        SET ref = 'API Input' 
        WHERE ref = 'Start'
        """
    )

    # Restore Trigger category association for the API Input component
    op.execute(
        """
        INSERT INTO component_categories (id, component_id, category_id)
        SELECT gen_random_uuid(), c.id, cat.id
        FROM components c, categories cat
        WHERE c.name = 'API Input' AND cat.name = 'Trigger'
        AND NOT EXISTS (
            SELECT 1 FROM component_categories cc 
            WHERE cc.component_id = c.id AND cc.category_id = cat.id
        )
        """
    )

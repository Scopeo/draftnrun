"""Initial schema after PostgreSQL migration

Revision ID: 2795c830aa09
Revises:
Create Date: 2025-05-20 01:18:19.714048

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "2795c830aa09"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "data_sources",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("type", sa.Enum("google_drive", "local", name="source_type"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("database_name", sa.String(), nullable=True),
        sa.Column("database_schema", sa.String(), nullable=True),
        sa.Column("database_table_name", sa.String(), nullable=True),
        sa.Column("qdrant_collection_name", sa.String(), nullable=True),
        sa.Column("qdrant_schema", sa.JSON(), nullable=True),
        sa.Column("embedding_model_name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("last_ingestion_time", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_data_sources_id"), "data_sources", ["id"], unique=False)
    op.create_table(
        "graph_runners",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_graph_runners_id"), "graph_runners", ["id"], unique=False)
    op.create_table(
        "organization_secrets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("encrypted_secret", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_organization_secrets_id"), "organization_secrets", ["id"], unique=False)
    op.create_index(op.f("ix_organization_secrets_key"), "organization_secrets", ["key"], unique=False)
    op.create_table(
        "projects",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("companion_image_url", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_projects_id"), "projects", ["id"], unique=False)
    op.create_table(
        "tool_descriptions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("tool_properties", sa.JSON(), nullable=True),
        sa.Column("required_tool_properties", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_tool_descriptions_id"), "tool_descriptions", ["id"], unique=False)
    op.create_table(
        "api_keys",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("public_key", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("creator_user_id", sa.UUID(), nullable=False),
        sa.Column("revoker_user_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_key"),
    )
    op.create_index(op.f("ix_api_keys_creator_user_id"), "api_keys", ["creator_user_id"], unique=False)
    op.create_index(op.f("ix_api_keys_id"), "api_keys", ["id"], unique=False)
    op.create_index(op.f("ix_api_keys_project_id"), "api_keys", ["project_id"], unique=False)
    op.create_index(op.f("ix_api_keys_revoker_user_id"), "api_keys", ["revoker_user_id"], unique=False)
    op.create_table(
        "components",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_agent", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("function_callable", sa.Boolean(), nullable=False),
        sa.Column("can_use_function_calling", sa.Boolean(), nullable=False),
        sa.Column("is_protected", sa.Boolean(), nullable=False),
        sa.Column("default_tool_description_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["default_tool_description_id"],
            ["tool_descriptions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_components_id"), "components", ["id"], unique=False)
    op.create_table(
        "graph_runner_nodes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("node_id", sa.UUID(), nullable=False),
        sa.Column("graph_runner_id", sa.UUID(), nullable=False),
        sa.Column("node_type", sa.Enum("graph_runner", "component_instance", name="node_type"), nullable=False),
        sa.Column("is_start_node", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["graph_runner_id"], ["graph_runners.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_graph_runner_nodes_id"), "graph_runner_nodes", ["id"], unique=False)
    op.create_index(op.f("ix_graph_runner_nodes_node_id"), "graph_runner_nodes", ["node_id"], unique=True)
    op.create_table(
        "ingestion_tasks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("source_name", sa.String(), nullable=False),
        sa.Column("source_type", sa.Enum("google_drive", "local", name="source_type"), nullable=False),
        sa.Column(
            "status", sa.Enum("pending", "in_progress", "completed", "failed", name="task_status"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["source_id"], ["data_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ingestion_tasks_id"), "ingestion_tasks", ["id"], unique=False)
    op.create_table(
        "project_env_binding",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("environment", sa.Enum("draft", "production", name="env_type"), nullable=True),
        sa.Column("graph_runner_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["graph_runner_id"], ["graph_runners.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_project_env_binding_id"), "project_env_binding", ["id"], unique=False)
    op.create_table(
        "component_instances",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("component_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("ref", sa.String(), nullable=True),
        sa.Column("tool_description_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["component_id"], ["components.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tool_description_id"],
            ["tool_descriptions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_component_instances_id"), "component_instances", ["id"], unique=False)
    op.create_index(op.f("ix_component_instances_name"), "component_instances", ["name"], unique=False)
    op.create_index(op.f("ix_component_instances_ref"), "component_instances", ["ref"], unique=False)
    op.create_table(
        "component_parameter_definitions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("component_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "type",
            sa.Enum(
                "string",
                "integer",
                "float",
                "boolean",
                "json",
                "component",
                "tool",
                "data_source",
                name="parameter_type",
            ),
            nullable=False,
        ),
        sa.Column("nullable", sa.Boolean(), nullable=False),
        sa.Column("order", sa.Integer(), nullable=True),
        sa.Column("default", sa.String(), nullable=True),
        sa.Column(
            "ui_component",
            sa.Enum(
                "Autocomplete",
                "Checkbox",
                "Combobox",
                "Date Time Picker",
                "Editors",
                "File Input",
                "Radio",
                "Custom Input",
                "Range Slider",
                "Rating",
                "Select",
                "Slider",
                "Switch",
                "Textarea",
                "Textfield",
                name="ui_component",
            ),
            nullable=True,
        ),
        sa.Column("ui_component_properties", sa.JSON(), nullable=True),
        sa.Column("is_advanced", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["component_id"], ["components.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_component_parameter_definitions_id"), "component_parameter_definitions", ["id"], unique=False
    )
    op.create_table(
        "graph_runner_edges",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source_node_id", sa.UUID(), nullable=False),
        sa.Column("target_node_id", sa.UUID(), nullable=False),
        sa.Column("graph_runner_id", sa.UUID(), nullable=False),
        sa.Column("order", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["graph_runner_id"], ["graph_runners.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_node_id"], ["graph_runner_nodes.node_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_node_id"], ["graph_runner_nodes.node_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_graph_runner_edges_id"), "graph_runner_edges", ["id"], unique=False)
    op.create_table(
        "basic_parameters",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("component_instance_id", sa.UUID(), nullable=False),
        sa.Column("parameter_definition_id", sa.UUID(), nullable=False),
        sa.Column("value", sa.String(), nullable=True),
        sa.Column("organization_secret_id", sa.UUID(), nullable=True),
        sa.Column("order", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            sqltext=(
                "(value IS NOT NULL AND organization_secret_id IS NULL) OR "
                "(value IS NULL AND organization_secret_id IS NOT NULL)"
            ),
            name="check_value_or_organization_secret",
        ),
        sa.ForeignKeyConstraint(
            ["component_instance_id"],
            ["component_instances.id"],
        ),
        sa.ForeignKeyConstraint(
            ["organization_secret_id"],
            ["organization_secrets.id"],
        ),
        sa.ForeignKeyConstraint(
            ["parameter_definition_id"],
            ["component_parameter_definitions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_basic_parameters_id"), "basic_parameters", ["id"], unique=False)
    op.create_table(
        "comp_param_child_comps_relationships",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("component_parameter_definition_id", sa.UUID(), nullable=False),
        sa.Column("child_component_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["child_component_id"], ["components.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["component_parameter_definition_id"], ["component_parameter_definitions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_comp_param_child_comps_relationships_id"),
        "comp_param_child_comps_relationships",
        ["id"],
        unique=False,
    )
    op.create_table(
        "component_sub_inputs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("parent_component_instance_id", sa.UUID(), nullable=False),
        sa.Column("child_component_instance_id", sa.UUID(), nullable=False),
        sa.Column("parameter_definition_id", sa.UUID(), nullable=False),
        sa.Column("order", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["child_component_instance_id"], ["component_instances.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["parameter_definition_id"], ["component_parameter_definitions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["parent_component_instance_id"], ["component_instances.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_component_sub_inputs_id"), "component_sub_inputs", ["id"], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f("ix_component_sub_inputs_id"), table_name="component_sub_inputs")
    op.drop_table("component_sub_inputs")
    op.drop_index(
        op.f("ix_comp_param_child_comps_relationships_id"), table_name="comp_param_child_comps_relationships"
    )
    op.drop_table("comp_param_child_comps_relationships")
    op.drop_index(op.f("ix_basic_parameters_id"), table_name="basic_parameters")
    op.drop_table("basic_parameters")
    op.drop_index(op.f("ix_graph_runner_edges_id"), table_name="graph_runner_edges")
    op.drop_table("graph_runner_edges")
    op.drop_index(op.f("ix_component_parameter_definitions_id"), table_name="component_parameter_definitions")
    op.drop_table("component_parameter_definitions")
    op.drop_index(op.f("ix_component_instances_ref"), table_name="component_instances")
    op.drop_index(op.f("ix_component_instances_name"), table_name="component_instances")
    op.drop_index(op.f("ix_component_instances_id"), table_name="component_instances")
    op.drop_table("component_instances")
    op.drop_index(op.f("ix_project_env_binding_id"), table_name="project_env_binding")
    op.drop_table("project_env_binding")
    op.drop_index(op.f("ix_ingestion_tasks_id"), table_name="ingestion_tasks")
    op.drop_table("ingestion_tasks")
    op.drop_index(op.f("ix_graph_runner_nodes_node_id"), table_name="graph_runner_nodes")
    op.drop_index(op.f("ix_graph_runner_nodes_id"), table_name="graph_runner_nodes")
    op.drop_table("graph_runner_nodes")
    op.drop_index(op.f("ix_components_id"), table_name="components")
    op.drop_table("components")
    op.drop_index(op.f("ix_api_keys_revoker_user_id"), table_name="api_keys")
    op.drop_index(op.f("ix_api_keys_project_id"), table_name="api_keys")
    op.drop_index(op.f("ix_api_keys_id"), table_name="api_keys")
    op.drop_index(op.f("ix_api_keys_creator_user_id"), table_name="api_keys")
    op.drop_table("api_keys")
    op.drop_index(op.f("ix_tool_descriptions_id"), table_name="tool_descriptions")
    op.drop_table("tool_descriptions")
    op.drop_index(op.f("ix_projects_id"), table_name="projects")
    op.drop_table("projects")
    op.drop_index(op.f("ix_organization_secrets_key"), table_name="organization_secrets")
    op.drop_index(op.f("ix_organization_secrets_id"), table_name="organization_secrets")
    op.drop_table("organization_secrets")
    op.drop_index(op.f("ix_graph_runners_id"), table_name="graph_runners")
    op.drop_table("graph_runners")
    op.drop_index(op.f("ix_data_sources_id"), table_name="data_sources")
    op.drop_table("data_sources")
    # ### end Alembic commands ###

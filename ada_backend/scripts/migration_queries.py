"""
SQL query templates for QA project migration.

Contains all DELETE, INSERT, and validation queries organized by migration steps.
All queries are parameterized with organization_id for flexibility.
"""

from typing import Dict, List, Tuple

# Target organization ID
TARGET_ORG_ID = "18012b84-b605-4669-95bf-55aa16c5513c"


class MigrationQueries:
    """SQL queries for QA project migration from staging to preprod."""

    # =============================================================================
    # CLEANUP QUERIES (Step 1: Clean Target Environment)
    # =============================================================================

    CLEANUP_QUERIES = {
        "component_sub_inputs": """
            DELETE FROM component_sub_inputs WHERE parent_component_instance_id IN (
                SELECT ci.id FROM component_instances ci
                JOIN graph_runner_nodes grn ON ci.id = grn.node_id
                JOIN graph_runners gr ON grn.graph_runner_id = gr.id
                JOIN project_env_binding peb ON gr.id = peb.graph_runner_id
                JOIN projects p ON peb.project_id = p.id
                WHERE p.organization_id = %s
            )
        """,
        "port_mappings": """
            DELETE FROM port_mappings WHERE graph_runner_id IN (
                SELECT gr.id FROM graph_runners gr
                JOIN project_env_binding peb ON gr.id = peb.graph_runner_id
                JOIN projects p ON peb.project_id = p.id
                WHERE p.organization_id = %s
            )
        """,
        "basic_parameters": """
            DELETE FROM basic_parameters WHERE component_instance_id IN (
                SELECT ci.id FROM component_instances ci
                JOIN graph_runner_nodes grn ON ci.id = grn.node_id
                JOIN graph_runners gr ON grn.graph_runner_id = gr.id
                JOIN project_env_binding peb ON gr.id = peb.graph_runner_id
                JOIN projects p ON peb.project_id = p.id
                WHERE p.organization_id = %s
            )
        """,
        "graph_runner_edges": """
            DELETE FROM graph_runner_edges WHERE graph_runner_id IN (
                SELECT gr.id FROM graph_runners gr
                JOIN project_env_binding peb ON gr.id = peb.graph_runner_id
                JOIN projects p ON peb.project_id = p.id
                WHERE p.organization_id = %s
            )
        """,
        "graph_runner_nodes": """
            DELETE FROM graph_runner_nodes WHERE graph_runner_id IN (
                SELECT gr.id FROM graph_runners gr
                JOIN project_env_binding peb ON gr.id = peb.graph_runner_id
                JOIN projects p ON peb.project_id = p.id
                WHERE p.organization_id = %s
            )
        """,
        "project_env_binding": """
            DELETE FROM project_env_binding WHERE project_id IN (
                SELECT id FROM projects WHERE organization_id = %s
            )
        """,
        "workflow_projects": """
            DELETE FROM workflow_projects WHERE id IN (
                SELECT id FROM projects WHERE organization_id = %s
            )
        """,
        "agent_projects": """
            DELETE FROM agent_projects WHERE id IN (
                SELECT id FROM projects WHERE organization_id = %s
            )
        """,
        "component_instances": """
            DELETE FROM component_instances WHERE id IN (
                SELECT ci.id FROM component_instances ci
                JOIN graph_runner_nodes grn ON ci.id = grn.node_id
                JOIN graph_runners gr ON grn.graph_runner_id = gr.id
                JOIN project_env_binding peb ON gr.id = peb.graph_runner_id
                JOIN projects p ON peb.project_id = p.id
                WHERE p.organization_id = %s
            )
        """,
        "graph_runners": """
            DELETE FROM graph_runners WHERE id IN (
                SELECT gr.id FROM graph_runners gr
                JOIN project_env_binding peb ON gr.id = peb.graph_runner_id
                JOIN projects p ON peb.project_id = p.id
                WHERE p.organization_id = %s
            )
        """,
        "projects": """
            DELETE FROM projects WHERE organization_id = %s
        """,
    }

    # =============================================================================
    # MIGRATION QUERIES (Steps 2-5: Copy Data)
    # =============================================================================

    # Step 2: Copy Core Data
    CORE_DATA_QUERIES = {
        "projects": """
            INSERT INTO projects (id, name, type, description, organization_id, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        "workflow_projects": """
            INSERT INTO workflow_projects (id)
            VALUES (%s)
        """,
        "agent_projects": """
            INSERT INTO agent_projects (id)
            VALUES (%s)
        """,
    }

    # Step 3: Copy Graph Data
    GRAPH_DATA_QUERIES = {
        "graph_runners": """
            INSERT INTO graph_runners (id, created_at, updated_at, tag_version)
            SELECT id, created_at, updated_at, tag_version
            FROM staging.graph_runners gr
            JOIN staging.project_env_binding peb ON gr.id = peb.graph_runner_id
            JOIN staging.projects p ON peb.project_id = p.id
            WHERE p.organization_id = %s
        """,
        "component_instances": """
            INSERT INTO component_instances (id, component_id, name, ref, tool_description_id, created_at)
            SELECT ci.id, ci.component_id, ci.name, ci.ref, ci.tool_description_id, ci.created_at
            FROM staging.component_instances ci
            JOIN staging.graph_runner_nodes grn ON ci.id = grn.node_id
            JOIN staging.graph_runners gr ON grn.graph_runner_id = gr.id
            JOIN staging.project_env_binding peb ON gr.id = peb.graph_runner_id
            JOIN staging.projects p ON peb.project_id = p.id
            WHERE p.organization_id = %s
        """,
        "project_env_binding": """
            INSERT INTO project_env_binding (id, project_id, environment, graph_runner_id, created_at, updated_at)
            SELECT peb.id, peb.project_id, peb.environment, peb.graph_runner_id, peb.created_at, peb.updated_at
            FROM staging.project_env_binding peb
            JOIN staging.projects p ON peb.project_id = p.id
            WHERE p.organization_id = %s
        """,
    }

    # Step 4: Copy Graph Structure
    GRAPH_STRUCTURE_QUERIES = {
        "graph_runner_nodes": """
            INSERT INTO graph_runner_nodes (id, node_id, graph_runner_id, node_type, is_start_node, created_at, updated_at)
            SELECT grn.id, grn.node_id, grn.graph_runner_id, grn.node_type, grn.is_start_node, grn.created_at, grn.updated_at
            FROM staging.graph_runner_nodes grn
            JOIN staging.graph_runners gr ON grn.graph_runner_id = gr.id
            JOIN staging.project_env_binding peb ON gr.id = peb.graph_runner_id
            JOIN staging.projects p ON peb.project_id = p.id
            WHERE p.organization_id = %s
        """,
        "graph_runner_edges": """
            INSERT INTO graph_runner_edges (id, source_node_id, target_node_id, graph_runner_id, "order", created_at, updated_at)
            SELECT gre.id, gre.source_node_id, gre.target_node_id, gre.graph_runner_id, gre."order", gre.created_at, gre.updated_at
            FROM staging.graph_runner_edges gre
            JOIN staging.graph_runners gr ON gre.graph_runner_id = gr.id
            JOIN staging.project_env_binding peb ON gr.id = peb.graph_runner_id
            JOIN staging.projects p ON peb.project_id = p.id
            WHERE p.organization_id = %s
        """,
    }

    # Step 5: Copy Configuration Data
    CONFIGURATION_QUERIES = {
        "basic_parameters": """
            INSERT INTO basic_parameters (id, component_instance_id, parameter_definition_id, value, organization_secret_id, "order")
            SELECT bp.id, bp.component_instance_id, bp.parameter_definition_id, bp.value, bp.organization_secret_id, bp."order"
            FROM staging.basic_parameters bp
            JOIN staging.component_instances ci ON bp.component_instance_id = ci.id
            JOIN staging.graph_runner_nodes grn ON ci.id = grn.node_id
            JOIN staging.graph_runners gr ON grn.graph_runner_id = gr.id
            JOIN staging.project_env_binding peb ON gr.id = peb.graph_runner_id
            JOIN staging.projects p ON peb.project_id = p.id
            WHERE p.organization_id = %s
        """,
        "port_mappings": """
            INSERT INTO port_mappings (id, graph_runner_id, source_instance_id, source_port_definition_id, target_instance_id, target_port_definition_id, dispatch_strategy)
            SELECT pm.id, pm.graph_runner_id, pm.source_instance_id, pm.source_port_definition_id, pm.target_instance_id, pm.target_port_definition_id, pm.dispatch_strategy
            FROM staging.port_mappings pm
            JOIN staging.graph_runners gr ON pm.graph_runner_id = gr.id
            JOIN staging.project_env_binding peb ON gr.id = peb.graph_runner_id
            JOIN staging.projects p ON peb.project_id = p.id
            WHERE p.organization_id = %s
        """,
        "component_sub_inputs": """
            INSERT INTO component_sub_inputs (id, parent_component_instance_id, child_component_instance_id, parameter_definition_id, "order")
            SELECT csi.id, csi.parent_component_instance_id, csi.child_component_instance_id, csi.parameter_definition_id, csi."order"
            FROM staging.component_sub_inputs csi
            JOIN staging.component_instances ci ON csi.parent_component_instance_id = ci.id
            JOIN staging.graph_runner_nodes grn ON ci.id = grn.node_id
            JOIN staging.graph_runners gr ON grn.graph_runner_id = gr.id
            JOIN staging.project_env_binding peb ON gr.id = peb.graph_runner_id
            JOIN staging.projects p ON peb.project_id = p.id
            WHERE p.organization_id = %s
        """,
    }

    # =============================================================================
    # VALIDATION QUERIES
    # =============================================================================

    VALIDATION_QUERIES = {
        "project_count": """
            SELECT COUNT(*) as project_count FROM projects WHERE organization_id = %s
        """,
        "polymorphic_records": """
            SELECT
                p.type,
                COUNT(*) as count
            FROM projects p
            LEFT JOIN workflow_projects wp ON p.id = wp.id AND p.type = 'workflow'
            LEFT JOIN agent_projects ap ON p.id = ap.id AND p.type = 'agent'
            WHERE p.organization_id = %s
            GROUP BY p.type
        """,
        "environment_bindings": """
            SELECT
                p.name,
                peb.environment,
                peb.graph_runner_id
            FROM projects p
            JOIN project_env_binding peb ON p.id = peb.project_id
            WHERE p.organization_id = %s
            ORDER BY p.name, peb.environment
        """,
        "graph_structure": """
            SELECT
                p.name,
                peb.environment,
                COUNT(grn.id) as node_count,
                COUNT(gre.id) as edge_count
            FROM projects p
            JOIN project_env_binding peb ON p.id = peb.project_id
            JOIN graph_runners gr ON peb.graph_runner_id = gr.id
            LEFT JOIN graph_runner_nodes grn ON gr.id = grn.graph_runner_id
            LEFT JOIN graph_runner_edges gre ON gr.id = gre.graph_runner_id
            WHERE p.organization_id = %s
            GROUP BY p.name, peb.environment, peb.graph_runner_id
            ORDER BY p.name, peb.environment
        """,
        "component_instances_count": """
            SELECT COUNT(*) as instance_count
            FROM component_instances ci
            JOIN graph_runner_nodes grn ON ci.id = grn.node_id
            JOIN graph_runners gr ON grn.graph_runner_id = gr.id
            JOIN project_env_binding peb ON gr.id = peb.graph_runner_id
            JOIN projects p ON peb.project_id = p.id
            WHERE p.organization_id = %s
        """,
        "foreign_key_integrity": """
            SELECT 
                'projects' as table_name,
                COUNT(*) as total_records,
                COUNT(CASE WHEN organization_id = %s THEN 1 END) as org_records
            FROM projects
            UNION ALL
            SELECT 
                'workflow_projects' as table_name,
                COUNT(*) as total_records,
                COUNT(CASE WHEN id IN (SELECT id FROM projects WHERE organization_id = %s) THEN 1 END) as org_records
            FROM workflow_projects
            UNION ALL
            SELECT 
                'agent_projects' as table_name,
                COUNT(*) as total_records,
                COUNT(CASE WHEN id IN (SELECT id FROM projects WHERE organization_id = %s) THEN 1 END) as org_records
            FROM agent_projects
        """,
    }

    # =============================================================================
    # STAGING VALIDATION QUERIES
    # =============================================================================

    STAGING_VALIDATION_QUERIES = {
        "source_project_count": """
            SELECT COUNT(*) as project_count FROM projects WHERE organization_id = %s
        """,
        "source_projects_detail": """
            SELECT 
                p.id,
                p.name,
                p.type,
                p.description,
                COUNT(peb.id) as binding_count
            FROM projects p
            LEFT JOIN project_env_binding peb ON p.id = peb.project_id
            WHERE p.organization_id = %s
            GROUP BY p.id, p.name, p.type, p.description
            ORDER BY p.name
        """,
        "source_graph_runners": """
            SELECT COUNT(DISTINCT gr.id) as graph_runner_count
            FROM graph_runners gr
            JOIN project_env_binding peb ON gr.id = peb.graph_runner_id
            JOIN projects p ON peb.project_id = p.id
            WHERE p.organization_id = %s
        """,
        "source_component_instances": """
            SELECT COUNT(DISTINCT ci.id) as component_instance_count
            FROM component_instances ci
            JOIN graph_runner_nodes grn ON ci.id = grn.node_id
            JOIN graph_runners gr ON grn.graph_runner_id = gr.id
            JOIN project_env_binding peb ON gr.id = peb.graph_runner_id
            JOIN projects p ON peb.project_id = p.id
            WHERE p.organization_id = %s
        """,
    }

    # =============================================================================
    # UTILITY METHODS
    # =============================================================================

    @staticmethod
    def get_cleanup_order() -> List[str]:
        """Get the order for cleanup queries (reverse of insertion order)."""
        return [
            "component_sub_inputs",
            "port_mappings",
            "basic_parameters",
            "graph_runner_edges",
            "graph_runner_nodes",
            "project_env_binding",
            "workflow_projects",
            "agent_projects",
            "component_instances",
            "graph_runners",
            "projects",
        ]

    @staticmethod
    def get_migration_order() -> List[str]:
        """Get the order for migration queries."""
        return [
            "projects",
            "workflow_projects",
            "agent_projects",
            "graph_runners",
            "component_instances",
            "project_env_binding",
            "graph_runner_nodes",
            "graph_runner_edges",
            "basic_parameters",
            "port_mappings",
            "component_sub_inputs",
        ]

    @staticmethod
    def get_validation_order() -> List[str]:
        """Get the order for validation queries."""
        return [
            "project_count",
            "polymorphic_records",
            "environment_bindings",
            "graph_structure",
            "component_instances_count",
            "foreign_key_integrity",
        ]

    @staticmethod
    def get_staging_validation_order() -> List[str]:
        """Get the order for staging validation queries."""
        return ["source_project_count", "source_projects_detail", "source_graph_runners", "source_component_instances"]

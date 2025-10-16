"""
Validation module for QA project migration.

Provides comprehensive validation checks for data integrity between staging and preprod.
"""

import logging
from typing import Dict, List, Tuple, Any, Optional
from migration_db_connection import DatabaseConnectionManager
from migration_queries import MigrationQueries, TARGET_ORG_ID

logger = logging.getLogger(__name__)

class MigrationValidator:
    """Validates QA project migration data integrity."""
    
    def __init__(self, db_manager: DatabaseConnectionManager):
        self.db_manager = db_manager
        self.org_id = TARGET_ORG_ID
        self.validation_results = {}
    
    def validate_staging_source(self) -> Dict[str, Any]:
        """Validate that source data exists in staging."""
        logger.info("Validating staging source data...")
        results = {}
        
        try:
            # Check project count
            project_count = self.db_manager.execute_staging_query(
                MigrationQueries.STAGING_VALIDATION_QUERIES['source_project_count'],
                (self.org_id,)
            )[0]['project_count']
            results['project_count'] = project_count
            
            # Get project details
            project_details = self.db_manager.execute_staging_query(
                MigrationQueries.STAGING_VALIDATION_QUERIES['source_projects_detail'],
                (self.org_id,)
            )
            results['project_details'] = project_details
            
            # Check graph runners
            graph_runner_count = self.db_manager.execute_staging_query(
                MigrationQueries.STAGING_VALIDATION_QUERIES['source_graph_runners'],
                (self.org_id,)
            )[0]['graph_runner_count']
            results['graph_runner_count'] = graph_runner_count
            
            # Check component instances
            component_instance_count = self.db_manager.execute_staging_query(
                MigrationQueries.STAGING_VALIDATION_QUERIES['source_component_instances'],
                (self.org_id,)
            )[0]['component_instance_count']
            results['component_instance_count'] = component_instance_count
            
            logger.info(f"Staging validation complete: {project_count} projects, {graph_runner_count} graph runners, {component_instance_count} component instances")
            
        except Exception as e:
            logger.error(f"Staging validation failed: {e}")
            results['error'] = str(e)
        
        self.validation_results['staging'] = results
        return results
    
    def validate_preprod_migration(self) -> Dict[str, Any]:
        """Validate that migration was successful in preprod."""
        logger.info("Validating preprod migration data...")
        results = {}
        
        try:
            # Validate project count
            project_count_result = self.db_manager.execute_preprod_query(
                MigrationQueries.VALIDATION_QUERIES['project_count'],
                (self.org_id,)
            )
            results['project_count'] = project_count_result[0]['project_count']
            
            # Validate polymorphic records
            polymorphic_result = self.db_manager.execute_preprod_query(
                MigrationQueries.VALIDATION_QUERIES['polymorphic_records'],
                (self.org_id,)
            )
            results['polymorphic_records'] = polymorphic_result
            
            # Validate environment bindings
            env_bindings = self.db_manager.execute_preprod_query(
                MigrationQueries.VALIDATION_QUERIES['environment_bindings'],
                (self.org_id,)
            )
            results['environment_bindings'] = env_bindings
            
            # Validate graph structure
            graph_structure = self.db_manager.execute_preprod_query(
                MigrationQueries.VALIDATION_QUERIES['graph_structure'],
                (self.org_id,)
            )
            results['graph_structure'] = graph_structure
            
            # Validate component instances
            component_instances = self.db_manager.execute_preprod_query(
                MigrationQueries.VALIDATION_QUERIES['component_instances_count'],
                (self.org_id,)
            )
            results['component_instances_count'] = component_instances[0]['instance_count']
            
            # Validate foreign key integrity
            fk_integrity = self.db_manager.execute_preprod_query(
                MigrationQueries.VALIDATION_QUERIES['foreign_key_integrity'],
                (self.org_id, self.org_id, self.org_id)
            )
            results['foreign_key_integrity'] = fk_integrity
            
            logger.info(f"Preprod validation complete: {results['project_count']} projects migrated")
            
        except Exception as e:
            logger.error(f"Preprod validation failed: {e}")
            results['error'] = str(e)
        
        self.validation_results['preprod'] = results
        return results
    
    def compare_staging_preprod(self) -> Dict[str, Any]:
        """Compare data between staging and preprod to ensure migration completeness."""
        logger.info("Comparing staging and preprod data...")
        
        staging_data = self.validation_results.get('staging', {})
        preprod_data = self.validation_results.get('preprod', {})
        
        comparison = {
            'project_count_match': staging_data.get('project_count') == preprod_data.get('project_count'),
            'graph_runner_count_match': staging_data.get('graph_runner_count') == len(preprod_data.get('graph_structure', [])),
            'component_instance_count_match': staging_data.get('component_instance_count') == preprod_data.get('component_instances_count'),
            'staging_project_count': staging_data.get('project_count', 0),
            'preprod_project_count': preprod_data.get('project_count', 0),
            'staging_graph_runners': staging_data.get('graph_runner_count', 0),
            'preprod_graph_runners': len(preprod_data.get('graph_structure', [])),
            'staging_component_instances': staging_data.get('component_instance_count', 0),
            'preprod_component_instances': preprod_data.get('component_instances_count', 0)
        }
        
        # Check if all counts match
        comparison['all_counts_match'] = all([
            comparison['project_count_match'],
            comparison['graph_runner_count_match'],
            comparison['component_instance_count_match']
        ])
        
        self.validation_results['comparison'] = comparison
        return comparison
    
    def validate_polymorphic_inheritance(self) -> bool:
        """Validate that polymorphic inheritance is working correctly."""
        logger.info("Validating polymorphic inheritance...")
        
        try:
            polymorphic_data = self.db_manager.execute_preprod_query(
                MigrationQueries.VALIDATION_QUERIES['polymorphic_records'],
                (self.org_id,)
            )
            
            # Check that each project type has corresponding polymorphic records
            for record in polymorphic_data:
                project_type = record['type']
                count = record['count']
                
                if project_type == 'workflow' and count == 0:
                    logger.error("No workflow_projects records found for workflow projects")
                    return False
                elif project_type == 'agent' and count == 0:
                    logger.error("No agent_projects records found for agent projects")
                    return False
            
            logger.info("Polymorphic inheritance validation passed")
            return True
            
        except Exception as e:
            logger.error(f"Polymorphic inheritance validation failed: {e}")
            return False
    
    def validate_environment_bindings(self) -> bool:
        """Validate that environment bindings exist for all projects."""
        logger.info("Validating environment bindings...")
        
        try:
            env_bindings = self.db_manager.execute_preprod_query(
                MigrationQueries.VALIDATION_QUERIES['environment_bindings'],
                (self.org_id,)
            )
            
            if not env_bindings:
                logger.error("No environment bindings found")
                return False
            
            # Check that each project has both draft and production bindings
            project_bindings = {}
            for binding in env_bindings:
                project_name = binding['name']
                environment = binding['environment']
                
                if project_name not in project_bindings:
                    project_bindings[project_name] = set()
                project_bindings[project_name].add(environment)
            
            # Validate each project has both environments
            for project_name, environments in project_bindings.items():
                if 'draft' not in environments or 'production' not in environments:
                    logger.error(f"Project {project_name} missing environment bindings: {environments}")
                    return False
            
            logger.info(f"Environment bindings validation passed for {len(project_bindings)} projects")
            return True
            
        except Exception as e:
            logger.error(f"Environment bindings validation failed: {e}")
            return False
    
    def validate_graph_structure(self) -> bool:
        """Validate that graph structure is complete."""
        logger.info("Validating graph structure...")
        
        try:
            graph_structure = self.db_manager.execute_preprod_query(
                MigrationQueries.VALIDATION_QUERIES['graph_structure'],
                (self.org_id,)
            )
            
            if not graph_structure:
                logger.error("No graph structure found")
                return False
            
            # Check that each graph has nodes and edges
            for graph in graph_structure:
                node_count = graph['node_count']
                edge_count = graph['edge_count']
                
                if node_count == 0:
                    logger.error(f"Graph {graph['name']} ({graph['environment']}) has no nodes")
                    return False
                
                # Edges can be 0 for single-node graphs, but should be validated
                logger.info(f"Graph {graph['name']} ({graph['environment']}): {node_count} nodes, {edge_count} edges")
            
            logger.info("Graph structure validation passed")
            return True
            
        except Exception as e:
            logger.error(f"Graph structure validation failed: {e}")
            return False
    
    def validate_foreign_key_integrity(self) -> bool:
        """Validate that all foreign key relationships are intact."""
        logger.info("Validating foreign key integrity...")
        
        try:
            fk_data = self.db_manager.execute_preprod_query(
                MigrationQueries.VALIDATION_QUERIES['foreign_key_integrity'],
                (self.org_id, self.org_id, self.org_id)
            )
            
            for record in fk_data:
                table_name = record['table_name']
                total_records = record['total_records']
                org_records = record['org_records']
                
                if org_records == 0 and table_name in ['workflow_projects', 'agent_projects']:
                    logger.error(f"No {table_name} records found for organization")
                    return False
                
                logger.info(f"{table_name}: {org_records} records for organization (total: {total_records})")
            
            logger.info("Foreign key integrity validation passed")
            return True
            
        except Exception as e:
            logger.error(f"Foreign key integrity validation failed: {e}")
            return False
    
    def run_comprehensive_validation(self) -> Dict[str, Any]:
        """Run all validation checks and return comprehensive results."""
        logger.info("Running comprehensive validation...")
        
        results = {
            'staging_validation': self.validate_staging_source(),
            'preprod_validation': self.validate_preprod_migration(),
            'comparison': self.compare_staging_preprod(),
            'polymorphic_inheritance': self.validate_polymorphic_inheritance(),
            'environment_bindings': self.validate_environment_bindings(),
            'graph_structure': self.validate_graph_structure(),
            'foreign_key_integrity': self.validate_foreign_key_integrity()
        }
        
        # Overall success
        results['overall_success'] = all([
            results['comparison'].get('all_counts_match', False),
            results['polymorphic_inheritance'],
            results['environment_bindings'],
            results['graph_structure'],
            results['foreign_key_integrity']
        ])
        
        logger.info(f"Comprehensive validation complete. Overall success: {results['overall_success']}")
        return results
    
    def print_validation_summary(self, results: Dict[str, Any]):
        """Print a summary of validation results."""
        print("\n" + "="*80)
        print("QA MIGRATION VALIDATION SUMMARY")
        print("="*80)
        
        # Staging data
        staging = results.get('staging_validation', {})
        print(f"\nSTAGING SOURCE DATA:")
        print(f"  Projects: {staging.get('project_count', 0)}")
        print(f"  Graph Runners: {staging.get('graph_runner_count', 0)}")
        print(f"  Component Instances: {staging.get('component_instance_count', 0)}")
        
        # Preprod data
        preprod = results.get('preprod_validation', {})
        print(f"\nPREPROD MIGRATED DATA:")
        print(f"  Projects: {preprod.get('project_count', 0)}")
        print(f"  Component Instances: {preprod.get('component_instances_count', 0)}")
        
        # Comparison
        comparison = results.get('comparison', {})
        print(f"\nDATA COMPARISON:")
        print(f"  Project Count Match: {comparison.get('project_count_match', False)}")
        print(f"  Graph Runner Count Match: {comparison.get('graph_runner_count_match', False)}")
        print(f"  Component Instance Count Match: {comparison.get('component_instance_count_match', False)}")
        
        # Validation checks
        print(f"\nVALIDATION CHECKS:")
        print(f"  Polymorphic Inheritance: {results.get('polymorphic_inheritance', False)}")
        print(f"  Environment Bindings: {results.get('environment_bindings', False)}")
        print(f"  Graph Structure: {results.get('graph_structure', False)}")
        print(f"  Foreign Key Integrity: {results.get('foreign_key_integrity', False)}")
        
        # Overall result
        overall_success = results.get('overall_success', False)
        print(f"\nOVERALL RESULT: {'✅ SUCCESS' if overall_success else '❌ FAILED'}")
        print("="*80)
        
        return overall_success

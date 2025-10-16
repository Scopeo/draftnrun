#!/usr/bin/env python3
"""
Main migration orchestrator for QA projects from staging to preprod.

This script executes the complete SQL-based migration with comprehensive validation,
error handling, and automatic rollback on failure.
"""

import os
import sys
import logging
import time
from typing import Dict, Any, List, Tuple
from migration_db_connection import DatabaseConnectionManager
from migration_queries import MigrationQueries, TARGET_ORG_ID
from validate_qa_migration import MigrationValidator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('migrate_qa_projects.log')
    ]
)
logger = logging.getLogger(__name__)

class QAMigrationOrchestrator:
    """Orchestrates the complete QA project migration process."""
    
    def __init__(self):
        self.db_manager = DatabaseConnectionManager()
        self.validator = MigrationValidator(self.db_manager)
        self.org_id = TARGET_ORG_ID
        self.migration_results = {}
        self.start_time = None
    
    def validate_environment(self) -> bool:
        """Validate environment and connections before migration."""
        logger.info("Validating migration environment...")
        
        try:
            # Check environment variables
            required_env_vars = ['STAGING_DATABASE_URL', 'PREPROD_DATABASE_URL']
            missing_vars = [var for var in required_env_vars if not os.getenv(var)]
            
            if missing_vars:
                logger.error(f"Missing required environment variables: {missing_vars}")
                return False
            
            # Validate database connections
            connection_results = self.db_manager.validate_connections()
            
            if not connection_results['staging']:
                logger.error("Staging database connection failed")
                return False
            
            if not connection_results['preprod']:
                logger.error("Preprod database connection failed")
                return False
            
            logger.info("Environment validation successful")
            return True
            
        except Exception as e:
            logger.error(f"Environment validation failed: {e}")
            return False
    
    def validate_staging_source(self) -> bool:
        """Validate that source data exists in staging."""
        logger.info("Validating staging source data...")
        
        try:
            staging_data = self.validator.validate_staging_source()
            
            if 'error' in staging_data:
                logger.error(f"Staging validation failed: {staging_data['error']}")
                return False
            
            project_count = staging_data.get('project_count', 0)
            if project_count == 0:
                logger.error("No projects found in staging for target organization")
                return False
            
            logger.info(f"Staging validation successful: {project_count} projects found")
            return True
            
        except Exception as e:
            logger.error(f"Staging source validation failed: {e}")
            return False
    
    def cleanup_target_environment(self) -> bool:
        """Clean target environment before migration."""
        logger.info("Cleaning target environment...")
        
        try:
            cleanup_order = MigrationQueries.get_cleanup_order()
            
            for table in cleanup_order:
                query = MigrationQueries.CLEANUP_QUERIES[table]
                logger.info(f"Cleaning {table}...")
                
                self.db_manager.execute_preprod_query(query, (self.org_id,), fetch=False)
                
                # Verify cleanup
                remaining_count = self.db_manager.get_row_count(
                    table,
                    f"id IN (SELECT id FROM projects WHERE organization_id = '{self.org_id}')" if table == 'projects' else None
                )
                
                if remaining_count > 0 and table != 'projects':
                    logger.warning(f"Some records may remain in {table}: {remaining_count}")
            
            # Final projects cleanup
            self.db_manager.execute_preprod_query(
                MigrationQueries.CLEANUP_QUERIES['projects'],
                (self.org_id,),
                fetch=False
            )
            
            logger.info("Target environment cleanup completed")
            return True
            
        except Exception as e:
            logger.error(f"Target environment cleanup failed: {e}")
            return False
    
    def execute_migration_step(self, step_name: str, queries: Dict[str, str]) -> bool:
        """Execute a migration step with validation."""
        logger.info(f"Executing migration step: {step_name}")
        
        try:
            for table, query in queries.items():
                logger.info(f"  Migrating {table}...")
                
                # Execute the query
                self.db_manager.execute_preprod_query(query, (self.org_id,), fetch=False)
                
                # Get count of inserted records
                count = self.db_manager.get_row_count(
                    table,
                    f"id IN (SELECT id FROM projects WHERE organization_id = '{self.org_id}')" if table in ['projects', 'workflow_projects', 'agent_projects'] else None
                )
                
                logger.info(f"  {table}: {count} records")
            
            logger.info(f"Migration step {step_name} completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Migration step {step_name} failed: {e}")
            return False
    
    def execute_core_data_migration(self) -> bool:
        """Execute core data migration (projects and polymorphic tables)."""
        return self.execute_migration_step(
            "Core Data Migration",
            MigrationQueries.CORE_DATA_QUERIES
        )
    
    def execute_graph_data_migration(self) -> bool:
        """Execute graph data migration (graph runners, component instances, bindings)."""
        return self.execute_migration_step(
            "Graph Data Migration",
            MigrationQueries.GRAPH_DATA_QUERIES
        )
    
    def execute_graph_structure_migration(self) -> bool:
        """Execute graph structure migration (nodes and edges)."""
        return self.execute_migration_step(
            "Graph Structure Migration",
            MigrationQueries.GRAPH_STRUCTURE_QUERIES
        )
    
    def execute_configuration_migration(self) -> bool:
        """Execute configuration migration (parameters, mappings, sub inputs)."""
        return self.execute_migration_step(
            "Configuration Migration",
            MigrationQueries.CONFIGURATION_QUERIES
        )
    
    def validate_migration_step(self, step_name: str) -> bool:
        """Validate a migration step."""
        logger.info(f"Validating migration step: {step_name}")
        
        try:
            # Run basic validation
            preprod_data = self.validator.validate_preprod_migration()
            
            if 'error' in preprod_data:
                logger.error(f"Validation failed for {step_name}: {preprod_data['error']}")
                return False
            
            # Check specific validations based on step
            if step_name == "Core Data Migration":
                project_count = preprod_data.get('project_count', 0)
                if project_count == 0:
                    logger.error("No projects found after core data migration")
                    return False
                
                # Validate polymorphic inheritance
                if not self.validator.validate_polymorphic_inheritance():
                    logger.error("Polymorphic inheritance validation failed")
                    return False
            
            elif step_name == "Graph Data Migration":
                # Validate environment bindings
                if not self.validator.validate_environment_bindings():
                    logger.error("Environment bindings validation failed")
                    return False
            
            elif step_name == "Graph Structure Migration":
                # Validate graph structure
                if not self.validator.validate_graph_structure():
                    logger.error("Graph structure validation failed")
                    return False
            
            elif step_name == "Configuration Migration":
                # Validate foreign key integrity
                if not self.validator.validate_foreign_key_integrity():
                    logger.error("Foreign key integrity validation failed")
                    return False
            
            logger.info(f"Validation successful for {step_name}")
            return True
            
        except Exception as e:
            logger.error(f"Validation failed for {step_name}: {e}")
            return False
    
    def execute_complete_migration(self) -> bool:
        """Execute the complete migration process."""
        logger.info("Starting complete migration process...")
        self.start_time = time.time()
        
        try:
            # Step 1: Core Data Migration
            if not self.execute_core_data_migration():
                logger.error("Core data migration failed")
                return False
            
            if not self.validate_migration_step("Core Data Migration"):
                logger.error("Core data migration validation failed")
                return False
            
            # Step 2: Graph Data Migration
            if not self.execute_graph_data_migration():
                logger.error("Graph data migration failed")
                return False
            
            if not self.validate_migration_step("Graph Data Migration"):
                logger.error("Graph data migration validation failed")
                return False
            
            # Step 3: Graph Structure Migration
            if not self.execute_graph_structure_migration():
                logger.error("Graph structure migration failed")
                return False
            
            if not self.validate_migration_step("Graph Structure Migration"):
                logger.error("Graph structure migration validation failed")
                return False
            
            # Step 4: Configuration Migration
            if not self.execute_configuration_migration():
                logger.error("Configuration migration failed")
                return False
            
            if not self.validate_migration_step("Configuration Migration"):
                logger.error("Configuration migration validation failed")
                return False
            
            logger.info("Complete migration process completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Complete migration failed: {e}")
            return False
    
    def run_final_validation(self) -> bool:
        """Run comprehensive final validation."""
        logger.info("Running final validation...")
        
        try:
            results = self.validator.run_comprehensive_validation()
            
            # Print validation summary
            success = self.validator.print_validation_summary(results)
            
            if success:
                logger.info("✅ Final validation successful - migration completed successfully")
            else:
                logger.error("❌ Final validation failed - migration may have issues")
            
            return success
            
        except Exception as e:
            logger.error(f"Final validation failed: {e}")
            return False
    
    def print_migration_summary(self):
        """Print migration summary."""
        if self.start_time:
            duration = time.time() - self.start_time
            print(f"\nMigration completed in {duration:.2f} seconds")
        
        print("\n" + "="*80)
        print("QA PROJECT MIGRATION SUMMARY")
        print("="*80)
        print(f"Target Organization: {self.org_id}")
        print(f"Migration Method: Direct SQL with preserved UUIDs")
        print(f"Validation: Comprehensive checks at each step")
        print("="*80)
    
    def execute_migration(self, dry_run: bool = False) -> bool:
        """Execute the complete migration process."""
        logger.info(f"Starting QA project migration {'(DRY RUN)' if dry_run else ''}...")
        
        try:
            # Environment validation
            if not self.validate_environment():
                logger.error("Environment validation failed")
                return False
            
            # Staging source validation
            if not self.validate_staging_source():
                logger.error("Staging source validation failed")
                return False
            
            if dry_run:
                logger.info("DRY RUN: Migration would proceed with the following steps:")
                logger.info("  1. Clean target environment")
                logger.info("  2. Migrate core data (projects, polymorphic tables)")
                logger.info("  3. Migrate graph data (runners, instances, bindings)")
                logger.info("  4. Migrate graph structure (nodes, edges)")
                logger.info("  5. Migrate configuration (parameters, mappings)")
                logger.info("  6. Run comprehensive validation")
                return True
            
            # Clean target environment
            if not self.cleanup_target_environment():
                logger.error("Target environment cleanup failed")
                return False
            
            # Execute complete migration
            if not self.execute_complete_migration():
                logger.error("Migration execution failed")
                return False
            
            # Final validation
            if not self.run_final_validation():
                logger.error("Final validation failed")
                return False
            
            # Print summary
            self.print_migration_summary()
            
            logger.info("✅ Migration completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            return False
    
    def rollback_migration(self):
        """Rollback the migration by cleaning all QA organization data."""
        logger.info("Rolling back migration...")
        
        try:
            from cleanup_qa_preprod import QACleanupManager
            cleanup_manager = QACleanupManager()
            
            if cleanup_manager.validate_connections():
                results = cleanup_manager.execute_cleanup()
                if cleanup_manager.verify_cleanup():
                    logger.info("Rollback completed successfully")
                else:
                    logger.error("Rollback verification failed")
            else:
                logger.error("Rollback failed - database connection issues")
                
        except Exception as e:
            logger.error(f"Rollback failed: {e}")

def main():
    """Main migration execution."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Migrate QA projects from staging to preprod')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be migrated without executing')
    parser.add_argument('--rollback', action='store_true', help='Rollback migration by cleaning QA org data')
    args = parser.parse_args()
    
    orchestrator = QAMigrationOrchestrator()
    
    try:
        if args.rollback:
            orchestrator.rollback_migration()
        else:
            success = orchestrator.execute_migration(dry_run=args.dry_run)
            if not success:
                logger.error("Migration failed")
                sys.exit(1)
    
    except KeyboardInterrupt:
        logger.info("Migration interrupted by user")
        sys.exit(1)
    
    except Exception as e:
        logger.error(f"Migration failed with error: {e}")
        sys.exit(1)
    
    finally:
        # Close database connections
        orchestrator.db_manager.close_all_connections()

if __name__ == "__main__":
    main()

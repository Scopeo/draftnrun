#!/usr/bin/env python3
"""
Cleanup script for QA organization data in preprod.

This script deletes all data for the target QA organization from preprod database.
Can be used for rollback or to clean the environment before migration.
"""

import os
import sys
import logging
from typing import Dict, Any
from migration_db_connection import DatabaseConnectionManager
from migration_queries import MigrationQueries, TARGET_ORG_ID

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('cleanup_qa_preprod.log')
    ]
)
logger = logging.getLogger(__name__)

class QACleanupManager:
    """Manages cleanup of QA organization data from preprod."""
    
    def __init__(self):
        self.db_manager = DatabaseConnectionManager()
        self.org_id = TARGET_ORG_ID
        self.cleanup_results = {}
    
    def validate_connections(self) -> bool:
        """Validate database connections before cleanup."""
        logger.info("Validating database connections...")
        
        try:
            results = self.db_manager.validate_connections()
            
            if not results['preprod']:
                logger.error("Preprod database connection failed")
                return False
            
            logger.info("Database connections validated successfully")
            return True
            
        except Exception as e:
            logger.error(f"Connection validation failed: {e}")
            return False
    
    def get_current_data_counts(self) -> Dict[str, int]:
        """Get current data counts for the target organization."""
        logger.info("Getting current data counts...")
        
        counts = {}
        
        try:
            # Get project count
            project_count = self.db_manager.get_row_count(
                'projects', 
                'organization_id = %s', 
                (self.org_id,)
            )
            counts['projects'] = project_count
            
            # Get workflow projects count
            workflow_count = self.db_manager.execute_preprod_query(
                "SELECT COUNT(*) as count FROM workflow_projects wp JOIN projects p ON wp.id = p.id WHERE p.organization_id = %s",
                (self.org_id,)
            )[0]['count']
            counts['workflow_projects'] = workflow_count
            
            # Get agent projects count
            agent_count = self.db_manager.execute_preprod_query(
                "SELECT COUNT(*) as count FROM agent_projects ap JOIN projects p ON ap.id = p.id WHERE p.organization_id = %s",
                (self.org_id,)
            )[0]['count']
            counts['agent_projects'] = agent_count
            
            # Get environment bindings count
            binding_count = self.db_manager.execute_preprod_query(
                "SELECT COUNT(*) as count FROM project_env_binding peb JOIN projects p ON peb.project_id = p.id WHERE p.organization_id = %s",
                (self.org_id,)
            )[0]['count']
            counts['project_env_binding'] = binding_count
            
            # Get graph runners count
            graph_runner_count = self.db_manager.execute_preprod_query(
                """SELECT COUNT(*) as count FROM graph_runners gr 
                   JOIN project_env_binding peb ON gr.id = peb.graph_runner_id 
                   JOIN projects p ON peb.project_id = p.id 
                   WHERE p.organization_id = %s""",
                (self.org_id,)
            )[0]['count']
            counts['graph_runners'] = graph_runner_count
            
            # Get component instances count
            component_instance_count = self.db_manager.execute_preprod_query(
                """SELECT COUNT(*) as count FROM component_instances ci 
                   JOIN graph_runner_nodes grn ON ci.id = grn.node_id 
                   JOIN graph_runners gr ON grn.graph_runner_id = gr.id 
                   JOIN project_env_binding peb ON gr.id = peb.graph_runner_id 
                   JOIN projects p ON peb.project_id = p.id 
                   WHERE p.organization_id = %s""",
                (self.org_id,)
            )[0]['count']
            counts['component_instances'] = component_instance_count
            
            logger.info(f"Current data counts: {counts}")
            
        except Exception as e:
            logger.error(f"Failed to get data counts: {e}")
            counts['error'] = str(e)
        
        return counts
    
    def execute_cleanup(self, dry_run: bool = False) -> Dict[str, Any]:
        """Execute cleanup of QA organization data."""
        logger.info(f"Starting cleanup {'(DRY RUN)' if dry_run else ''}...")
        
        results = {}
        cleanup_order = MigrationQueries.get_cleanup_order()
        
        try:
            for table in cleanup_order:
                query = MigrationQueries.CLEANUP_QUERIES[table]
                
                if dry_run:
                    logger.info(f"DRY RUN: Would delete from {table}")
                    results[table] = {'status': 'dry_run', 'rows_affected': 0}
                else:
                    logger.info(f"Deleting from {table}...")
                    
                    # Execute delete query
                    self.db_manager.execute_preprod_query(query, (self.org_id,), fetch=False)
                    
                    # Get count of affected rows (approximate)
                    remaining_count = self.db_manager.get_row_count(
                        table, 
                        f"id IN (SELECT id FROM projects WHERE organization_id = '{self.org_id}')" if table == 'projects' else None
                    )
                    
                    results[table] = {'status': 'completed', 'remaining_rows': remaining_count}
                    logger.info(f"Completed deletion from {table}")
            
            # Final cleanup for projects table
            if not dry_run:
                logger.info("Deleting from projects table...")
                self.db_manager.execute_preprod_query(
                    MigrationQueries.CLEANUP_QUERIES['projects'],
                    (self.org_id,),
                    fetch=False
                )
                results['projects'] = {'status': 'completed', 'remaining_rows': 0}
            
            logger.info("Cleanup completed successfully")
            
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
            results['error'] = str(e)
            raise
        
        return results
    
    def verify_cleanup(self) -> bool:
        """Verify that cleanup was successful."""
        logger.info("Verifying cleanup...")
        
        try:
            # Check if any projects remain for the organization
            remaining_projects = self.db_manager.get_row_count(
                'projects',
                'organization_id = %s',
                (self.org_id,)
            )
            
            if remaining_projects > 0:
                logger.error(f"Cleanup verification failed: {remaining_projects} projects still exist")
                return False
            
            # Check for any remaining related data
            remaining_bindings = self.db_manager.execute_preprod_query(
                "SELECT COUNT(*) as count FROM project_env_binding peb JOIN projects p ON peb.project_id = p.id WHERE p.organization_id = %s",
                (self.org_id,)
            )[0]['count']
            
            if remaining_bindings > 0:
                logger.error(f"Cleanup verification failed: {remaining_bindings} environment bindings still exist")
                return False
            
            logger.info("Cleanup verification successful - no QA organization data remains")
            return True
            
        except Exception as e:
            logger.error(f"Cleanup verification failed: {e}")
            return False
    
    def print_cleanup_summary(self, before_counts: Dict[str, int], results: Dict[str, Any]):
        """Print a summary of cleanup results."""
        print("\n" + "="*80)
        print("QA PREPROD CLEANUP SUMMARY")
        print("="*80)
        
        print(f"\nBEFORE CLEANUP:")
        for table, count in before_counts.items():
            print(f"  {table}: {count}")
        
        print(f"\nCLEANUP RESULTS:")
        for table, result in results.items():
            if table != 'error':
                status = result.get('status', 'unknown')
                remaining = result.get('remaining_rows', 0)
                print(f"  {table}: {status} (remaining: {remaining})")
        
        if 'error' in results:
            print(f"\nERROR: {results['error']}")
        
        print("="*80)

def main():
    """Main cleanup execution."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Cleanup QA organization data from preprod')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be deleted without executing')
    parser.add_argument('--verify-only', action='store_true', help='Only verify current state without cleanup')
    args = parser.parse_args()
    
    cleanup_manager = QACleanupManager()
    
    try:
        # Validate connections
        if not cleanup_manager.validate_connections():
            logger.error("Database connection validation failed")
            sys.exit(1)
        
        # Get current data counts
        before_counts = cleanup_manager.get_current_data_counts()
        
        if args.verify_only:
            logger.info("Verify-only mode: showing current data counts")
            cleanup_manager.print_cleanup_summary(before_counts, {})
            return
        
        # Execute cleanup
        results = cleanup_manager.execute_cleanup(dry_run=args.dry_run)
        
        # Print summary
        cleanup_manager.print_cleanup_summary(before_counts, results)
        
        if not args.dry_run:
            # Verify cleanup
            if cleanup_manager.verify_cleanup():
                logger.info("✅ Cleanup completed and verified successfully")
            else:
                logger.error("❌ Cleanup verification failed")
                sys.exit(1)
        
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")
        sys.exit(1)
    
    finally:
        # Close database connections
        cleanup_manager.db_manager.close_all_connections()

if __name__ == "__main__":
    main()

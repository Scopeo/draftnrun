#!/usr/bin/env python3
"""
Database Schema Comparison Script

This script compares the database schemas between staging and preprod environments
to identify differences that could explain the polymorphic inheritance issue.

Usage:
    python compare_database_schemas.py --staging-url <staging_db_url> --preprod-url <preprod_db_url>
"""

import argparse
import sys
from typing import Dict, List, Set, Tuple, Any
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import Engine
import json
from datetime import datetime


class DatabaseSchemaComparator:
    def __init__(self, staging_engine: Engine, preprod_engine: Engine):
        self.staging_engine = staging_engine
        self.preprod_engine = preprod_engine
        self.differences = []
        
    def compare_schemas(self) -> Dict[str, Any]:
        """Compare schemas between staging and preprod databases."""
        print("🔍 Starting database schema comparison...")
        
        comparison_results = {
            "timestamp": datetime.now().isoformat(),
            "tables": self._compare_tables(),
            "columns": self._compare_columns(),
            "indexes": self._compare_indexes(),
            "constraints": self._compare_constraints(),
            "enums": self._compare_enums(),
            "polymorphic_tables": self._analyze_polymorphic_tables(),
            "migration_status": self._check_migration_status(),
            "data_analysis": self._analyze_project_data()
        }
        
        return comparison_results
    
    def _compare_tables(self) -> Dict[str, Any]:
        """Compare table structures between databases."""
        print("📊 Comparing table structures...")
        
        staging_inspector = inspect(self.staging_engine)
        preprod_inspector = inspect(self.preprod_engine)
        
        staging_tables = set(staging_inspector.get_table_names())
        preprod_tables = set(preprod_inspector.get_table_names())
        
        return {
            "staging_only": list(staging_tables - preprod_tables),
            "preprod_only": list(preprod_tables - staging_tables),
            "common": list(staging_tables & preprod_tables),
            "staging_count": len(staging_tables),
            "preprod_count": len(preprod_tables)
        }
    
    def _compare_columns(self) -> Dict[str, Any]:
        """Compare column structures for common tables."""
        print("📋 Comparing column structures...")
        
        staging_inspector = inspect(self.staging_engine)
        preprod_inspector = inspect(self.preprod_engine)
        
        # Get common tables
        staging_tables = set(staging_inspector.get_table_names())
        preprod_tables = set(preprod_inspector.get_table_names())
        common_tables = staging_tables & preprod_tables
        
        column_differences = {}
        
        for table_name in common_tables:
            staging_columns = {col['name']: col for col in staging_inspector.get_columns(table_name)}
            preprod_columns = {col['name']: col for col in preprod_inspector.get_columns(table_name)}
            
            # Find differences
            staging_only = set(staging_columns.keys()) - set(preprod_columns.keys())
            preprod_only = set(preprod_columns.keys()) - set(staging_columns.keys())
            
            # Compare common columns
            common_cols = set(staging_columns.keys()) & set(preprod_columns.keys())
            type_differences = []
            
            for col_name in common_cols:
                staging_col = staging_columns[col_name]
                preprod_col = preprod_columns[col_name]
                
                if staging_col['type'] != preprod_col['type']:
                    type_differences.append({
                        'column': col_name,
                        'staging_type': str(staging_col['type']),
                        'preprod_type': str(preprod_col['type'])
                    })
            
            if staging_only or preprod_only or type_differences:
                column_differences[table_name] = {
                    'staging_only': list(staging_only),
                    'preprod_only': list(preprod_only),
                    'type_differences': type_differences
                }
        
        return column_differences
    
    def _compare_indexes(self) -> Dict[str, Any]:
        """Compare indexes between databases."""
        print("🔍 Comparing indexes...")
        
        staging_inspector = inspect(self.staging_engine)
        preprod_inspector = inspect(self.preprod_engine)
        
        # Focus on projects table and related polymorphic tables
        target_tables = ['projects', 'workflow_projects', 'agent_projects']
        
        index_differences = {}
        
        for table_name in target_tables:
            try:
                staging_indexes = staging_inspector.get_indexes(table_name)
                preprod_indexes = preprod_inspector.get_indexes(table_name)
                
                staging_index_names = {idx['name'] for idx in staging_indexes}
                preprod_index_names = {idx['name'] for idx in preprod_indexes}
                
                if staging_index_names != preprod_index_names:
                    index_differences[table_name] = {
                        'staging_indexes': [idx['name'] for idx in staging_indexes],
                        'preprod_indexes': [idx['name'] for idx in preprod_indexes],
                        'staging_only': list(staging_index_names - preprod_index_names),
                        'preprod_only': list(preprod_index_names - staging_index_names)
                    }
            except Exception as e:
                print(f"⚠️  Could not compare indexes for {table_name}: {e}")
        
        return index_differences
    
    def _compare_constraints(self) -> Dict[str, Any]:
        """Compare constraints between databases."""
        print("🔗 Comparing constraints...")
        
        staging_inspector = inspect(self.staging_engine)
        preprod_inspector = inspect(self.preprod_engine)
        
        target_tables = ['projects', 'workflow_projects', 'agent_projects']
        constraint_differences = {}
        
        for table_name in target_tables:
            try:
                staging_constraints = staging_inspector.get_foreign_keys(table_name)
                preprod_constraints = preprod_inspector.get_foreign_keys(table_name)
                
                if len(staging_constraints) != len(preprod_constraints):
                    constraint_differences[table_name] = {
                        'staging_count': len(staging_constraints),
                        'preprod_count': len(preprod_constraints),
                        'staging_constraints': staging_constraints,
                        'preprod_constraints': preprod_constraints
                    }
            except Exception as e:
                print(f"⚠️  Could not compare constraints for {table_name}: {e}")
        
        return constraint_differences
    
    def _compare_enums(self) -> Dict[str, Any]:
        """Compare enum types between databases."""
        print("📝 Comparing enum types...")
        
        # Check for project_type enum
        enum_queries = {
            'project_type_enum': """
                SELECT enumlabel 
                FROM pg_enum 
                WHERE enumtypid = (
                    SELECT oid 
                    FROM pg_type 
                    WHERE typname = 'project_type'
                )
                ORDER BY enumsortorder;
            """,
            'env_type_enum': """
                SELECT enumlabel 
                FROM pg_enum 
                WHERE enumtypid = (
                    SELECT oid 
                    FROM pg_type 
                    WHERE typname = 'env_type'
                )
                ORDER BY enumsortorder;
            """
        }
        
        enum_differences = {}
        
        for enum_name, query in enum_queries.items():
            try:
                with self.staging_engine.connect() as staging_conn:
                    staging_result = staging_conn.execute(text(query)).fetchall()
                    staging_values = [row[0] for row in staging_result]
                
                with self.preprod_engine.connect() as preprod_conn:
                    preprod_result = preprod_conn.execute(text(query)).fetchall()
                    preprod_values = [row[0] for row in preprod_result]
                
                if staging_values != preprod_values:
                    enum_differences[enum_name] = {
                        'staging_values': staging_values,
                        'preprod_values': preprod_values
                    }
            except Exception as e:
                print(f"⚠️  Could not compare enum {enum_name}: {e}")
        
        return enum_differences
    
    def _analyze_polymorphic_tables(self) -> Dict[str, Any]:
        """Analyze polymorphic table relationships and data."""
        print("🔍 Analyzing polymorphic table relationships...")
        
        analysis_queries = {
            'projects_data': """
                SELECT 
                    type,
                    COUNT(*) as count,
                    MIN(created_at) as earliest,
                    MAX(created_at) as latest
                FROM projects 
                GROUP BY type
                ORDER BY type;
            """,
            'workflow_projects_data': """
                SELECT COUNT(*) as count FROM workflow_projects;
            """,
            'agent_projects_data': """
                SELECT COUNT(*) as count FROM agent_projects;
            """,
            'polymorphic_consistency': """
                SELECT 
                    p.type,
                    CASE 
                        WHEN p.type = 'workflow' AND wp.id IS NOT NULL THEN 'consistent'
                        WHEN p.type = 'agent' AND ap.id IS NOT NULL THEN 'consistent'
                        ELSE 'inconsistent'
                    END as status,
                    COUNT(*) as count
                FROM projects p
                LEFT JOIN workflow_projects wp ON p.id = wp.id
                LEFT JOIN agent_projects ap ON p.id = ap.id
                GROUP BY p.type, status
                ORDER BY p.type, status;
            """
        }
        
        results = {}
        
        for query_name, query in analysis_queries.items():
            try:
                with self.staging_engine.connect() as staging_conn:
                    staging_result = staging_conn.execute(text(query)).fetchall()
                    staging_data = [dict(row._mapping) for row in staging_result]
                
                with self.preprod_engine.connect() as preprod_conn:
                    preprod_result = preprod_conn.execute(text(query)).fetchall()
                    preprod_data = [dict(row._mapping) for row in preprod_result]
                
                results[query_name] = {
                    'staging': staging_data,
                    'preprod': preprod_data,
                    'different': staging_data != preprod_data
                }
            except Exception as e:
                print(f"⚠️  Could not analyze {query_name}: {e}")
                results[query_name] = {'error': str(e)}
        
        return results
    
    def _check_migration_status(self) -> Dict[str, Any]:
        """Check Alembic migration status in both databases."""
        print("📋 Checking migration status...")
        
        migration_query = """
            SELECT version_num, is_current 
            FROM alembic_version 
            ORDER BY version_num DESC 
            LIMIT 5;
        """
        
        try:
            with self.staging_engine.connect() as staging_conn:
                staging_migrations = staging_conn.execute(text(migration_query)).fetchall()
                staging_current = [row[0] for row in staging_migrations if row[1]]
            
            with self.preprod_engine.connect() as preprod_conn:
                preprod_migrations = preprod_conn.execute(text(migration_query)).fetchall()
                preprod_current = [row[0] for row in preprod_migrations if row[1]]
            
            return {
                'staging_current': staging_current,
                'preprod_current': preprod_current,
                'different_versions': staging_current != preprod_current,
                'staging_migrations': [row[0] for row in staging_migrations],
                'preprod_migrations': [row[0] for row in preprod_migrations]
            }
        except Exception as e:
            return {'error': f"Could not check migration status: {e}"}
    
    def _analyze_project_data(self) -> Dict[str, Any]:
        """Analyze project data specifically for the QA organization."""
        print("📊 Analyzing project data for QA organization...")
        
        qa_org_id = '18012b84-b605-4669-95bf-55aa16c5513c'
        
        analysis_queries = {
            'qa_projects': f"""
                SELECT 
                    id, name, type, created_at, updated_at
                FROM projects 
                WHERE organization_id = '{qa_org_id}'
                ORDER BY created_at;
            """,
            'qa_workflow_projects': f"""
                SELECT wp.id, p.name, p.type
                FROM workflow_projects wp
                JOIN projects p ON wp.id = p.id
                WHERE p.organization_id = '{qa_org_id}'
                ORDER BY p.created_at;
            """,
            'qa_agent_projects': f"""
                SELECT ap.id, p.name, p.type
                FROM agent_projects ap
                JOIN projects p ON ap.id = p.id
                WHERE p.organization_id = '{qa_org_id}'
                ORDER BY p.created_at;
            """
        }
        
        results = {}
        
        for query_name, query in analysis_queries.items():
            try:
                with self.staging_engine.connect() as staging_conn:
                    staging_result = staging_conn.execute(text(query)).fetchall()
                    staging_data = [dict(row._mapping) for row in staging_result]
                
                with self.preprod_engine.connect() as preprod_conn:
                    preprod_result = preprod_conn.execute(text(query)).fetchall()
                    preprod_data = [dict(row._mapping) for row in preprod_result]
                
                results[query_name] = {
                    'staging_count': len(staging_data),
                    'preprod_count': len(preprod_data),
                    'staging_data': staging_data,
                    'preprod_data': preprod_data,
                    'different': staging_data != preprod_data
                }
            except Exception as e:
                print(f"⚠️  Could not analyze {query_name}: {e}")
                results[query_name] = {'error': str(e)}
        
        return results
    
    def generate_report(self, results: Dict[str, Any]) -> str:
        """Generate a comprehensive comparison report."""
        report = []
        report.append("# Database Schema Comparison Report")
        report.append(f"**Generated**: {results['timestamp']}")
        report.append("")
        
        # Tables comparison
        tables = results['tables']
        report.append("## 📊 Table Comparison")
        report.append(f"- **Staging tables**: {tables['staging_count']}")
        report.append(f"- **Preprod tables**: {tables['preprod_count']}")
        if tables['staging_only']:
            report.append(f"- **Staging only**: {', '.join(tables['staging_only'])}")
        if tables['preprod_only']:
            report.append(f"- **Preprod only**: {', '.join(tables['preprod_only'])}")
        report.append("")
        
        # Column differences
        if results['columns']:
            report.append("## 📋 Column Differences")
            for table_name, differences in results['columns'].items():
                report.append(f"### {table_name}")
                if differences['staging_only']:
                    report.append(f"- **Staging only columns**: {', '.join(differences['staging_only'])}")
                if differences['preprod_only']:
                    report.append(f"- **Preprod only columns**: {', '.join(differences['preprod_only'])}")
                if differences['type_differences']:
                    for diff in differences['type_differences']:
                        report.append(f"- **{diff['column']}**: staging={diff['staging_type']}, preprod={diff['preprod_type']}")
            report.append("")
        
        # Polymorphic analysis
        polymorphic = results['polymorphic_tables']
        report.append("## 🔍 Polymorphic Table Analysis")
        
        for query_name, data in polymorphic.items():
            if 'error' not in data:
                report.append(f"### {query_name.replace('_', ' ').title()}")
                if data['different']:
                    report.append("⚠️ **DIFFERENCE DETECTED**")
                report.append(f"- **Staging**: {data['staging']}")
                report.append(f"- **Preprod**: {data['preprod']}")
                report.append("")
        
        # Migration status
        migration_status = results['migration_status']
        if 'error' not in migration_status:
            report.append("## 📋 Migration Status")
            report.append(f"- **Staging current**: {migration_status['staging_current']}")
            report.append(f"- **Preprod current**: {migration_status['preprod_current']}")
            if migration_status['different_versions']:
                report.append("⚠️ **DIFFERENT MIGRATION VERSIONS**")
            report.append("")
        
        # Project data analysis
        project_data = results['data_analysis']
        report.append("## 📊 QA Project Data Analysis")
        
        for query_name, data in project_data.items():
            if 'error' not in data:
                report.append(f"### {query_name.replace('_', ' ').title()}")
                report.append(f"- **Staging count**: {data['staging_count']}")
                report.append(f"- **Preprod count**: {data['preprod_count']}")
                if data['different']:
                    report.append("⚠️ **DATA DIFFERENCES DETECTED**")
                report.append("")
        
        return "\n".join(report)


def main():
    parser = argparse.ArgumentParser(description='Compare database schemas between staging and preprod')
    parser.add_argument('--staging-url', required=True, help='Staging database URL')
    parser.add_argument('--preprod-url', required=True, help='Preprod database URL')
    parser.add_argument('--output', help='Output file for the report')
    
    args = parser.parse_args()
    
    try:
        # Create database engines
        print("🔌 Connecting to databases...")
        staging_engine = create_engine(args.staging_url)
        preprod_engine = create_engine(args.preprod_url)
        
        # Test connections
        with staging_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("✅ Staging database connected")
        
        with preprod_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("✅ Preprod database connected")
        
        # Run comparison
        comparator = DatabaseSchemaComparator(staging_engine, preprod_engine)
        results = comparator.compare_schemas()
        
        # Generate report
        report = comparator.generate_report(results)
        
        # Output results
        if args.output:
            with open(args.output, 'w') as f:
                f.write(report)
            print(f"📄 Report saved to {args.output}")
        else:
            print("\n" + "="*80)
            print(report)
        
        # Also save raw results as JSON
        json_output = args.output.replace('.md', '.json') if args.output else 'schema_comparison.json'
        with open(json_output, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"📊 Raw results saved to {json_output}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

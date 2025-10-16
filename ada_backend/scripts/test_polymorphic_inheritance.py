#!/usr/bin/env python3
"""
Test Polymorphic Inheritance Issue - SAFE VERSION

This script tests the polymorphic inheritance issue by running READ-ONLY queries
that should work if the inheritance is set up correctly.

SAFETY FEATURES:
- READ-ONLY operations only (no writes, no schema changes)
- Safe to run on preprod server
- Compares staging vs preprod data
- No modifications to any database

Usage:
    python test_polymorphic_inheritance.py --staging-url <staging_db_url> --preprod-url <preprod_db_url>
"""

import argparse
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


def test_polymorphic_inheritance(staging_url: str, preprod_url: str):
    """Test polymorphic inheritance queries comparing staging vs preprod."""
    print("🔍 Testing polymorphic inheritance - SAFE READ-ONLY VERSION")
    print(f"📊 Staging: {staging_url}")
    print(f"📊 Preprod: {preprod_url}")

    try:
        staging_engine = create_engine(staging_url)
        preprod_engine = create_engine(preprod_url)

        # Test both databases
        staging_results = test_single_database(staging_engine, "STAGING")
        preprod_results = test_single_database(preprod_engine, "PREPROD")

        # Compare results
        print("\n" + "=" * 80)
        print("📊 COMPARISON RESULTS")
        print("=" * 80)

        compare_results(staging_results, preprod_results)

        return staging_results, preprod_results

    except Exception as e:
        print(f"❌ Error testing polymorphic inheritance: {e}")
        return None, None


def test_single_database(engine: Engine, environment: str):
    """Test polymorphic inheritance on a single database (READ-ONLY)."""
    print(f"\n🔍 Testing {environment} database...")

    results = {
        "environment": environment,
        "connection": False,
        "projects_table": False,
        "type_column": False,
        "project_type_enum": False,
        "polymorphic_tables": False,
        "qa_projects_count": 0,
        "workflow_projects_count": 0,
        "agent_projects_count": 0,
        "polymorphic_consistency": False,
        "sqlalchemy_style_count": 0,
        "missing_polymorphic_records": 0,
    }

    try:
        with engine.connect() as conn:
            results["connection"] = True
            print(f"✅ {environment} database connected")

            # Test 1: Check if projects table has type column
            print(f"\n1️⃣ Testing {environment} projects table structure...")
            result = conn.execute(
                text(
                    """
                SELECT column_name, data_type, is_nullable 
                FROM information_schema.columns 
                WHERE table_name = 'projects' AND column_name = 'type';
            """
                )
            ).fetchall()

            if result:
                results["projects_table"] = True
                results["type_column"] = True
                print(f"✅ {environment} projects table has 'type' column")
                for row in result:
                    print(f"   - {row[0]}: {row[1]} (nullable: {row[2]})")
            else:
                print(f"❌ {environment} projects table missing 'type' column")
                return results

            # Test 2: Check project_type enum
            print(f"\n2️⃣ Testing {environment} project_type enum...")
            result = conn.execute(
                text(
                    """
                SELECT enumlabel 
                FROM pg_enum 
                WHERE enumtypid = (
                    SELECT oid 
                    FROM pg_type 
                    WHERE typname = 'project_type'
                )
                ORDER BY enumsortorder;
            """
                )
            ).fetchall()

            if result:
                results["project_type_enum"] = True
                enum_values = [row[0] for row in result]
                print(f"✅ {environment} project type enum values: {enum_values}")
            else:
                print(f"❌ {environment} project type enum not found")
                return results

            # Test 3: Check polymorphic tables exist
            print(f"\n3️⃣ Testing {environment} polymorphic tables...")
            tables_to_check = ["workflow_projects", "agent_projects"]
            all_tables_exist = True

            for table in tables_to_check:
                result = conn.execute(
                    text(
                        f"""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = '{table}'
                    );
                """
                    )
                ).fetchone()

                if result[0]:
                    print(f"✅ {environment} table {table} exists")
                else:
                    print(f"❌ {environment} table {table} missing")
                    all_tables_exist = False

            results["polymorphic_tables"] = all_tables_exist
            if not all_tables_exist:
                return results

            # Test 4: Check QA organization data
            print(f"\n4️⃣ Testing {environment} QA organization data...")
            qa_org_id = "18012b84-b605-4669-95bf-55aa16c5513c"

            # Count total projects
            result = conn.execute(
                text(
                    f"""
                SELECT COUNT(*) as total_projects
                FROM projects 
                WHERE organization_id = '{qa_org_id}';
            """
                )
            ).fetchone()
            results["qa_projects_count"] = result[0]
            print(f"   - {environment} total projects: {results['qa_projects_count']}")

            # Count by type
            result = conn.execute(
                text(
                    f"""
                SELECT type, COUNT(*) as count
                FROM projects 
                WHERE organization_id = '{qa_org_id}'
                GROUP BY type
                ORDER BY type;
            """
                )
            ).fetchall()
            print(f"   - {environment} projects by type:")
            for row in result:
                print(f"     * {row[0]}: {row[1]}")

            # Test 5: Test polymorphic queries
            print(f"\n5️⃣ Testing {environment} polymorphic queries...")

            # Test WorkflowProject query
            result = conn.execute(
                text(
                    f"""
                SELECT COUNT(*) as count
                FROM workflow_projects wp
                JOIN projects p ON wp.id = p.id
                WHERE p.organization_id = '{qa_org_id}';
            """
                )
            ).fetchone()
            results["workflow_projects_count"] = result[0]
            print(f"   - {environment} WorkflowProject query result: {results['workflow_projects_count']}")

            # Test AgentProject query
            result = conn.execute(
                text(
                    f"""
                SELECT COUNT(*) as count
                FROM agent_projects ap
                JOIN projects p ON ap.id = p.id
                WHERE p.organization_id = '{qa_org_id}';
            """
                )
            ).fetchone()
            results["agent_projects_count"] = result[0]
            print(f"   - {environment} AgentProject query result: {results['agent_projects_count']}")

            # Test 6: Test SQLAlchemy-style polymorphic query
            print(f"\n6️⃣ Testing {environment} SQLAlchemy polymorphic query...")
            result = conn.execute(
                text(
                    f"""
                SELECT p.id, p.name, p.type
                FROM projects p
                WHERE p.organization_id = '{qa_org_id}'
                AND p.type = 'workflow';
            """
                )
            ).fetchall()
            results["sqlalchemy_style_count"] = len(result)
            print(f"   - {environment} SQLAlchemy-style query result: {results['sqlalchemy_style_count']}")

            # Test 7: Check polymorphic consistency
            print(f"\n7️⃣ Testing {environment} polymorphic consistency...")
            result = conn.execute(
                text(
                    f"""
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
                WHERE p.organization_id = '{qa_org_id}'
                GROUP BY p.type, status
                ORDER BY p.type, status;
            """
                )
            ).fetchall()

            print(f"   - {environment} polymorphic consistency:")
            consistent_count = 0
            total_count = 0
            for row in result:
                print(f"     * {row[0]} ({row[1]}): {row[2]}")
                if row[1] == "consistent":
                    consistent_count += row[2]
                total_count += row[2]

            results["polymorphic_consistency"] = consistent_count == total_count and total_count > 0

            # Test 8: Check for missing polymorphic records
            print(f"\n8️⃣ Checking {environment} for missing polymorphic records...")
            result = conn.execute(
                text(
                    f"""
                SELECT p.id, p.name, p.type
                FROM projects p
                LEFT JOIN workflow_projects wp ON p.id = wp.id AND p.type = 'workflow'
                LEFT JOIN agent_projects ap ON p.id = ap.id AND p.type = 'agent'
                WHERE p.organization_id = '{qa_org_id}'
                AND wp.id IS NULL AND ap.id IS NULL;
            """
                )
            ).fetchall()

            results["missing_polymorphic_records"] = len(result)
            if result:
                print(f"❌ {environment} found {len(result)} projects with missing polymorphic records:")
                for row in result:
                    print(f"   - {row[1]} ({row[2]}) - ID: {row[0]}")
            else:
                print(f"✅ {environment} all projects have proper polymorphic records")

            # Summary for this environment
            print(f"\n" + "=" * 60)
            print(f"📊 {environment} SUMMARY")
            print(f"   - Total projects: {results['qa_projects_count']}")
            print(f"   - WorkflowProject records: {results['workflow_projects_count']}")
            print(f"   - AgentProject records: {results['agent_projects_count']}")
            print(f"   - SQLAlchemy-style query: {results['sqlalchemy_style_count']}")
            print(f"   - Polymorphic consistency: {results['polymorphic_consistency']}")

            if (
                results["qa_projects_count"] > 0
                and results["workflow_projects_count"] == 0
                and results["agent_projects_count"] == 0
            ):
                print(f"❌ {environment} POLYMORPHIC INHERITANCE ISSUE DETECTED")
                print(f"   - Projects exist but polymorphic queries return 0 results")
            elif results["qa_projects_count"] == results["workflow_projects_count"] + results["agent_projects_count"]:
                print(f"✅ {environment} Polymorphic inheritance working correctly")
            else:
                print(f"⚠️  {environment} Partial polymorphic inheritance issue")

    except Exception as e:
        print(f"❌ Error testing {environment} polymorphic inheritance: {e}")
        results["error"] = str(e)

    return results


def compare_results(staging_results, preprod_results):
    """Compare staging vs preprod results."""
    if not staging_results or not preprod_results:
        print("❌ Cannot compare - missing results from one or both environments")
        return

    print("🔍 COMPARISON ANALYSIS")
    print("-" * 40)

    # Compare key metrics
    comparisons = [
        ("QA Projects Count", "qa_projects_count"),
        ("Workflow Projects Count", "workflow_projects_count"),
        ("Agent Projects Count", "agent_projects_count"),
        ("SQLAlchemy Style Count", "sqlalchemy_style_count"),
        ("Polymorphic Consistency", "polymorphic_consistency"),
        ("Missing Polymorphic Records", "missing_polymorphic_records"),
    ]

    for label, key in comparisons:
        staging_val = staging_results.get(key, "N/A")
        preprod_val = preprod_results.get(key, "N/A")

        if staging_val == preprod_val:
            print(f"✅ {label}: {staging_val} (same)")
        else:
            print(f"⚠️  {label}: Staging={staging_val}, Preprod={preprod_val} (DIFFERENT)")

    # Identify the issue
    print("\n🔍 ISSUE IDENTIFICATION")
    print("-" * 40)

    if preprod_results.get("qa_projects_count", 0) > 0:
        if (
            preprod_results.get("workflow_projects_count", 0) == 0
            and preprod_results.get("agent_projects_count", 0) == 0
        ):
            print("❌ PREPROD ISSUE: Projects exist but polymorphic queries return 0 results")
            print("   → This explains why API returns empty array")
        elif not preprod_results.get("polymorphic_consistency", False):
            print("❌ PREPROD ISSUE: Polymorphic consistency problems detected")
        else:
            print("✅ PREPROD: Polymorphic inheritance appears to be working")
    else:
        print("❌ PREPROD ISSUE: No QA projects found in database")

    if staging_results.get("qa_projects_count", 0) > 0:
        if staging_results.get("workflow_projects_count", 0) > 0 or staging_results.get("agent_projects_count", 0) > 0:
            print("✅ STAGING: Polymorphic inheritance working correctly")
        else:
            print("❌ STAGING ISSUE: Polymorphic queries also failing")
    else:
        print("❌ STAGING ISSUE: No QA projects found in database")


def main():
    parser = argparse.ArgumentParser(description="Test polymorphic inheritance - SAFE READ-ONLY VERSION")
    parser.add_argument("--staging-url", required=True, help="Staging database URL")
    parser.add_argument("--preprod-url", required=True, help="Preprod database URL")

    args = parser.parse_args()

    print("🔒 SAFETY NOTICE: This script performs READ-ONLY operations only")
    print("   - No writes, no schema changes, no modifications")
    print("   - Safe to run on preprod server")
    print("   - Compares staging vs preprod data")
    print("")

    staging_results, preprod_results = test_polymorphic_inheritance(args.staging_url, args.preprod_url)

    if staging_results and preprod_results:
        print("\n✅ Polymorphic inheritance test COMPLETED")

        # Determine if we found the issue
        if (
            preprod_results.get("qa_projects_count", 0) > 0
            and preprod_results.get("workflow_projects_count", 0) == 0
            and preprod_results.get("agent_projects_count", 0) == 0
        ):
            print("🎯 ISSUE CONFIRMED: Preprod has projects but polymorphic queries fail")
            print("   → This explains why API returns empty array")
            print("   → Solution: Modify repository function to use base Project queries")
        else:
            print("🤔 Issue not clearly identified - review results above")

        sys.exit(0)
    else:
        print("\n❌ Polymorphic inheritance test FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()

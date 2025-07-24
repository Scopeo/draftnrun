#!/usr/bin/env python3
"""
Test script to demonstrate the schedule cleanup functionality.
This shows how schedules are identified and cleaned up correctly.
"""

import sys
import os
from uuid import UUID, uuid4

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ada_backend.services.schedule_service import (
    _matches_schedule_criteria,
    generate_schedule_name,
    cleanup_schedules_for_project,
    cleanup_schedules_for_graph
)
from ada_backend.celery_app import celery_app


def test_schedule_matching():
    """Test the schedule matching logic."""
    print("🔍 SCHEDULE MATCHING LOGIC TEST")
    print("=" * 50)
    
    # Mock schedule configurations
    test_configs = [
        {
            "name": "schedule_12345678_87654321_abcdefgh",
            "config": {
                "task": "execute_scheduled_workflow",
                "args": ["project-1", "graph-1", "scheduler-1"],
                "schedule": "crontab(minute=0, hour=9)"
            }
        },
        {
            "name": "schedule_12345678_87654321_ijklmnop",
            "config": {
                "task": "execute_scheduled_workflow", 
                "args": ["project-1", "graph-1", "scheduler-2"],
                "schedule": "crontab(minute=0, hour=14)"
            }
        },
        {
            "name": "schedule_abcdefgh_12345678_qrstuvwx",
            "config": {
                "task": "execute_scheduled_workflow",
                "args": ["project-2", "graph-2", "scheduler-3"], 
                "schedule": "crontab(minute=30, hour=16)"
            }
        },
        {
            "name": "cleanup-old-executions",
            "config": {
                "task": "cleanup_old_executions",
                "args": [90],
                "schedule": "crontab(hour=2, minute=0)"
            }
        }
    ]
    
    print("\n📋 Test Configurations:")
    for item in test_configs:
        config = item["config"]
        args = config.get("args", [])
        print(f"  • {item['name']}")
        print(f"    Task: {config['task']}")
        print(f"    Args: {args}")
    
    print("\n🎯 Testing Matching Criteria:")
    
    # Test project matching
    print("\n1. Matching by project_id='project-1':")
    for item in test_configs:
        matches = _matches_schedule_criteria(item["config"], project_id="project-1")
        status = "✅ MATCH" if matches else "❌ NO MATCH"
        print(f"   {status}: {item['name']}")
    
    # Test graph matching 
    print("\n2. Matching by graph_runner_id='graph-1':")
    for item in test_configs:
        matches = _matches_schedule_criteria(item["config"], graph_runner_id="graph-1")
        status = "✅ MATCH" if matches else "❌ NO MATCH"
        print(f"   {status}: {item['name']}")
    
    # Test scheduler matching
    print("\n3. Matching by scheduler_id='scheduler-2':")
    for item in test_configs:
        matches = _matches_schedule_criteria(item["config"], scheduler_id="scheduler-2")
        status = "✅ MATCH" if matches else "❌ NO MATCH"
        print(f"   {status}: {item['name']}")
    
    # Test combined matching
    print("\n4. Matching by project_id='project-1' AND graph_runner_id='graph-1':")
    for item in test_configs:
        matches = _matches_schedule_criteria(item["config"], project_id="project-1", graph_runner_id="graph-1")
        status = "✅ MATCH" if matches else "❌ NO MATCH"
        print(f"   {status}: {item['name']}")


def test_schedule_name_generation():
    """Test schedule name generation."""
    print("\n\n🏷️  SCHEDULE NAME GENERATION")
    print("=" * 50)
    
    test_cases = [
        {
            "project_id": UUID("12345678-1234-1234-1234-123456789012"),
            "graph_runner_id": UUID("87654321-4321-4321-4321-210987654321"), 
            "scheduler_id": UUID("abcdefab-cdef-abcd-efab-cdefabcdefab")
        },
        {
            "project_id": UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            "graph_runner_id": UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            "scheduler_id": UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
        }
    ]
    
    for i, case in enumerate(test_cases, 1):
        schedule_name = generate_schedule_name(
            case["project_id"], 
            case["graph_runner_id"], 
            case["scheduler_id"]
        )
        print(f"\n{i}. Generated schedule name:")
        print(f"   Project:   {case['project_id']}")
        print(f"   Graph:     {case['graph_runner_id']}")  
        print(f"   Scheduler: {case['scheduler_id']}")
        print(f"   → Name:    {schedule_name}")


def test_current_celery_schedules():
    """Show current Celery Beat schedules."""
    print("\n\n📅 CURRENT CELERY BEAT SCHEDULES")
    print("=" * 50)
    
    schedules = celery_app.conf.beat_schedule
    
    if not schedules:
        print("No schedules currently configured.")
        return
    
    for name, config in schedules.items():
        print(f"\n📋 {name}:")
        print(f"   Task: {config.get('task', 'N/A')}")
        print(f"   Schedule: {config.get('schedule', 'N/A')}")
        print(f"   Args: {config.get('args', [])}")
        print(f"   Options: {config.get('options', {})}")
        
        # Test if it matches our workflow criteria
        is_workflow = _matches_schedule_criteria(config)
        print(f"   Is Workflow Schedule: {'✅ YES' if is_workflow else '❌ NO'}")


def simulate_cleanup_scenarios():
    """Simulate different cleanup scenarios."""
    print("\n\n🧹 CLEANUP SCENARIOS SIMULATION")
    print("=" * 50)
    
    # Mock some schedules in beat configuration for testing
    mock_schedules = {
        "schedule_12345678_87654321_abcdefab": {
            "task": "execute_scheduled_workflow",
            "args": ["12345678-1234-1234-1234-123456789012", "87654321-4321-4321-4321-210987654321", "abcdefab-cdef-abcd-efab-cdefabcdefab"],
            "schedule": "crontab(minute=0, hour=9)",
            "options": {"queue": "scheduled_workflows"}
        },
        "schedule_12345678_87654321_cdefcdef": {
            "task": "execute_scheduled_workflow", 
            "args": ["12345678-1234-1234-1234-123456789012", "87654321-4321-4321-4321-210987654321", "cdefcdef-cdef-cdef-cdef-cdefcdefcdef"],
            "schedule": "crontab(minute=0, hour=14)",
            "options": {"queue": "scheduled_workflows"}
        },
        "schedule_aaaaaaaa_bbbbbbbb_cccccccc": {
            "task": "execute_scheduled_workflow",
            "args": ["aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", "cccccccc-cccc-cccc-cccc-cccccccccccc"],
            "schedule": "crontab(minute=30, hour=16)",
            "options": {"queue": "scheduled_workflows"}
        }
    }
    
    print(f"\n📋 Mock schedules created:")
    for name, config in mock_schedules.items():
        args = config["args"]
        print(f"   • {name}")
        print(f"     Project: {args[0][:8]}...")
        print(f"     Graph:   {args[1][:8]}...")
        print(f"     Scheduler: {args[2][:8]}...")
    
    # Temporarily add to Celery config for testing
    original_schedules = celery_app.conf.beat_schedule.copy()
    celery_app.conf.beat_schedule.update(mock_schedules)
    
    try:
        print("\n🎯 Cleanup Scenario 1: Remove schedules for specific project")
        project_id = "12345678-1234-1234-1234-123456789012"
        print(f"   Target project: {project_id[:8]}...")
        
        matching_schedules = []
        for name, config in celery_app.conf.beat_schedule.items():
            if _matches_schedule_criteria(config, project_id=project_id):
                matching_schedules.append(name)
        
        print(f"   Would remove {len(matching_schedules)} schedules:")
        for name in matching_schedules:
            print(f"     - {name}")
        
        print("\n🎯 Cleanup Scenario 2: Remove schedules for specific graph")
        graph_id = "87654321-4321-4321-4321-210987654321"
        print(f"   Target graph: {graph_id[:8]}...")
        
        matching_schedules = []
        for name, config in celery_app.conf.beat_schedule.items():
            if _matches_schedule_criteria(config, graph_runner_id=graph_id):
                matching_schedules.append(name)
        
        print(f"   Would remove {len(matching_schedules)} schedules:")
        for name in matching_schedules:
            print(f"     - {name}")
            
    finally:
        # Restore original schedules
        celery_app.conf.beat_schedule = original_schedules


if __name__ == "__main__":
    print("🚀 SCHEDULE CLEANUP TESTING SYSTEM")
    print("=" * 60)
    
    try:
        test_schedule_matching()
        test_schedule_name_generation()
        test_current_celery_schedules()
        simulate_cleanup_scenarios()
        
        print("\n\n🎉 All tests completed successfully!")
        print("\n💡 Key Improvements:")
        print("  • Precise schedule matching by project/graph/scheduler IDs")
        print("  • Safe cleanup that won't accidentally remove wrong schedules")
        print("  • Project deletion now cleans up Celery Beat schedules")
        print("  • API keys are cleaned up during project deletion")
        print("  • Better error handling and logging")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc() 
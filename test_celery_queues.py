#!/usr/bin/env python3
"""
Test script to demonstrate that active_queues shows worker configuration,
not job content. This proves you don't need jobs to see queues.
"""

import sys
import os
import time

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ada_backend.celery_app import celery_app

def test_active_queues_without_jobs():
    """Test that active_queues shows worker configuration, not job content."""
    print("🔍 TESTING: active_queues without any scheduled jobs")
    print("=" * 60)
    
    try:
        # Check active queues (should show worker configuration)
        inspector = celery_app.control.inspect()
        active_queues = inspector.active_queues()
        
        print(f"Active queues result: {active_queues}")
        
        if active_queues:
            print("\n✅ WORKERS ARE RUNNING AND REGISTERED:")
            for worker, queues in active_queues.items():
                print(f"  Worker: {worker}")
                for queue in queues:
                    print(f"    → Listening to: {queue['name']}")
                    
            # Check if scheduled_workflows queue is active
            scheduled_workflows_active = any(
                q["name"] == "scheduled_workflows" 
                for worker_queues in active_queues.values() 
                for q in worker_queues
            )
            
            print(f"\n🎯 scheduled_workflows queue active: {scheduled_workflows_active}")
            
        else:
            print("\n❌ NO WORKERS RUNNING")
            print("To see active_queues, you need to start workers:")
            print("  celery -A ada_backend.celery_app worker -Q scheduled_workflows")
            
    except Exception as e:
        print(f"❌ Error checking active queues: {e}")
        print("\nThis might mean:")
        print("  1. No workers are running")
        print("  2. Redis connection failed")
        print("  3. Celery configuration issue")


def test_beat_schedule_without_jobs():
    """Test that beat_schedule can be empty but active_queues still shows workers."""
    print("\n\n⏰ TESTING: beat_schedule vs active_queues")
    print("=" * 60)
    
    try:
        # Check beat schedule (scheduled jobs)
        beat_schedule = celery_app.conf.beat_schedule
        scheduled_jobs = [
            name for name, config in beat_schedule.items()
            if config.get("task") == "execute_scheduled_workflow"
        ]
        
        print(f"Beat schedule: {beat_schedule}")
        print(f"Scheduled jobs count: {len(scheduled_jobs)}")
        print(f"Scheduled job names: {scheduled_jobs}")
        
        # Check active queues again
        inspector = celery_app.control.inspect()
        active_queues = inspector.active_queues()
        
        print(f"\nActive queues: {active_queues}")
        
        if active_queues:
            print("\n✅ CONCLUSION:")
            print("  - Beat schedule can be EMPTY (no jobs)")
            print("  - Active queues can still show WORKERS")
            print("  - active_queues = worker configuration, not job content")
        else:
            print("\n❌ No workers running to demonstrate")
            
    except Exception as e:
        print(f"❌ Error: {e}")


def demonstrate_the_difference():
    """Demonstrate the difference between worker registration and job content."""
    print("\n\n📚 EXPLANATION: Worker Registration vs Job Content")
    print("=" * 60)
    
    print("""
🔧 WORKER REGISTRATION (active_queues):
   - Happens when worker starts
   - Shows which queues workers listen to
   - Independent of job scheduling
   - Example: {"worker1": [{"name": "scheduled_workflows"}]}

📋 JOB CONTENT (Redis queue):
   - Happens when Beat schedules tasks
   - Shows actual tasks waiting to be executed
   - Depends on cron schedules
   - Example: [{"task": "execute_scheduled_workflow", "args": [...]}]

🎯 HEALTH CHECK LOGIC:
   - Check if workers are listening to scheduled_workflows queue
   - If yes: tasks can be executed when scheduled
   - If no: tasks pile up in Redis but never execute
    """)


if __name__ == "__main__":
    print("🚀 CELERY QUEUE TESTING")
    print("=" * 60)
    
    test_active_queues_without_jobs()
    test_beat_schedule_without_jobs()
    demonstrate_the_difference()
    
    print("\n" + "=" * 60)
    print("💡 KEY INSIGHT:")
    print("active_queues shows WORKER CONFIGURATION, not JOB CONTENT!")
    print("Workers register their queue preferences when they start,")
    print("regardless of whether any jobs are scheduled.") 
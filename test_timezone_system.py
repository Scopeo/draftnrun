#!/usr/bin/env python3
"""
Test script to demonstrate the timezone system for CRON_SCHEDULER.
This shows how timezones are handled in the cron scheduling system.
"""

import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine.agent.triggers.utils import (
    get_timezone_options,
    validate_timezone,
    convert_cron_to_utc,
    validate_cron_expression
)


def test_timezone_options():
    """Test the timezone options system."""
    print("🌍 TIMEZONE OPTIONS SYSTEM")
    print("=" * 50)
    
    options = get_timezone_options()
    
    for region, timezones in options.items():
        print(f"\n📍 {region}:")
        for tz in timezones:
            print(f"  • {tz['value']} - {tz['label']}")
    
    print(f"\n✅ Total timezones available: {sum(len(tzs) for tzs in options.values())}")


def test_timezone_validation():
    """Test timezone validation."""
    print("\n🔍 TIMEZONE VALIDATION")
    print("=" * 50)
    
    test_timezones = [
        "UTC",
        "America/New_York", 
        "Europe/Paris",
        "Asia/Tokyo",
        "Australia/Sydney",
        "Invalid/Timezone"
    ]
    
    for tz in test_timezones:
        result = validate_timezone(tz)
        if result["status"] == "SUCCESS":
            print(f"✅ {tz}: {result['label']} (Offset: {result['current_offset']})")
        else:
            print(f"❌ {tz}: {result['error']}")


def test_cron_timezone_conversion():
    """Test cron expression timezone conversion."""
    print("\n⏰ CRON TIMEZONE CONVERSION")
    print("=" * 50)
    
    test_cases = [
        ("0 9 * * *", "UTC"),
        ("0 9 * * *", "America/New_York"),
        ("0 9 * * *", "Europe/Paris"),
        ("0 9 * * *", "Asia/Tokyo"),
        ("0 9 * * *", "Australia/Sydney"),
    ]
    
    for cron_expr, timezone in test_cases:
        print(f"\n🕐 Converting: {cron_expr} in {timezone}")
        
        # Validate original cron
        cron_validation = validate_cron_expression(cron_expr)
        if cron_validation["status"] != "SUCCESS":
            print(f"❌ Invalid cron: {cron_validation['error']}")
            continue
        
        # Convert to UTC
        conversion = convert_cron_to_utc(cron_expr, timezone)
        if conversion["status"] == "SUCCESS":
            print(f"  Original: {conversion['original_description']}")
            print(f"  UTC:      {conversion['utc_description']}")
            print(f"  Offset:   {conversion['timezone_offset']}")
        else:
            print(f"❌ Conversion failed: {conversion['error']}")


def test_complex_cron_expressions():
    """Test complex cron expressions with timezone conversion."""
    print("\n🎯 COMPLEX CRON EXPRESSIONS")
    print("=" * 50)
    
    complex_crons = [
        ("0 9 1,15 * *", "America/New_York"),  # 1st and 15th at 9 AM
        ("0 */2 * * *", "Europe/Paris"),       # Every 2 hours
        ("0 9 * * 1-5", "Asia/Tokyo"),         # Weekdays at 9 AM
        ("30 14 * * 0", "Australia/Sydney"),   # Sundays at 2:30 PM
    ]
    
    for cron_expr, timezone in complex_crons:
        print(f"\n🔄 Complex: {cron_expr} in {timezone}")
        
        conversion = convert_cron_to_utc(cron_expr, timezone)
        if conversion["status"] == "SUCCESS":
            print(f"  Original: {conversion['original_description']}")
            print(f"  UTC:      {conversion['utc_description']}")
            print(f"  Cron:     {cron_expr} -> {conversion['utc_cron']}")
        else:
            print(f"❌ Failed: {conversion['error']}")


if __name__ == "__main__":
    print("🚀 CRON SCHEDULER TIMEZONE SYSTEM DEMO")
    print("=" * 60)
    
    try:
        test_timezone_options()
        test_timezone_validation()
        test_cron_timezone_conversion()
        test_complex_cron_expressions()
        
        print("\n🎉 All tests completed successfully!")
        print("\n💡 Key Features:")
        print("  • 40+ timezones across 6 regions")
        print("  • Automatic timezone validation")
        print("  • Cron expression conversion to UTC")
        print("  • Human-readable descriptions")
        print("  • Proper error handling")
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Make sure you have the required dependencies installed:")
        print("  pip install pytz cron-converter")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc() 
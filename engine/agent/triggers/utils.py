import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
import pytz

from cron_converter import Cron

LOGGER = logging.getLogger(__name__)


# Comprehensive timezone options for CRON_SCHEDULER component
TIMEZONE_OPTIONS = {
    "UTC & GMT": [
        {"value": "UTC", "label": "UTC (Coordinated Universal Time)"},
        {"value": "GMT", "label": "GMT (Greenwich Mean Time)"},
    ],
    "North America": [
        {"value": "America/New_York", "label": "Eastern Time (ET) - New York, Toronto"},
        {"value": "America/Chicago", "label": "Central Time (CT) - Chicago, Mexico City"},
        {"value": "America/Denver", "label": "Mountain Time (MT) - Denver, Phoenix"},
        {"value": "America/Los_Angeles", "label": "Pacific Time (PT) - Los Angeles, Vancouver"},
        {"value": "America/Anchorage", "label": "Alaska Time (AKT) - Anchorage"},
        {"value": "Pacific/Honolulu", "label": "Hawaii Time (HST) - Honolulu"},
    ],
    "Europe": [
        {"value": "Europe/London", "label": "GMT/BST - London, Dublin"},
        {"value": "Europe/Paris", "label": "CET/CEST - Paris, Berlin, Rome"},
        {"value": "Europe/Moscow", "label": "MSK - Moscow"},
        {"value": "Europe/Istanbul", "label": "TRT - Istanbul"},
        {"value": "Europe/Amsterdam", "label": "CET/CEST - Amsterdam, Brussels"},
        {"value": "Europe/Stockholm", "label": "CET/CEST - Stockholm, Oslo"},
    ],
    "Asia": [
        {"value": "Asia/Tokyo", "label": "JST - Tokyo, Seoul"},
        {"value": "Asia/Shanghai", "label": "CST - Shanghai, Beijing"},
        {"value": "Asia/Hong_Kong", "label": "HKT - Hong Kong"},
        {"value": "Asia/Singapore", "label": "SGT - Singapore, Kuala Lumpur"},
        {"value": "Asia/Kolkata", "label": "IST - Mumbai, New Delhi"},
        {"value": "Asia/Dubai", "label": "GST - Dubai, Abu Dhabi"},
        {"value": "Asia/Bangkok", "label": "ICT - Bangkok, Jakarta"},
    ],
    "Australia & Pacific": [
        {"value": "Australia/Sydney", "label": "AEST/AEDT - Sydney, Melbourne"},
        {"value": "Australia/Perth", "label": "AWST - Perth"},
        {"value": "Pacific/Auckland", "label": "NZST/NZDT - Auckland, Wellington"},
        {"value": "Pacific/Fiji", "label": "FJT - Fiji"},
    ],
    "South America": [
        {"value": "America/Sao_Paulo", "label": "BRT/BRST - São Paulo, Rio de Janeiro"},
        {"value": "America/Argentina/Buenos_Aires", "label": "ART - Buenos Aires"},
        {"value": "America/Santiago", "label": "CLT/CLST - Santiago"},
        {"value": "America/Lima", "label": "PET - Lima"},
    ],
    "Africa": [
        {"value": "Africa/Cairo", "label": "EET - Cairo"},
        {"value": "Africa/Johannesburg", "label": "SAST - Johannesburg, Cape Town"},
        {"value": "Africa/Lagos", "label": "WAT - Lagos, Kinshasa"},
        {"value": "Africa/Nairobi", "label": "EAT - Nairobi, Addis Ababa"},
    ],
}


def get_timezone_options() -> Dict[str, List[Dict[str, str]]]:
    return TIMEZONE_OPTIONS


def get_all_timezone_values() -> List[str]:
    return [opt["value"] for region in TIMEZONE_OPTIONS.values() for opt in region]


def validate_timezone(timezone_str: str) -> Dict[str, Any]:
    try:
        all_timezones = get_all_timezone_values()
        if timezone_str not in all_timezones:
            return {"status": "FAILED", "error": f"Unsupported timezone: {timezone_str}"}

        tz = pytz.timezone(timezone_str)
        now = datetime.now(tz)
        offset = now.utcoffset().total_seconds() / 3600
        offset_str = f"{offset:+.1f}h"

        label = next(
            (opt["label"] for region in TIMEZONE_OPTIONS.values() for opt in region if opt["value"] == timezone_str),
            timezone_str,
        )

        return {
            "status": "SUCCESS",
            "timezone": timezone_str,
            "label": label,
            "current_offset": offset_str,
            "current_time": now.strftime("%Y-%m-%d %H:%M:%S %Z"),
        }

    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


def _generate_cron_description(cron_expression: str) -> str:
    """
    Generate a simple human-readable description for a cron expression.
    """
    parts = cron_expression.split()
    if len(parts) != 5:
        return f"Cron: {cron_expression}"

    minute, hour, day, month, day_of_week = parts

    # Simple patterns
    if minute == "0" and hour != "*" and day == "*" and month == "*" and day_of_week == "*":
        return f"Daily at {hour.zfill(2)}:00"
    elif minute != "*" and hour != "*" and day == "*" and month == "*" and day_of_week == "*":
        return f"Daily at {hour.zfill(2)}:{minute.zfill(2)}"
    elif minute == "0" and hour == "0" and day == "*" and month == "*" and day_of_week == "*":
        return "Daily at midnight"
    else:
        return f"Cron: {cron_expression}"


def validate_cron_expression(cron_expression: str) -> Dict[str, Any]:
    """
    Validate cron expression using cron-converter.
    Returns status, description, and parsed components if valid.
    """
    try:
        cron = Cron(cron_expression)
    except Exception as e:
        return {"status": "FAILED", "error": f"Invalid cron: {e}"}

    # Generate a simple description since cron-converter doesn't have description() method
    description = _generate_cron_description(cron_expression)
    parts = cron.to_list()
    components = dict(
        zip(["minute", "hour", "day", "month", "day_of_week"], [" ".join(str(p) for p in part) for part in parts])
    )

    return {
        "status": "SUCCESS",
        "description": description,
        "components": components,
    }


def convert_cron_to_utc(cron_expression: str, user_timezone: str) -> Dict[str, Any]:
    """
    Convert a cron expression from user timezone to UTC by computing the next scheduled time.
    """
    v = validate_cron_expression(cron_expression)
    if v["status"] != "SUCCESS":
        return {"status": "FAILED", "error": v["error"]}

    try:
        cron = Cron(cron_expression)

        if user_timezone.upper() in ["UTC", "GMT"]:
            return {
                "status": "SUCCESS",
                "utc_cron": cron_expression,
                "original_description": v["description"],
                "utc_description": v["description"],
                "timezone_offset": "UTC (no conversion needed)",
            }

        try:
            tz = pytz.timezone(user_timezone)
        except pytz.UnknownTimeZoneError:
            return {"status": "FAILED", "error": f"Unknown timezone: {user_timezone}"}

        now_local = datetime.now(tz)
        now_utc = datetime.now(pytz.UTC)

        next_local = cron.schedule(now_local).next()
        next_utc = cron.schedule(now_utc).next()

        offset = (next_local - next_utc).total_seconds() / 3600
        offset_str = f"{offset:+.1f}h"

        return {
            "status": "SUCCESS",
            "utc_cron": cron_expression,
            "original_description": v["description"],
            "utc_description": _generate_cron_description(cron_expression),
            "timezone_offset": offset_str,
            "next_local": next_local.isoformat(),
            "next_utc": next_utc.isoformat(),
        }

    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


def validate_and_describe_cron(cron_expr: str) -> Optional[str]:
    """
    Legacy helper: returns description if cron is valid, else None.
    """
    v = validate_cron_expression(cron_expr)
    return v["description"] if v["status"] == "SUCCESS" else None

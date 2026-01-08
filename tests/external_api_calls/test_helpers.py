import base64
import json
import os

import pytest
from pydantic import BaseModel

from engine.components.types import ToolDescription
from settings import settings


class ConstrainedResponse(BaseModel):
    response: str
    is_successful: bool


def get_setting_value(name: str) -> str | None:
    value = getattr(settings, name, None)
    if not value:
        return None
    return str(value)


def skip_if_missing_settings(*required_names: str) -> None:
    missing = [name for name in required_names if not get_setting_value(name)]
    if missing:
        pytest.skip(f"Missing required settings/env: {', '.join(missing)}")


def small_test_image_bytes_png() -> bytes:
    b64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAG0AAAAoCAMAAADDs4S7AAABJlBMVEUAAADFIiDFIh/FIh/FIx+/ICD3vwD7vAT7vAT8vAP8vAPEJSDFIh/G"
        "Ih76vAX7vAP7uwTDIh7rRDXfQDDrQjX8vAVASEjEIR7qQzXqQzXnSDBFRUVER0VERkVER0ZGRkZISEhERkVER0ZAQEBERERERkbqQzXoQjft"
        "QzXrQzRFR0ZER0dDR0fUuBNDR0ZGRkZCSEVER0dBhPKEU4qksyc1qFNDSEZChfRzYKS0LjruuglmrT80qFNSednJtxhNqklER0dERkZER0ZE"
        "R0bpQjXqQjRFSEhESEhDR0VER0ZESEbnQDjqQzRFRUXpRDToQzVDRkRESETqQjXnRDRCR0RDR0VDR0ZESEZDRkZDRkNFSEVARUVBg/MzplFA"
        "h+9BhPQ0qFMwp1Cjq+zaAAAAYnRSTlMAb9//vyAgv//fXzDvcG/vQJCPEI+fIKD/3yBgv+//XyDPzxBAgO9wb+/fT5+f31BgcKD//59f////"
        "////////j3+Pr9/vYECQ76AgvzCAkKBAYEBwn6+AoFBgMJCQIM+/IDH/nxkAAAIVSURBVHgBYhi+YBSMglHAyMTMwoopzMbOwclFdcu4mYGA"
        "hxddmI+fAwgEqG2bIDMYCAkjCwqLcICBKBYNAFboAkuBGAqiaK0i2E8hGRzG3d3dZf/7mN9BDjmkR3m43u4yBn8v09OyuTyG5XPZFK0glrRS"
        "xPeVyhWHKalGtWytjn6NZjaulUSpVouklPBdVbKNAjtRTdM1/Yr6tK91Q6zF6RkHYHaac/guUxYzps0vDDVd06841BaXMFqLuo3PLONHjWsr"
        "q2sDTdfUFQfa+sZmoBU47TCWM6MP/pn7SlvZUi4bptr2zmaolbmMEJLdkpCtPSQP3Ifmn7WK/tODmKYtjGuLm5uh5kiHIMPplpVpcq9ly6pU"
        "FbO0Uibnkk9bUU1bPQyxo43NUOv/Oum41wkM/ban+mCAWZ4BVXvukqd06Zp2EXCXF5vpGn2URLvyJ00/saWaxkE7ZeFLDbjODrsBPBZfspp0"
        "67UzJPU/KPMOOBFLirD6jYb7w/6KD4hpaPEOwx55OjxbEkmin8+QrafnaX6vwa+pKyKuVSmjdDumtfgC7fV7Tbv2K6ZoznIP/fY4jYhmhk+/"
        "17T7B6RquCOfSt7dJ+9imiNL/li+04LiGt6mSXl6EtLOIqZB2HqqCqcnocG8Wmr2wCCuuVdqL9WJaNrd2/uHQ3rmc5GReKRj8NkWy0BlEBeP"
        "27aERGJMGAWjYBSMAgCA2YXMvdXiqwAAAABJRU5ErkJggg=="
    )
    return base64.b64decode(b64)


def default_tool_description() -> ToolDescription:
    return ToolDescription(
        name="extract_answer",
        description="Return a structured answer.",
        tool_properties={
            "answer": {"type": "string", "description": "The answer text"},
            "ok": {"type": "boolean", "description": "Whether the operation succeeded"},
        },
        required_tool_properties=["answer", "ok"],
    )


def json_schema_str() -> str:
    schema = {
        "name": "test_response",
        "schema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        },
    }
    return json.dumps(schema)


def parse_possibly_double_encoded_json(value: str) -> dict:
    parsed = json.loads(value)
    if isinstance(parsed, str):
        parsed = json.loads(parsed)
    if isinstance(parsed, list) and parsed:
        item = parsed[0]
        if isinstance(item, dict) and "tool_use" in item and isinstance(item["tool_use"], dict):
            tool_use = item["tool_use"]
            params = tool_use.get("parameters")
            if isinstance(params, dict):
                return params
    if not isinstance(parsed, dict):
        raise ValueError(f"Expected dict-like JSON, got: {type(parsed).__name__}")
    return parsed


def mistral_ocr_messages() -> tuple[dict | None, str]:
    override_url = os.getenv("EXTERNAL_TEST_MISTRAL_OCR_IMAGE_URL")
    if override_url:
        image_url_value = override_url
        url_kind = "override"
    else:
        return None, "missing_override"
    return {
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": image_url_value},
                    }
                ],
            }
        ]
    }, url_kind

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class RichTextItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str = "text"
    text: dict[str, Any] = Field(default_factory=lambda: {"content": ""})
    annotations: Optional[dict[str, Any]] = None


class DatabasePropertySchema(BaseModel):
    """Schema definition for a database property (column)."""

    model_config = ConfigDict(extra="allow")


class PagePropertyValue(BaseModel):
    """A single property value when creating/updating a page."""

    model_config = ConfigDict(extra="allow")


class BlockItem(BaseModel):
    """A Notion block (paragraph, heading, list item, etc.)."""

    model_config = ConfigDict(extra="allow")

    type: str = "paragraph"
    object: str = "block"


class DatabaseFilter(BaseModel):
    """Notion database query filter (compound or property-level)."""

    model_config = ConfigDict(extra="allow")


class DatabaseSort(BaseModel):
    """Notion database query sort."""

    property: Optional[str] = None
    timestamp: Optional[str] = None
    direction: str = "ascending"

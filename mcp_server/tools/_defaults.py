"""Default values for entity creation and model format utilities."""

import random
import uuid

ICONS = [
    "ph-rocket", "ph-lightbulb", "ph-crown", "ph-target", "ph-star",
    "ph-diamond", "ph-flag", "ph-gear", "ph-book", "ph-palette",
    "ph-fire", "ph-lightning", "ph-planet", "ph-cube", "ph-shield",
    "ph-compass", "ph-fire-simple", "ph-cloud-lightning", "ph-shooting-star",
    "ph-heart", "ph-leaf", "ph-airplane", "ph-cloud", "ph-sun",
    "ph-moon", "ph-mountains", "ph-sword", "ph-anchor", "ph-flask",
    "ph-archive", "ph-battery-charging", "ph-atom", "ph-bell",
    "ph-puzzle-piece", "ph-trophy", "ph-eye", "ph-camera",
    "ph-music-note", "ph-tree", "ph-flower", "ph-magnet", "ph-key",
    "ph-lock", "ph-feather", "ph-butterfly", "ph-ghost",
    "ph-lighthouse", "ph-tent", "ph-bicycle", "ph-hourglass",
]

COLORS = [
    "#FF6B6B", "#4ECDC4", "#45B7D1", "#FFA07A", "#98D8C8",
    "#F7DC6F", "#BB8FCE", "#85C1E2", "#F06292", "#AED581",
    "#FF8A65", "#9575CD", "#52C41A", "#FF9800", "#2196F3",
    "#E91E63", "#26C6DA", "#FFAB91", "#5E35B1", "#A1887F",
    "#66BB6A", "#FFA726", "#42A5F5", "#EC407A",
]


def generate_entity_defaults() -> dict[str, str]:
    """Generate id, icon, and icon_color for a new project/agent."""
    return {
        "id": str(uuid.uuid4()),
        "icon": random.choice(ICONS),
        "icon_color": random.choice(COLORS),
    }


def ensure_provider_model_format(model: str) -> str:
    """Ensure model string has a provider prefix (e.g. 'openai:gpt-4.1').

    Mirrors back-office/src/utils/agentUtils.ts ensureProviderModelFormat.
    If the caller passes an empty string, raises ValueError — the model
    must be chosen explicitly from the agent's available options.
    """
    if not model:
        raise ValueError(
            "Model name must not be empty. Use get_graph() to inspect the "
            "completion_model parameter's options and pick a valid model."
        )
    if ":" in model:
        return model
    return f"openai:{model}"

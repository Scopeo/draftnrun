from uuid import UUID

from mcp_server.tools.webhooks import SPECS


def test_create_typeform_webhook_tool_spec():
    spec = next(item for item in SPECS if item.name == "create_typeform_webhook")

    assert spec.method == "post"
    assert spec.path == "/projects/{project_id}/webhooks/typeform"
    assert spec.scope == "role"
    assert spec.roles == ("developer", "admin", "super_admin")
    assert spec.path_params[0].name == "project_id"
    assert spec.path_params[0].annotation is UUID
    assert [param.name for param in spec.body_fields] == ["events", "filter_options", "rotate_secret"]

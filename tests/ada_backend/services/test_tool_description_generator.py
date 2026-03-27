"""Unit tests for tool_description_generator service.

Uses mock objects to avoid database dependencies while thoroughly testing
the generation logic, setup modes, overrides, and backward-compatibility.
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

from ada_backend.database.models import (
    JsonSchemaType,
    ParameterType,
    PortSetupMode,
    PortType,
)
from ada_backend.services.tool_description_generator import (
    _build_property_schema,
    _is_port_required,
    generate_tool_description,
    get_user_set_port_names,
    sanitize_tool_name,
)


def _make_port_definition(
    name="query",
    parameter_type=ParameterType.STRING,
    description="A search query",
    nullable=False,
    is_tool_input=True,
    port_type=PortType.INPUT,
):
    pd = MagicMock()
    pd.id = uuid4()
    pd.name = name
    pd.parameter_type = parameter_type
    pd.description = description
    pd.nullable = nullable
    pd.is_tool_input = is_tool_input
    pd.port_type = port_type
    pd.component_version_id = uuid4()
    pd.default_tool_json_schema = None
    return pd


def _make_tool_port_config(
    port_def=None,
    setup_mode=PortSetupMode.AI_FILLED,
    ai_name_override=None,
    ai_description_override=None,
    is_required_override=None,
    custom_parameter_type=None,
    json_schema_override=None,
    input_port_instance=None,
    expression_json=None,
    custom_ui_component_properties=None,
):
    config = MagicMock()
    config.id = uuid4()
    config.port_definition_id = port_def.id if port_def else None
    config.port_definition = port_def
    config.setup_mode = setup_mode
    config.ai_name_override = ai_name_override
    config.ai_description_override = ai_description_override
    config.is_required_override = is_required_override
    config.custom_parameter_type = custom_parameter_type
    config.json_schema_override = json_schema_override
    config.input_port_instance_id = input_port_instance.id if input_port_instance else None
    config.input_port_instance = input_port_instance
    config.expression_json = expression_json
    config.custom_ui_component_properties = custom_ui_component_properties
    return config


def _make_component_instance(component_version_id=None):
    ci = MagicMock()
    ci.id = uuid4()
    ci.component_version_id = component_version_id or uuid4()
    ci.tool_description_override = None
    return ci


# ---------------------------------------------------------------------------
# _build_property_schema
# ---------------------------------------------------------------------------


class TestBuildPropertySchema:
    def test_from_port_definition_defaults(self):
        pd = _make_port_definition(description="A query string")
        schema = _build_property_schema(pd, config=None)
        assert schema == {"type": "string", "description": "A query string"}

    def test_integer_type_mapping(self):
        pd = _make_port_definition(parameter_type=ParameterType.INTEGER, description="Count")
        schema = _build_property_schema(pd, config=None)
        assert schema["type"] == "integer"

    def test_float_type_mapping(self):
        pd = _make_port_definition(parameter_type=ParameterType.FLOAT, description="Score")
        schema = _build_property_schema(pd, config=None)
        assert schema["type"] == "number"

    def test_boolean_type_mapping(self):
        pd = _make_port_definition(parameter_type=ParameterType.BOOLEAN, description="Flag")
        schema = _build_property_schema(pd, config=None)
        assert schema["type"] == "boolean"

    def test_json_type_mapping(self):
        pd = _make_port_definition(parameter_type=ParameterType.JSON, description="Data")
        schema = _build_property_schema(pd, config=None)
        assert schema["type"] == "object"

    def test_config_ai_description_overrides_port_definition(self):
        pd = _make_port_definition(description="default")
        config = _make_tool_port_config(port_def=pd, ai_description_override="custom AI desc")
        schema = _build_property_schema(pd, config=config)
        assert schema["description"] == "custom AI desc"

    def test_default_tool_json_schema_used_as_fallback(self):
        rich_schema = {"type": "object", "properties": {"must": {"type": "array"}}, "additionalProperties": False}
        pd = _make_port_definition(parameter_type=ParameterType.JSON, description="Filters")
        pd.default_tool_json_schema = rich_schema
        schema = _build_property_schema(pd, config=None)
        assert schema == rich_schema

    def test_config_json_schema_override_beats_default_tool_json_schema(self):
        default_schema = {"type": "object", "properties": {"must": {"type": "array"}}}
        override_schema = {"type": "string", "description": "override"}
        pd = _make_port_definition(parameter_type=ParameterType.JSON)
        pd.default_tool_json_schema = default_schema
        config = _make_tool_port_config(port_def=pd, json_schema_override=override_schema)
        schema = _build_property_schema(pd, config=config)
        assert schema == override_schema

    def test_json_schema_override_replaces_everything(self):
        pd = _make_port_definition()
        config = _make_tool_port_config(
            port_def=pd,
            json_schema_override={
                "type": "array",
                "items": {"type": "string"},
                "description": "A list of tags",
            },
        )
        schema = _build_property_schema(pd, config=config)
        assert schema == {"type": "array", "items": {"type": "string"}, "description": "A list of tags"}

    def test_json_schema_override_adds_description_from_config(self):
        pd = _make_port_definition()
        config = _make_tool_port_config(
            port_def=pd,
            json_schema_override={"type": "object"},
            ai_description_override="The payload",
        )
        schema = _build_property_schema(pd, config=config)
        assert schema == {"type": "object", "description": "The payload"}

    def test_custom_parameter_type(self):
        config = _make_tool_port_config(
            custom_parameter_type=JsonSchemaType.ARRAY,
            ai_description_override="List of items",
        )
        schema = _build_property_schema(None, config=config)
        assert schema["type"] == "array"
        assert schema["description"] == "List of items"

    def test_no_port_def_no_config_defaults_to_string(self):
        schema = _build_property_schema(None, config=None)
        assert schema == {"type": "string"}


# ---------------------------------------------------------------------------
# _is_port_required
# ---------------------------------------------------------------------------


class TestIsPortRequired:
    def test_non_nullable_port_is_required(self):
        pd = _make_port_definition(nullable=False)
        assert _is_port_required(pd, config=None) is True

    def test_nullable_port_is_not_required(self):
        pd = _make_port_definition(nullable=True)
        assert _is_port_required(pd, config=None) is False

    def test_override_true_makes_required(self):
        pd = _make_port_definition(nullable=True)
        config = _make_tool_port_config(port_def=pd, is_required_override=True)
        assert _is_port_required(pd, config=config) is True

    def test_override_false_makes_optional(self):
        pd = _make_port_definition(nullable=False)
        config = _make_tool_port_config(port_def=pd, is_required_override=False)
        assert _is_port_required(pd, config=config) is False

    def test_no_port_def_defaults_to_required(self):
        assert _is_port_required(None, config=None) is True


# ---------------------------------------------------------------------------
# generate_tool_description
# ---------------------------------------------------------------------------


class TestGenerateToolDescription:
    @patch("ada_backend.services.tool_description_generator.get_tool_port_configurations")
    @patch("ada_backend.services.tool_description_generator._get_tool_eligible_port_definitions")
    @patch("ada_backend.services.tool_description_generator._resolve_tool_name_and_description")
    def test_all_ports_ai_filled_no_configs(self, mock_resolve, mock_ports, mock_configs):
        """With no ToolPortConfiguration rows, all is_tool_input=True ports default to AI_FILLED."""
        ci = _make_component_instance()
        session = MagicMock()

        pd_query = _make_port_definition(name="query", description="Search query", nullable=False)
        pd_topic = _make_port_definition(name="topic", description="Topic", nullable=True)

        mock_resolve.return_value = ("tavily_api", "Search API")
        mock_ports.return_value = [pd_query, pd_topic]
        mock_configs.return_value = []

        result = generate_tool_description(session, ci)

        assert result is not None
        assert result.name == "tavily_api"
        assert result.description == "Search API"
        assert "query" in result.tool_properties
        assert "topic" in result.tool_properties
        assert "query" in result.required_tool_properties

    @patch("ada_backend.services.tool_description_generator.get_tool_port_configurations")
    @patch("ada_backend.services.tool_description_generator._get_tool_eligible_port_definitions")
    @patch("ada_backend.services.tool_description_generator._resolve_tool_name_and_description")
    def test_user_set_port_excluded_from_properties(self, mock_resolve, mock_ports, mock_configs):
        """Ports with setup_mode=USER_SET should NOT appear in tool_properties."""
        ci = _make_component_instance()
        session = MagicMock()

        pd_query = _make_port_definition(name="query", description="Search query")
        pd_topic = _make_port_definition(name="topic", description="Topic")

        config_topic = _make_tool_port_config(port_def=pd_topic, setup_mode=PortSetupMode.USER_SET)

        mock_resolve.return_value = ("search", "Search")
        mock_ports.return_value = [pd_query, pd_topic]
        mock_configs.return_value = [config_topic]

        result = generate_tool_description(session, ci)

        assert "query" in result.tool_properties
        assert "topic" not in result.tool_properties

    @patch("ada_backend.services.tool_description_generator.get_tool_port_configurations")
    @patch("ada_backend.services.tool_description_generator._get_tool_eligible_port_definitions")
    @patch("ada_backend.services.tool_description_generator._resolve_tool_name_and_description")
    def test_deactivated_port_excluded(self, mock_resolve, mock_ports, mock_configs):
        """Ports with setup_mode=DEACTIVATED should NOT appear in tool_properties."""
        ci = _make_component_instance()
        session = MagicMock()

        pd_query = _make_port_definition(name="query")
        pd_days = _make_port_definition(name="days", parameter_type=ParameterType.INTEGER)

        config_days = _make_tool_port_config(port_def=pd_days, setup_mode=PortSetupMode.DEACTIVATED)

        mock_resolve.return_value = ("search", "Search")
        mock_ports.return_value = [pd_query, pd_days]
        mock_configs.return_value = [config_days]

        result = generate_tool_description(session, ci)

        assert "query" in result.tool_properties
        assert "days" not in result.tool_properties

    @patch("ada_backend.services.tool_description_generator.get_tool_port_configurations")
    @patch("ada_backend.services.tool_description_generator._get_tool_eligible_port_definitions")
    @patch("ada_backend.services.tool_description_generator._resolve_tool_name_and_description")
    def test_ai_name_override(self, mock_resolve, mock_ports, mock_configs):
        """ai_name_override should change the property key in tool_properties."""
        ci = _make_component_instance()
        session = MagicMock()

        pd = _make_port_definition(name="query", description="Original")
        config = _make_tool_port_config(
            port_def=pd,
            ai_name_override="search_query",
            ai_description_override="The search query to use",
        )

        mock_resolve.return_value = ("search", "Search")
        mock_ports.return_value = [pd]
        mock_configs.return_value = [config]

        result = generate_tool_description(session, ci)

        assert "search_query" in result.tool_properties
        assert "query" not in result.tool_properties
        assert result.tool_properties["search_query"]["description"] == "The search query to use"

    @patch("ada_backend.services.tool_description_generator.get_tool_port_configurations")
    @patch("ada_backend.services.tool_description_generator._get_tool_eligible_port_definitions")
    @patch("ada_backend.services.tool_description_generator._resolve_tool_name_and_description")
    def test_custom_port_without_port_definition(self, mock_resolve, mock_ports, mock_configs):
        """Custom ports (no port_definition_id) should be generated from config alone."""
        ci = _make_component_instance()
        session = MagicMock()

        custom_ipi = MagicMock()
        custom_ipi.id = uuid4()
        custom_ipi.name = "custom_param"

        config = _make_tool_port_config(
            setup_mode=PortSetupMode.AI_FILLED,
            ai_name_override="extra_filter",
            ai_description_override="An additional filter",
            custom_parameter_type=JsonSchemaType.STRING,
            input_port_instance=custom_ipi,
        )

        mock_resolve.return_value = ("search", "Search")
        mock_ports.return_value = []
        mock_configs.return_value = [config]

        result = generate_tool_description(session, ci)

        assert "extra_filter" in result.tool_properties
        assert result.tool_properties["extra_filter"]["type"] == "string"
        assert result.tool_properties["extra_filter"]["description"] == "An additional filter"

    @patch("ada_backend.services.tool_description_generator.get_tool_port_configurations")
    @patch("ada_backend.services.tool_description_generator._get_tool_eligible_port_definitions")
    @patch("ada_backend.services.tool_description_generator._resolve_tool_name_and_description")
    def test_custom_port_uses_instance_name_as_fallback(self, mock_resolve, mock_ports, mock_configs):
        """If ai_name_override is None, use input_port_instance.name."""
        ci = _make_component_instance()
        session = MagicMock()

        custom_ipi = MagicMock()
        custom_ipi.id = uuid4()
        custom_ipi.name = "dynamic_input"

        config = _make_tool_port_config(
            setup_mode=PortSetupMode.AI_FILLED,
            custom_parameter_type=JsonSchemaType.BOOLEAN,
            input_port_instance=custom_ipi,
        )

        mock_resolve.return_value = ("tool", "A tool")
        mock_ports.return_value = []
        mock_configs.return_value = [config]

        result = generate_tool_description(session, ci)

        assert "dynamic_input" in result.tool_properties
        assert result.tool_properties["dynamic_input"]["type"] == "boolean"

    @patch("ada_backend.services.tool_description_generator._resolve_tool_name_and_description")
    def test_returns_none_when_no_tool_name(self, mock_resolve):
        ci = _make_component_instance()
        session = MagicMock()

        mock_resolve.return_value = (None, None)

        result = generate_tool_description(session, ci)
        assert result is None

    @patch("ada_backend.services.tool_description_generator.get_tool_port_configurations")
    @patch("ada_backend.services.tool_description_generator._get_tool_eligible_port_definitions")
    @patch("ada_backend.services.tool_description_generator._resolve_tool_name_and_description")
    def test_required_override_propagated(self, mock_resolve, mock_ports, mock_configs):
        ci = _make_component_instance()
        session = MagicMock()

        pd = _make_port_definition(name="query", nullable=True)
        config = _make_tool_port_config(port_def=pd, is_required_override=True)

        mock_resolve.return_value = ("search", "Search")
        mock_ports.return_value = [pd]
        mock_configs.return_value = [config]

        result = generate_tool_description(session, ci)

        assert "query" in result.required_tool_properties

    @patch("ada_backend.services.tool_description_generator.get_tool_port_configurations")
    @patch("ada_backend.services.tool_description_generator._get_tool_eligible_port_definitions")
    @patch("ada_backend.services.tool_description_generator._resolve_tool_name_and_description")
    def test_tool_name_sanitized(self, mock_resolve, mock_ports, mock_configs):
        ci = _make_component_instance()
        session = MagicMock()

        mock_resolve.return_value = ("My Tool Name!", "Desc")
        mock_ports.return_value = []
        mock_configs.return_value = []

        result = generate_tool_description(session, ci)
        assert result.name == "My_Tool_Name"

    @patch("ada_backend.services.tool_description_generator.get_tool_port_configurations")
    @patch("ada_backend.services.tool_description_generator._get_tool_eligible_port_definitions")
    @patch("ada_backend.services.tool_description_generator._resolve_tool_name_and_description")
    def test_mixed_modes(self, mock_resolve, mock_ports, mock_configs):
        """Test a realistic mix of AI_FILLED, USER_SET, and DEACTIVATED ports."""
        ci = _make_component_instance()
        session = MagicMock()

        pd_query = _make_port_definition(name="query", description="Query")
        pd_topic = _make_port_definition(name="topic", description="Topic", nullable=True)
        pd_days = _make_port_definition(name="days", parameter_type=ParameterType.INTEGER, description="Days")
        pd_domains = _make_port_definition(name="include_domains", description="Domains", nullable=True)

        config_topic = _make_tool_port_config(port_def=pd_topic, setup_mode=PortSetupMode.USER_SET)
        config_days = _make_tool_port_config(port_def=pd_days, setup_mode=PortSetupMode.DEACTIVATED)

        mock_resolve.return_value = ("tavily_api", "Tavily search")
        mock_ports.return_value = [pd_query, pd_topic, pd_days, pd_domains]
        mock_configs.return_value = [config_topic, config_days]

        result = generate_tool_description(session, ci)

        assert "query" in result.tool_properties
        assert "topic" not in result.tool_properties  # USER_SET
        assert "days" not in result.tool_properties  # DEACTIVATED
        assert "include_domains" in result.tool_properties  # AI_FILLED (default)
        assert result.tool_properties["include_domains"]["description"] == "Domains"


# ---------------------------------------------------------------------------
# get_user_set_port_names
# ---------------------------------------------------------------------------


class TestGetUserSetPortNames:
    @patch("ada_backend.services.tool_description_generator.get_tool_port_configurations")
    def test_returns_user_set_names(self, mock_configs):
        session = MagicMock()
        ci_id = uuid4()

        pd = _make_port_definition(name="topic")
        config = _make_tool_port_config(port_def=pd, setup_mode=PortSetupMode.USER_SET)
        mock_configs.return_value = [config]

        names = get_user_set_port_names(session, ci_id)
        assert names == {"topic"}

    @patch("ada_backend.services.tool_description_generator.get_tool_port_configurations")
    def test_excludes_ai_filled(self, mock_configs):
        session = MagicMock()
        ci_id = uuid4()

        pd = _make_port_definition(name="query")
        config = _make_tool_port_config(port_def=pd, setup_mode=PortSetupMode.AI_FILLED)
        mock_configs.return_value = [config]

        names = get_user_set_port_names(session, ci_id)
        assert names == set()

    @patch("ada_backend.services.tool_description_generator.get_tool_port_configurations")
    def test_excludes_deactivated(self, mock_configs):
        session = MagicMock()
        ci_id = uuid4()

        pd = _make_port_definition(name="days")
        config = _make_tool_port_config(port_def=pd, setup_mode=PortSetupMode.DEACTIVATED)
        mock_configs.return_value = [config]

        names = get_user_set_port_names(session, ci_id)
        assert names == set()


# ---------------------------------------------------------------------------
# sanitize_tool_name
# ---------------------------------------------------------------------------


class TestSanitizeToolName:
    def test_spaces_replaced(self):
        assert sanitize_tool_name("My Tool Name") == "My_Tool_Name"

    def test_special_characters_removed(self):
        assert sanitize_tool_name("tool@v2.0!") == "tool_v2_0"

    def test_hyphens_preserved(self):
        assert sanitize_tool_name("my-tool") == "my-tool"

    def test_consecutive_underscores_collapsed(self):
        assert sanitize_tool_name("a   b___c") == "a_b_c"

    def test_leading_trailing_stripped(self):
        assert sanitize_tool_name("  _tool_ ") == "tool"

    def test_empty_string_fallback(self):
        assert sanitize_tool_name("") == "unnamed_tool"
        assert sanitize_tool_name("!!!") == "unnamed_tool"

    def test_truncated_to_max_length(self):
        long_name = "a" * 100
        assert len(sanitize_tool_name(long_name)) == 64

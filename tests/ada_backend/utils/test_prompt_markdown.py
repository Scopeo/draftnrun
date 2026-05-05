from ada_backend.utils.prompt_markdown import parse_prompt_markdown


class TestParsePromptMarkdown:
    def test_plain_content_no_frontmatter(self):
        result = parse_prompt_markdown("Hello world", "system.md")
        assert result.name == "system"
        assert result.content == "Hello world"
        assert result.description is None

    def test_with_frontmatter(self):
        raw = "---\ndescription: My prompt description\n---\n\nThe prompt content."
        result = parse_prompt_markdown(raw, "my-prompt.md")
        assert result.name == "my-prompt"
        assert result.content == "The prompt content."
        assert result.description == "My prompt description"

    def test_nested_path_name(self):
        raw = "Content here"
        result = parse_prompt_markdown(raw, "folderA/folderB/prompt.md")
        assert result.name == "folderA/folderB/prompt"
        assert result.content == "Content here"

    def test_frontmatter_no_description(self):
        raw = "---\nauthor: someone\n---\n\nContent."
        result = parse_prompt_markdown(raw, "test.md")
        assert result.description is None
        assert result.content == "Content."

    def test_empty_frontmatter(self):
        raw = "---\n---\n\nContent."
        result = parse_prompt_markdown(raw, "test.md")
        assert result.description is None
        assert result.content == "Content."

    def test_no_closing_frontmatter(self):
        raw = "---\ndescription: broken"
        result = parse_prompt_markdown(raw, "test.md")
        assert result.content == "---\ndescription: broken"
        assert result.description is None

    def test_preserves_content_whitespace(self):
        raw = "---\ndescription: desc\n---\n\nLine 1\n\nLine 2\n"
        result = parse_prompt_markdown(raw, "test.md")
        assert result.content == "Line 1\n\nLine 2\n"

    def test_variable_placeholders(self):
        raw = "Hello {{name}}, welcome to {{place}}."
        result = parse_prompt_markdown(raw, "greet.md")
        assert "{{name}}" in result.content
        assert "{{place}}" in result.content

    def test_leading_newlines_stripped(self):
        raw = "\n\n---\ndescription: test\n---\n\nContent"
        result = parse_prompt_markdown(raw, "test.md")
        assert result.description == "test"
        assert result.content == "Content"

    def test_non_string_description_coerced(self):
        raw = "---\ndescription: 42\n---\n\nContent"
        result = parse_prompt_markdown(raw, "test.md")
        assert result.description == "42"
        assert isinstance(result.description, str)

    def test_boolean_description_coerced(self):
        raw = "---\ndescription: true\n---\n\nContent"
        result = parse_prompt_markdown(raw, "test.md")
        assert result.description == "True"
        assert isinstance(result.description, str)

    def test_null_description_stays_none(self):
        raw = "---\ndescription: null\n---\n\nContent"
        result = parse_prompt_markdown(raw, "test.md")
        assert result.description is None

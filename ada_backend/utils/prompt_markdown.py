from dataclasses import dataclass

import yaml


@dataclass
class ParsedPromptFile:
    name: str
    content: str
    description: str | None


_FRONTMATTER_DELIMITER = "---"


def parse_prompt_markdown(raw: str, file_path: str) -> ParsedPromptFile:
    """Parse a prompt markdown file with optional YAML frontmatter.

    ``file_path`` is relative to ``prompt_library/`` (e.g. ``folderA/prompt.md``).
    The prompt name is derived by stripping the ``.md`` extension.
    """
    name = file_path.removesuffix(".md")
    description: str | None = None
    content = raw

    stripped = raw.lstrip("\n")
    if stripped.startswith(_FRONTMATTER_DELIMITER):
        after_first = stripped[len(_FRONTMATTER_DELIMITER) :]
        end_idx = after_first.find(f"\n{_FRONTMATTER_DELIMITER}")
        if end_idx != -1:
            frontmatter_raw = after_first[:end_idx]
            body_start = end_idx + len(f"\n{_FRONTMATTER_DELIMITER}")
            remaining = after_first[body_start:]
            content = remaining.lstrip("\n")

            try:
                meta = yaml.safe_load(frontmatter_raw)
            except yaml.YAMLError:
                meta = None
            if isinstance(meta, dict):
                raw_desc = meta.get("description")
                if raw_desc is not None and not isinstance(raw_desc, str):
                    raw_desc = str(raw_desc)
                description = raw_desc

    return ParsedPromptFile(name=name, content=content, description=description)

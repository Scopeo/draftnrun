import pytest

from mcp_server import docs


def test_register_docs_exposes_expected_safety_resources(fake_mcp):
    docs.register(fake_mcp)

    assert sorted(fake_mcp.resources.keys()) == [f"docs://{domain}" for domain in sorted(docs.DOMAINS.keys())]
    assert fake_mcp.resources["docs://versioning"]["description"] == docs.DOMAIN_DESCRIPTIONS["versioning"]
    assert fake_mcp.resources["docs://known-quirks"]["description"] == docs.DOMAIN_DESCRIPTIONS["known-quirks"]


@pytest.mark.asyncio
async def test_get_guide_returns_corrected_versioning_admin_and_qa_guidance(fake_mcp):
    docs.register(fake_mcp)
    get_guide = fake_mcp.tools["get_guide"]

    versioning = await get_guide("versioning")
    admin = await get_guide("admin")
    qa = await get_guide("qa")

    assert "keeps the current draft runner as the editable draft" in versioning
    assert "creates a brand new draft runner for continued editing" in versioning
    assert "`list_crons()`" in admin
    assert "list_widgets" not in admin
    assert "`run_evaluation(project_id, judge_id, version_output_id)`" in qa


@pytest.mark.asyncio
async def test_get_guide_rejects_unknown_domain(fake_mcp):
    docs.register(fake_mcp)

    with pytest.raises(ValueError, match="Unknown domain 'nope'"):
        await fake_mcp.tools["get_guide"]("nope")


class TestDocSync:
    """Guard against parameter-name drift in high-risk doc strings."""

    def test_admin_doc_mentions_provider_config_key(self):
        assert "provider_config_key" in docs.ADMIN

    def test_qa_doc_mentions_version_output_id_singular(self):
        assert "version_output_id" in docs.QA
        assert "version_output_ids" not in docs.QA

    def test_knowledge_doc_mentions_developer_role(self):
        assert "developer" in docs.KNOWLEDGE.lower()

    def test_graph_and_qa_docs_embed_pinned_example_uuids(self):
        for node_id in docs._GRAPH_DOC_THREE_NODE_EXAMPLE_IDS:
            assert node_id in docs.GRAPHS
        assert docs._GRAPH_DOC_QA_CUSTOM_COLUMN_EXAMPLE_ID in docs.QA

"""suppression_of_rag_filtering_paramters_and_vocabulary_rag_components_clean

Revision ID: 51055d3718c1
Revises: 2301736f9201
Create Date: 2025-06-19 14:34:31.070100

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "51055d3718c1"
down_revision: Union[str, None] = "2301736f9201"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # === Delete parameter-child relationships for Vocabulary RAG components ===
    op.execute(
        """
            DELETE FROM comp_param_child_comps_relationships
            WHERE id IN (
                -- VocabularyEnhancedRAGAgent.retriever → Retriever
                '1e7c4fc5-3e58-4f0a-a3f7-5981aaae7c37',
                -- VocabularyEnhancedRAGAgent.vocabulary_search → VocabularySearch
                '3d2f4a8c-d98e-48d8-b315-6df1762c556f',
                -- VocabularyEnhancedRAGAgent.synthesizer → VocabularyEnhancedSynthesizer
                '9c9dbb74-3008-49cf-a6d6-03293ff83577',
                -- VocabularyEnhancedRAGAgent.reranker → CohereReranker
                '6c1f64aa-ff0e-4a82-b86a-f80321a580ff',
                -- VocabularyEnhancedRAGAgent.formatter → Formatter
                '14f50ab4-49d4-4b02-999e-2591888a8454',
                -- VocabularySearch.db_service → SnowflakeDBService
                '0da14d9b-d699-4542-974f-dc57e15f248f'
            );
        """
    )

    # === Delete basic_parameters linked to vocabulary-related parameter definitions ===
    op.execute(
        """
            DELETE FROM basic_parameters
            WHERE parameter_definition_id IN (
                '3a29fbb1-53f0-44c6-b1e1-d5a2d93f5b0a',  -- retriever
                '9f0c4ab7-621c-46cf-921b-260f5890cc3f',  -- vocabulary_search
                '32a40716-30c4-4d6e-82ff-0be6eecf5951',  -- synthesizer
                '9502a8a6-f48b-42cc-a3f0-c6df296a1677',  -- reranker
                '2e05bc76-54d0-4f45-86b5-50bcbb301c9e',  -- formatter
                '1074ae9c-1944-4f0f-b9e8-2b27a59b6e2a',  -- db_service
                'd73052c1-82d5-4ad3-b8e7-cccf8e8a3804',  -- filtering_condition (enhanced)
                '9472f57b-8d8f-4c8f-8ee1-81c94fc9726d',  -- add_sources
                '67be6c2e-8023-4e2d-9203-c234f5ebd947',  -- prompt_template
                '7e28e4dc-b377-4cd5-a9ec-81e2b2187ab9',  -- model_name
                '52cf3a13-4fcb-4c19-b89a-bd2a016e2ee7',  -- default_temperature
                '3442d221-e6f8-4fa3-b542-24969881fdaf',  -- api_key
                '87f71635-5fa4-4f8f-a1d1-5f33c97fba62',  -- fuzzy_threshold
                'e2c19387-e5c7-486b-baa8-e3ad20e1f6c8',  -- fuzzy_matching_candidates
                '9e55d3e5-316f-4ad2-bde5-7e46e48bc2a6',  -- table_name
                '93b4f0e5-872a-47f8-902f-e29e1d7d8d09'   -- schema_name
            );
        """
    )

    # === Delete parameter definitions for all relevant components ===
    op.execute(
        """
            DELETE FROM component_parameter_definitions
            WHERE id IN (
                '3a29fbb1-53f0-44c6-b1e1-d5a2d93f5b0a',  -- retriever
                '9f0c4ab7-621c-46cf-921b-260f5890cc3f',  -- vocabulary_search
                '32a40716-30c4-4d6e-82ff-0be6eecf5951',  -- synthesizer
                '9502a8a6-f48b-42cc-a3f0-c6df296a1677',  -- reranker
                '2e05bc76-54d0-4f45-86b5-50bcbb301c9e',  -- formatter
                '1074ae9c-1944-4f0f-b9e8-2b27a59b6e2a',  -- db_service
                'd73052c1-82d5-4ad3-b8e7-cccf8e8a3804',  -- filtering_condition
                '9472f57b-8d8f-4c8f-8ee1-81c94fc9726d',  -- add_sources
                '67be6c2e-8023-4e2d-9203-c234f5ebd947',  -- prompt_template
                '7e28e4dc-b377-4cd5-a9ec-81e2b2187ab9',  -- model_name
                '52cf3a13-4fcb-4c19-b89a-bd2a016e2ee7',  -- default_temperature
                '3442d221-e6f8-4fa3-b542-24969881fdaf',  -- api_key
                '87f71635-5fa4-4f8f-a1d1-5f33c97fba62',  -- fuzzy_threshold
                'e2c19387-e5c7-486b-baa8-e3ad20e1f6c8',  -- fuzzy_matching_candidates
                '9e55d3e5-316f-4ad2-bde5-7e46e48bc2a6',  -- table_name
                '93b4f0e5-872a-47f8-902f-e29e1d7d8d09'   -- schema_name
            );
        """
    )

    # === Delete components instances of suppressed components
    op.execute(
        """
                DELETE FROM component_instances
                WHERE component_id IN (
                'f7b4902f-f12c-4f85-9e95-3d0c3c0832e6',  -- VocabularyEnhancedRAGAgent
                '2fd04a07-8f21-4b02-82e3-0b8a627c3e9c',  -- VocabularyEnhancedSynthesizer
                '77e305a4-5d3b-466c-abe0-d944163c06be'   -- VocabularySearch
                );
                """
    )
    # === Delete the vocabulary-related components themselves ===
    op.execute(
        """
            DELETE FROM components
            WHERE id IN (
                'f7b4902f-f12c-4f85-9e95-3d0c3c0832e6',  -- VocabularyEnhancedRAGAgent
                '2fd04a07-8f21-4b02-82e3-0b8a627c3e9c',  -- VocabularyEnhancedSynthesizer
                '77e305a4-5d3b-466c-abe0-d944163c06be'   -- VocabularySearch
            );
        """
    )

    # === Delete basic_parameters linked to the generic RAGAgent filtering_condition parameter ===
    op.execute(
        """
            DELETE FROM basic_parameters
            WHERE parameter_definition_id = '3cf2a47c-dae5-4b29-b44c-c5a4bc8133a5';  -- filtering_condition on RAGAgent
        """
    )

    # === Delete additional filtering_condition for generic RAGAgent ===
    op.execute(
        """
            DELETE FROM component_parameter_definitions
            WHERE id = '3cf2a47c-dae5-4b29-b44c-c5a4bc8133a5';  -- filtering_condition on RAGAgent
        """
    )


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    pass
    # ### end Alembic commands ###

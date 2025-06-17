from engine.agent.synthesizer import Synthesizer
from engine.llm_services.openai_llm_service import OpenAILLMService
from ada_backend.services.registry import FACTORY_REGISTRY, SupportedEntityType
from tests.mocks.trace_manager import MockTraceManager


def test_synthesizer_registration():
    # Register a new entity class with the registry
    factory = FACTORY_REGISTRY.get(entity_name=SupportedEntityType.SYNTHESIZER)
    assert factory is not None

    # Create an instance of the registered entity
    synthesizer = factory(
        trace_manager=MockTraceManager(project_name="test_project"),
        model_name="openai:gpt-4o-mini",
        default_temperature=0.99,
    )
    assert synthesizer is not None
    assert isinstance(synthesizer, Synthesizer)
    assert synthesizer._llm_service is not None
    assert isinstance(synthesizer._llm_service, OpenAILLMService)
    assert synthesizer._llm_service._completion_model == "gpt-4o-mini"
    assert synthesizer._llm_service._default_temperature == 0.99

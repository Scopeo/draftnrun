from ada_backend.database.seed.utils import COMPONENT_VERSION_UUIDS
from ada_backend.services.registry import FACTORY_REGISTRY
from engine.components.synthesizer import Synthesizer
from engine.llm_services.llm_service import CompletionService
from engine.trace.trace_context import set_trace_manager
from tests.mocks.trace_manager import MockTraceManager


def test_synthesizer_registration():
    # Register a new entity class with the registry
    set_trace_manager(MockTraceManager(project_name="test_project"))
    factory = FACTORY_REGISTRY.get(component_version_id=COMPONENT_VERSION_UUIDS["synthesizer"])
    assert factory is not None

    # Create an instance of the registered entity
    synthesizer = factory(
        trace_manager=MockTraceManager(project_name="test_project"),
        completion_model="openai:gpt-4.1-mini",
        temperature=0.99,
    )
    assert synthesizer is not None
    assert isinstance(synthesizer, Synthesizer)
    assert synthesizer._completion_service is not None
    assert isinstance(synthesizer._completion_service, CompletionService)
    assert synthesizer._completion_service._model_name == "gpt-4.1-mini"
    assert synthesizer._completion_service._invocation_parameters.get("temperature") == 0.99

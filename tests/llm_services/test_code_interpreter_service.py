from unittest.mock import MagicMock

from engine.llm_services.llm_service import CodeInterpreterService


def test_code_interpreter_service():
    code_interpreter_service = CodeInterpreterService(
        trace_manager=MagicMock(), provider="openai", model_name="gpt-4.1-mini"
    )
    assert code_interpreter_service._provider == "openai"
    assert code_interpreter_service._model_name == "gpt-4.1-mini"
    assert code_interpreter_service._api_key is None
    assert code_interpreter_service._trace_manager is not None
    
    code_prompt = "print('Hello, world!')"
    response = code_interpreter_service.execute_code(code_prompt)
    assert response is not None
    assert isinstance(response, str)
    assert len(response) > 0


def test_code_interpreter_service_with_api_key():
    code_interpreter_service = CodeInterpreterService(
        trace_manager=MagicMock(), 
        provider="openai", 
        model_name="gpt-4o-mini", 
        api_key="test-api-key"
    )
    assert code_interpreter_service._provider == "openai"
    assert code_interpreter_service._model_name == "gpt-4o-mini"
    assert code_interpreter_service._api_key == "test-api-key"
    assert code_interpreter_service._trace_manager is not None


def test_code_interpreter_service_complex_code():
    code_interpreter_service = CodeInterpreterService(
        trace_manager=MagicMock(), provider="openai", model_name="gpt-4.1-mini"
    )
    
    complex_code_prompt = """
    import matplotlib.pyplot as plt
    import numpy as np
    
    x = np.linspace(0, 10, 100)
    y = np.sin(x)
    
    plt.figure(figsize=(10, 6))
    plt.plot(x, y)
    plt.title('Sine Wave')
    plt.xlabel('x')
    plt.ylabel('sin(x)')
    plt.show()
    """
    
    response = code_interpreter_service.execute_code(complex_code_prompt)
    assert response is not None
    assert isinstance(response, str)
    assert len(response) > 0
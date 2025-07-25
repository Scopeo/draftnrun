FILE_SUPPORTED_MODELS = [
    {"GPT-4.1": "openai:gpt-4.1"},
    {"GPT-4.1 Mini": "openai:gpt-4.1-mini"},
    {"GPT-4.1 Nano": "openai:gpt-4.1-nano"},
    {"GPT-4o": "openai:gpt-4o"},
    {"GPT-4o Mini": "openai:gpt-4o-mini"},
]

IMAGE_SUPPORTED_MODELS = FILE_SUPPORTED_MODELS + [
    {"Gemini 2.5 Pro": "google:gemini-2.5-pro-preview-06-05"},
    {"Gemini 2.5 Flash": "google:gemini-2.5-flash-preview-05-20"},
    {"Gemini 2.0 Flash": "google:gemini-2.0-flash"},
    {"Gemini 2.0 Flash lite": "google:gemini-2.0-flash-lite"},
]

FULL_CAPACITY_COMPLETION_MODELS = IMAGE_SUPPORTED_MODELS + [
    {"Llama 3.3 70B (Cerebras)": "cerebras:llama-3.3-70b"},
    {"Qwen 3 235B (Cerebras)": "cerebras:qwen-3-235b-a22b"},
    {"Mistral Large 2411": "mistral:mistral-large-latest"},
    {"Mistral Medium 2505": "mistral:mistral-medium-latest"},
]

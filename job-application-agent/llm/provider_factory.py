import yaml
import os
from llm.mock_provider import MockProvider

def get_provider():
    # If we are in pytest, conftest.py should mock this, but we can also default to mock
    # based on config.
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'config.yaml')
    
    provider_name = "mock"
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            provider_name = config.get("llm", {}).get("provider", "mock")

    # Override for tests if ENV var set
    if os.environ.get("USE_MOCK_PROVIDER") == "true":
        provider_name = "mock"

    if provider_name == "claude":
        from llm.claude_provider import ClaudeProvider
        return ClaudeProvider()
    elif provider_name == "gemini":
        from llm.gemini_provider import GeminiProvider
        # You can also parse model config from yaml if needed
        return GeminiProvider()
    elif provider_name == "mock":
        return MockProvider()
    else:
        raise ValueError(f"Unknown provider: {provider_name}")

import os
from llm.base_provider import BaseProvider
import anthropic

class ClaudeProvider(BaseProvider):
    def __init__(self, model_name="claude-3-5-sonnet-20240620"):
        self.model_name = model_name
        self.api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")
        self.client = anthropic.Anthropic(api_key=self.api_key)

    def generate_completion(self, prompt: str, system_prompt: str = "") -> str:
        response = self.client.messages.create(
            model=self.model_name,
            max_tokens=2048,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text

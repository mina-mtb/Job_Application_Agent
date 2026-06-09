import os
import google.generativeai as genai
from llm.base_provider import BaseProvider

class GeminiProvider(BaseProvider):
    def __init__(self, model_name="gemini-1.5-flash"):
        self.model_name = model_name
        self.api_key = os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set")
        genai.configure(api_key=self.api_key)
        # You can use gemini-1.5-pro for better reasoning or flash for speed
        self.model = genai.GenerativeModel(self.model_name)

    def generate_completion(self, prompt: str, system_prompt: str = "") -> str:
        # Gemini handles system instructions in model init, but we can prepend it 
        # to the prompt for a simple fallback if not set at model level.
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"System Instruction:\n{system_prompt}\n\nUser Request:\n{prompt}"
            
        response = self.model.generate_content(full_prompt)
        return response.text

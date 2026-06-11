import os
import time
import logging
from llm.base_provider import BaseProvider
from google import genai

logger = logging.getLogger(__name__)


class QuotaExhaustedError(Exception):
    """Raised when Gemini API credits are exhausted."""
    def __init__(self):
        super().__init__(
            "⚠️ Your Gemini API credits have run out!\n\n"
            "To recharge:\n"
            "1. Go to https://aistudio.google.com/billing\n"
            "2. Click 'Buy credits'\n"
            "3. Add more credits (SEK 100 is enough for thousands of CVs)\n\n"
            "After recharging, come back and try again."
        )


class GeminiProvider(BaseProvider):
    def __init__(self, model_name="gemini-2.5-flash"):
        self.model_name = model_name
        self.api_key = os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set")
        self.client = genai.Client(api_key=self.api_key)
        self.max_retries = 2

    def generate_completion(self, prompt: str, system_prompt: str = "") -> str:
        """Generate a completion with retry logic for transient errors."""
        config = genai.types.GenerateContentConfig(
            system_instruction=system_prompt if system_prompt else None,
            temperature=0.7,
            max_output_tokens=8192,
        )
        
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=config,
                )
                return response.text
            except Exception as e:
                last_error = e
                error_str = str(e).lower()
                
                # Check if credits are fully exhausted (not just rate-limited)
                if 'quota' in error_str and 'limit: 0' in str(e):
                    raise QuotaExhaustedError()
                
                # Retry on transient/rate-limit errors
                if any(kw in error_str for kw in ['429', 'rate', 'quota', 'timeout', 'unavailable', '503', '500']):
                    if attempt < self.max_retries:
                        wait_time = 2 ** (attempt + 1)  # 2s, 4s
                        logger.warning(f"Gemini API transient error (attempt {attempt+1}), retrying in {wait_time}s: {e}")
                        time.sleep(wait_time)
                        continue
                # Non-transient error, raise immediately
                raise
        
        raise last_error

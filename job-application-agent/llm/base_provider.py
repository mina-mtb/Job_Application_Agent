from abc import ABC, abstractmethod

class BaseProvider(ABC):
    @abstractmethod
    def generate_completion(self, prompt: str, system_prompt: str = "") -> str:
        """Generate a response from the LLM"""
        pass

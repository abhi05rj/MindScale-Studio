from abc import ABC, abstractmethod


class LocalLLMProvider(ABC):
    """Contract for local language models used to create image prompts."""

    @abstractmethod
    def generate_text(self, prompt: str) -> str:
        """Return text generated from a prompt without using a cloud API."""

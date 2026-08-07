import json
from urllib.error import URLError
from urllib.request import Request, urlopen

from app.image_engine.local_llm_provider import LocalLLMProvider


class OllamaProvider(LocalLLMProvider):
    """Local prompt-generation provider for a running Ollama instance."""

    def __init__(self, model: str = "llama3.2", base_url: str = "http://localhost:11434"):
        self.name = "Ollama Local LLM Provider"
        self.model = model
        self.base_url = base_url.rstrip("/")

    def generate_text(self, prompt: str) -> str:
        payload = json.dumps(
            {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
            }
        ).encode("utf-8")
        request = Request(
            f"{self.base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urlopen(request, timeout=60) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (OSError, URLError, json.JSONDecodeError) as error:
            raise RuntimeError(f"Ollama is unavailable: {error}") from error

        generated_text = body.get("response", "").strip()
        if not generated_text:
            raise RuntimeError("Ollama returned no generated text.")

        return generated_text

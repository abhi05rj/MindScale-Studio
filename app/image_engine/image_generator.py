from app.image_engine.local_llm_provider import LocalLLMProvider
from app.image_engine.ollama_provider import OllamaProvider


class ImageGenerator:
    FIRST_PIN_PROMPT = (
        "A beautiful, modern Pinterest illustration about personal growth, "
        "clean minimal design, soft lighting, premium quality, vertical "
        "composition, inspiring colors."
    )

    def __init__(self, llm_provider: LocalLLMProvider | None = None, image_provider=None):
        self.name = "MindScale Image Engine"
        self.llm_provider = llm_provider or OllamaProvider()
        self.image_provider = image_provider

    def generate_prompt(self, content):
        try:
            return self.llm_provider.generate_text(self.FIRST_PIN_PROMPT)
        except RuntimeError as error:
            print(f"Local prompt generation unavailable: {error}")
            print("Using the built-in image prompt instead.")
            return self.FIRST_PIN_PROMPT

    def generate_image(self, prompt):
        if not self.image_provider:
            print("No cloud image provider configured; skipping image generation.")
            return None

        return self.image_provider.generate_image(prompt)

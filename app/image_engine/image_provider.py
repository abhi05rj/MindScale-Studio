import base64
from binascii import Error as BinasciiError
from pathlib import Path

import openai
from openai import OpenAI


class ImageProvider:

    def __init__(self):
        self.name = "OpenAI Image Provider"
        self.client = OpenAI()
        self.output_path = Path(__file__).resolve().parents[2] / "output" / "first_pin.png"

    def generate_image(self, prompt):
        print("Starting generation...")

        try:
            print("Calling OpenAI...")
            result = self.client.images.generate(
                model="gpt-image-2",
                prompt=prompt,
                n=1,
                size="1024x1536",
                quality="medium",
                output_format="png",
            )
        except openai.OpenAIError as error:
            request_id = f" (request ID: {error.request_id})" if error.request_id else ""
            print(f"Image generation failed{request_id}: {error}")
            return None

        image_base64 = result.data[0].b64_json if result.data else None
        if not image_base64:
            print("Image generation failed: OpenAI returned no image data.")
            return None

        try:
            print("Downloading image...")
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            self.output_path.write_bytes(base64.b64decode(image_base64, validate=True))
        except (BinasciiError, OSError, ValueError) as error:
            print(f"Image download failed: {error}")
            return None

        print("Image saved successfully.")
        return str(self.output_path)

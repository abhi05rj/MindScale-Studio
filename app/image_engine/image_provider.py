class ImageProvider:

    def __init__(self):
        self.name = "OpenAI Image Provider"

    def generate_image(self, prompt):

        print("Generating image...")
        print(prompt)

        return "image_generated.png"
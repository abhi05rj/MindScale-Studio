class ImageGenerator:

    def __init__(self):
        self.name = "MindScale Image Engine"

    def generate_prompt(self, content):

        image_prompt = {
            "subject": content["title"],
            "visual": content["visual_direction"],
            "style": "cinematic, realistic, educational",
            "format": "Pinterest vertical 2:3"
        }

        return image_prompt
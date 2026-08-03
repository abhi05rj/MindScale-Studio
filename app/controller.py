class MindScaleController:

    def __init__(self):
        self.name = "MindScale Studio"

    def start(self):
        print("==============================")
        print(" Welcome to MindScale Studio 🧠")
        print("==============================")
        print("Your AI content engine is ready!")

from app.content_engine.content_engine import ContentEngine
from app.idea_engine.idea_generator import IdeaGenerator
from app.image_engine.image_generator import ImageGenerator

class MindScaleController:

    def __init__(self):
        self.name = "MindScale Studio"
        self.content_engine = ContentEngine()
        self.idea_engine = IdeaGenerator()
        self.image_engine = ImageGenerator()

    def start(self):
        print("----------------")
        print("Welcome to MindScale Studio 🧠")
        print("----------------")

        ideas = self.idea_engine.generate_ideas()
        idea = ideas[0]
     
        print("Available Ideas:")
        for item in ideas:
            print("----------------")
            print(item["title"])

        print("Generated Idea:")
        print(idea)
        post = self.content_engine.generate_post(idea)
        image_prompt = self.image_engine.generate_prompt(post)

        print("\nGenerated Image Prompt:")
        print(image_prompt)

        print("\nGenerated Post:")
        print(post)
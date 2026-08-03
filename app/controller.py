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

class MindScaleController:

    def __init__(self):
        self.name = "MindScale Studio"
        self.content_engine = ContentEngine()
        self.idea_engine = IdeaGenerator()

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

        print("\nGenerated Post:")
        print(post)
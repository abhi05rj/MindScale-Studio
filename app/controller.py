class MindScaleController:

    def __init__(self):
        self.name = "MindScale Studio"

    def start(self):
        print("==============================")
        print(" Welcome to MindScale Studio 🧠")
        print("==============================")
        print("Your AI content engine is ready!")
        from app.content_engine.content_engine import ContentEngine

from app.content_engine.content_engine import ContentEngine
class MindScaleController:

    def __init__(self):
        self.name = "MindScale Studio"
        self.content_engine = ContentEngine()

    def start(self):
        print("----------------")
        print("Welcome to MindScale Studio 🧠")
        print("----------------")

        result = self.content_engine.generate_post(
            "AI Product Management"
        )

        print(result)
from app.content_engine.content_strategy import ContentStrategy, ContentStrategyEngine


class IdeaGenerator:
    """Small facade for turning a raw topic into a content-ready idea."""

    def __init__(self, strategy_engine: ContentStrategyEngine | None = None):
        self.strategy_engine = strategy_engine or ContentStrategyEngine()

    def generate(self, topic: str) -> ContentStrategy:
        return self.strategy_engine.create_strategy(topic)

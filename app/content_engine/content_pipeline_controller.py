from dataclasses import asdict, dataclass

from app.content_engine.idea_generator import IdeaGenerator
from app.content_engine.pinterest_formatter import PinterestFormatter
from app.content_engine.scoring_engine import ContentScoringEngine, ContentScores
from app.content_engine.content_strategy import ContentStrategy
from app.image_engine.local_llm_provider import LocalLLMProvider


@dataclass(frozen=True)
class ContentPackage:
    topic: str
    strategy: ContentStrategy
    pinterest: dict[str, str | list[str]]
    scores: ContentScores
    local_editorial_angle: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class ContentPipelineController:
    """Coordinates the complete, zero-cost Pinterest content workflow."""

    def __init__(
        self,
        idea_generator: IdeaGenerator | None = None,
        pinterest_formatter: PinterestFormatter | None = None,
        scoring_engine: ContentScoringEngine | None = None,
        local_llm_provider: LocalLLMProvider | None = None,
    ):
        self.idea_generator = idea_generator or IdeaGenerator()
        self.pinterest_formatter = pinterest_formatter or PinterestFormatter()
        self.scoring_engine = scoring_engine or ContentScoringEngine()
        self.local_llm_provider = local_llm_provider

    def create_content_package(self, topic: str) -> ContentPackage:
        strategy = self.idea_generator.generate(topic)
        pinterest_content = self.pinterest_formatter.format(strategy)
        scores = self.scoring_engine.score(strategy)

        return ContentPackage(
            topic=topic,
            strategy=strategy,
            pinterest=pinterest_content,
            scores=scores,
            local_editorial_angle=self._generate_local_editorial_angle(strategy),
        )

    def _generate_local_editorial_angle(self, strategy: ContentStrategy) -> str | None:
        if not self.local_llm_provider:
            return None

        prompt = (
            "Give one concise, audience-friendly editorial angle for this Pinterest topic. "
            f"Title: {strategy.title}\nHook: {strategy.hook}"
        )
        try:
            return self.local_llm_provider.generate_text(prompt)
        except RuntimeError as error:
            print(f"Local LLM unavailable; continuing without an editorial angle: {error}")
            return None

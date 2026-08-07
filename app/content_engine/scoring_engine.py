from dataclasses import dataclass

from app.content_engine.content_strategy import ContentStrategy


@dataclass(frozen=True)
class ContentScores:
    curiosity: int
    emotional_impact: int
    shareability: int


class ContentScoringEngine:
    """Scores content with transparent, deterministic editorial heuristics."""

    def score(self, strategy: ContentStrategy) -> ContentScores:
        title_and_hook = f"{strategy.title} {strategy.hook}".casefold()
        curiosity = 7 + int("?" in strategy.title) + int("how" in title_and_hook)
        emotional_impact = 6 + int("human" in title_and_hook) + int("imagine" in title_and_hook)
        shareability = 7 + int(len(strategy.pinterest_keywords) >= 4) + int("visual" in title_and_hook)

        return ContentScores(
            curiosity=min(curiosity, 10),
            emotional_impact=min(emotional_impact, 10),
            shareability=min(shareability, 10),
        )

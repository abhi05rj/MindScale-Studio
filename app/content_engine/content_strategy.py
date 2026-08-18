from dataclasses import dataclass

from app.content_engine.content_quality import editorial_variant, format_pattern_text, pattern_for


@dataclass(frozen=True)
class ContentStrategy:
    category: str
    title: str
    hook: str
    story_structure: dict[str, str]
    audience: str
    visual_direction: str
    pinterest_keywords: tuple[str, ...]


class ContentStrategyEngine:
    """Builds deterministic, reusable content strategies from a topic."""

    def create_strategy(self, topic: str) -> ContentStrategy:
        normalized_topic = topic.strip()
        if not normalized_topic:
            raise ValueError("A topic is required to create a content strategy.")

        pattern = pattern_for(normalized_topic)
        variant = editorial_variant(normalized_topic, pattern)
        keyword_topic = normalized_topic.casefold()
        return ContentStrategy(
            category="Curiosity-Driven Visual Education",
            title=variant.title,
            hook=variant.hook,
            story_structure={
                "opening": format_pattern_text(pattern.opening, normalized_topic),
                "escalation": format_pattern_text(pattern.escalation, normalized_topic),
                "takeaway": format_pattern_text(pattern.takeaway, normalized_topic),
            },
            audience="Curious learners who save and share clear visual explanations.",
            visual_direction=format_pattern_text(pattern.visual_direction, normalized_topic),
            pinterest_keywords=(
                keyword_topic,
                f"{keyword_topic} facts",
                f"how {keyword_topic} works",
                f"{pattern.name} infographic",
                "educational infographic",
                "visual learning",
            ),
        )

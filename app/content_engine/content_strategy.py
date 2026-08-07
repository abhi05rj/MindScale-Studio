from dataclasses import dataclass


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

    _TOPIC_STRATEGIES = {
        "universe": {
            "category": "Space & Science",
            "title": "How Small Are Humans Compared to the Universe?",
            "hook": "A human is smaller compared to the universe than we can imagine.",
            "story_structure": {
                "opening": "Start with one person standing beneath a star-filled sky.",
                "escalation": "Zoom out from Earth to the Solar System, Milky Way, and observable universe.",
                "takeaway": "End by showing that our small place makes curiosity matter even more.",
            },
            "audience": "Curious learners, science fans, and visual education audiences.",
            "visual_direction": "Human → Earth → Solar System → Milky Way → Observable Universe",
            "pinterest_keywords": (
                "universe facts",
                "space science",
                "cosmic scale",
                "astronomy for beginners",
                "educational infographic",
            ),
        }
    }

    def create_strategy(self, topic: str) -> ContentStrategy:
        normalized_topic = topic.strip()
        if not normalized_topic:
            raise ValueError("A topic is required to create a content strategy.")

        template = self._TOPIC_STRATEGIES.get(normalized_topic.casefold())
        if template:
            return ContentStrategy(**template)

        title_topic = normalized_topic.title()
        return ContentStrategy(
            category="Educational Storytelling",
            title=f"What Makes {title_topic} So Fascinating?",
            hook=f"There is more to {normalized_topic} than most people realize.",
            story_structure={
                "opening": f"Introduce a surprising fact about {normalized_topic}.",
                "escalation": f"Break {normalized_topic} into three clear visual moments.",
                "takeaway": "Finish with one memorable perspective the audience can share.",
            },
            audience="Curious learners and visual education audiences.",
            visual_direction=f"Simple visual journey explaining {normalized_topic}",
            pinterest_keywords=(
                normalized_topic.casefold(),
                f"{normalized_topic.casefold()} facts",
                "educational infographic",
                "visual learning",
            ),
        )

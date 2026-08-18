from app.content_engine.content_strategy import ContentStrategy
from app.content_engine.content_quality import rewrite_generic_title


class PinterestFormatter:
    def format(self, strategy: ContentStrategy) -> dict[str, str | list[str]]:
        topic = strategy.pinterest_keywords[0]
        title = rewrite_generic_title(strategy.title, topic)
        hashtags = [
            f"#{''.join(character for character in keyword.title() if character.isalnum())}"
            for keyword in strategy.pinterest_keywords[:6]
        ]
        keywords = ", ".join(strategy.pinterest_keywords[:3])
        description = (
            f"{strategy.hook} Discover {keywords} through a visual story that turns the idea "
            f"into a clear, memorable mental model. Save this {topic} explainer for your next "
            "curiosity deep dive, or share it with someone who loves seeing familiar ideas differently."
        )
        image_prompt = (
            f"Pinterest vertical 2:3 visual story about {topic}. {strategy.visual_direction}. "
            f"Opening visual: {strategy.story_structure['opening']} "
            f"Visual progression: {strategy.story_structure['escalation']} "
            "Create one dominant focal subject, clear foreground/midground/background separation, "
            "strong scale cues, intentional negative space for title overlay, cinematic natural light, "
            "cohesive editorial color palette, premium educational illustration, no text, no labels, "
            "no logos, no watermark."
        )

        return {
            "pinterest_title": title,
            "pinterest_description": description,
            "hashtags": hashtags,
            "image_prompt": image_prompt,
        }

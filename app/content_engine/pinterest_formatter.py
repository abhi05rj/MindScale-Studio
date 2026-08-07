from app.content_engine.content_strategy import ContentStrategy


class PinterestFormatter:
    def format(self, strategy: ContentStrategy) -> dict[str, str | list[str]]:
        hashtags = [f"#{keyword.replace(' ', '')}" for keyword in strategy.pinterest_keywords]
        description = (
            f"{strategy.hook} Explore {strategy.title.lower()} with this clear visual guide. "
            f"Perfect for curious minds who love {', '.join(strategy.pinterest_keywords[:3])}."
        )
        image_prompt = (
            f"Pinterest vertical 2:3 educational illustration. {strategy.visual_direction}. "
            "Clean modern infographic layout, cinematic soft lighting, inspiring colors, "
            "premium editorial quality, no text."
        )

        return {
            "pinterest_title": strategy.title,
            "pinterest_description": description,
            "hashtags": hashtags,
            "image_prompt": image_prompt,
        }

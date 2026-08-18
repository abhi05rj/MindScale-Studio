from dataclasses import dataclass
import re

from app.content_engine.content_quality import is_generic_title
from app.content_engine.content_strategy import ContentStrategy


@dataclass(frozen=True)
class ContentScores:
    curiosity: int
    specificity: int
    novelty: int
    emotional_impact: int
    shareability: int
    visual_storytelling: int
    overall: int


class ContentScoringEngine:
    """Scores content with transparent, deterministic editorial heuristics."""

    def score(self, strategy: ContentStrategy) -> ContentScores:
        title_and_hook = f"{strategy.title} {strategy.hook}".casefold()
        complete_text = " ".join(
            (
                title_and_hook,
                strategy.visual_direction.casefold(),
                " ".join(strategy.story_structure.values()).casefold(),
            )
        )
        generic = is_generic_title(strategy.title) or any(
            phrase in title_and_hook
            for phrase in ("more than most people realize", "interesting facts", "learn about")
        )

        curiosity = 3
        curiosity += int("?" in strategy.title)
        curiosity += 2 * int(
            any(signal in title_and_hook for signal in ("what if", "hidden", "sounds wrong", "really"))
        )
        curiosity += int(any(signal in title_and_hook for signal in ("how", "why", "where")))
        curiosity += int("but" in title_and_hook or "—" in strategy.title)

        specificity = 3
        specificity += 2 * int(bool(re.search(r"\b\d+", complete_text)))
        specificity += int(any(word in complete_text for word in ("three", "five", "ratio", "stage")))
        specificity += int(len(strategy.story_structure) >= 3)
        specificity += int(len(strategy.pinterest_keywords) >= 5)

        novelty = 4
        novelty += 2 * int(
            any(
                signal in complete_text
                for signal in (
                    "counterintuitive",
                    "thought experiment",
                    "hidden mechanism",
                    "turning points",
                    "transition zone",
                    "hiding in plain sight",
                )
            )
        )
        novelty += int("misconception" in complete_text or "assumption" in complete_text)
        novelty += int("cause-and-effect" in complete_text or "transformation" in complete_text)

        emotional_impact = 4
        emotional_impact += int(
            any(word in title_and_hook for word in ("you", "we", "human", "imagine"))
        )
        emotional_impact += int(
            any(word in complete_text for word in ("consequence", "stakes", "impossible", "surprising"))
        )
        emotional_impact += int("everyday" in complete_text or "familiar" in complete_text)

        shareability = 4
        shareability += int(len(strategy.pinterest_keywords) >= 5)
        shareability += int(
            any(word in complete_text for word in ("steps", "points", "guide", "remember"))
        )
        shareability += int(
            any(word in complete_text for word in ("repeat", "share", "spot", "observation prompt"))
        )
        shareability += int(bool(re.search(r"\b\d+", strategy.title)))

        visual_storytelling = 4
        visual_storytelling += sum(
            int(signal in strategy.visual_direction.casefold())
            for signal in (
                "foreground",
                "split-screen",
                "triptych",
                "cutaway",
                "timeline",
                "vignettes",
                "threshold",
            )
        )
        visual_storytelling += int(
            any(word in strategy.visual_direction.casefold() for word in ("contrast", "progression", "flow"))
        )
        visual_storytelling += int(len(strategy.story_structure) >= 3)

        values = [
            curiosity,
            specificity,
            novelty,
            emotional_impact,
            shareability,
            visual_storytelling,
        ]
        if generic:
            values = [value - 2 for value in values]
        values = [max(1, min(value, 10)) for value in values]

        return ContentScores(
            curiosity=values[0],
            specificity=values[1],
            novelty=values[2],
            emotional_impact=values[3],
            shareability=values[4],
            visual_storytelling=values[5],
            overall=round(sum(values) / len(values)),
        )

import tempfile
import unittest
from datetime import date
from pathlib import Path

from app.content_engine import (
    ContentScoringEngine,
    ContentStrategy,
    ContentStrategyEngine,
    PinterestFormatter,
)
from app.content_engine.content_quality import is_generic_title
from app.planning import ContentPlanner, WeeklyPlanStorage
from app.planning import ContentPillar


class ContentQualityTests(unittest.TestCase):
    def test_generic_fallback_title_is_rewritten(self):
        weak = ContentStrategy(
            category="Education",
            title="What Makes Ocean So Fascinating?",
            hook="There is more to ocean than most people realize.",
            story_structure={
                "opening": "Introduce ocean.",
                "escalation": "Explain ocean.",
                "takeaway": "Remember ocean.",
            },
            audience="Everyone",
            visual_direction="Simple visual journey explaining ocean",
            pinterest_keywords=("ocean", "ocean facts", "visual learning"),
        )

        formatted = PinterestFormatter().format(weak)

        self.assertFalse(is_generic_title(formatted["pinterest_title"]))
        self.assertNotEqual(formatted["pinterest_title"], weak.title)

    def test_weak_generic_content_scores_below_strong_specific_content(self):
        weak = ContentStrategy(
            category="Education",
            title="What Makes Nature So Fascinating?",
            hook="There is more to nature than most people realize.",
            story_structure={"opening": "Start.", "escalation": "Explain.", "takeaway": "End."},
            audience="Everyone",
            visual_direction="Simple visual",
            pinterest_keywords=("nature", "facts"),
        )
        strong = ContentStrategyEngine().create_strategy("Nature")
        scorer = ContentScoringEngine()

        weak_scores = scorer.score(weak)
        strong_scores = scorer.score(strong)

        self.assertLess(weak_scores.overall, strong_scores.overall)
        self.assertLess(weak_scores.curiosity, strong_scores.curiosity)
        self.assertLess(weak_scores.specificity, strong_scores.specificity)
        self.assertLess(weak_scores.novelty, strong_scores.novelty)
        self.assertLess(weak_scores.visual_storytelling, strong_scores.visual_storytelling)

    def test_default_week_uses_at_least_five_distinct_angle_patterns(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = ContentPlanner(
                storage=WeeklyPlanStorage(root / "plans"),
                content_history_directory=root / "history",
            ).create_weekly_plan(date(2026, 8, 26))

        titles = [day.working_title for day in plan.days]
        angles = [day.content_angle.split(":", 1)[0] for day in plan.days]
        self.assertEqual(len(set(angles)), 7)
        self.assertTrue(all(not is_generic_title(title) for title in titles))

    def test_quality_gate_rewrites_once_and_marks_subthreshold_ideas_for_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = ContentPlanner(
                storage=WeeklyPlanStorage(root / "plans"),
                content_history_directory=root / "history",
            ).create_weekly_plan(date(2026, 8, 26))

        self.assertTrue(any(day.quality_rewritten for day in plan.days))
        for day in plan.days:
            expected = "planned" if day.quality_score >= 6 else "needs_review"
            self.assertEqual(day.status, expected)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            unprofiled = ContentPlanner(
                pillars=(ContentPillar.generic("Abstract"), ContentPillar.generic("Concept")),
                storage=WeeklyPlanStorage(root / "plans"),
                content_history_directory=root / "history",
            ).create_weekly_plan(date(2026, 8, 26))
        self.assertTrue(any(day.status == "needs_review" for day in unprofiled.days))

    def test_pinterest_copy_uses_keywords_and_save_share_language(self):
        strategy = ContentStrategyEngine().create_strategy("Brain")

        formatted = PinterestFormatter().format(strategy)

        description = formatted["pinterest_description"].casefold()
        self.assertIn("brain facts", description)
        self.assertIn("save", description)
        self.assertIn("share", description)
        self.assertLessEqual(len(formatted["pinterest_description"]), 500)
        self.assertIn("foreground/midground/background", formatted["image_prompt"])
        self.assertIn("no text", formatted["image_prompt"])

    def test_generated_strategies_have_six_differentiated_quality_dimensions(self):
        scores = ContentScoringEngine().score(ContentStrategyEngine().create_strategy("Time"))

        for field in (
            "curiosity",
            "specificity",
            "novelty",
            "emotional_impact",
            "shareability",
            "visual_storytelling",
        ):
            self.assertGreaterEqual(getattr(scores, field), 1)
            self.assertLessEqual(getattr(scores, field), 10)
        self.assertGreaterEqual(scores.overall, 1)
        self.assertLessEqual(scores.overall, 10)


if __name__ == "__main__":
    unittest.main()

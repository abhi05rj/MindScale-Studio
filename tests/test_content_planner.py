import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from app.planning import (
    ContentPillar,
    ContentPlanner,
    DuplicateWeeklyPlanError,
    WeeklyPlanStorage,
)


class ContentPlannerTests(unittest.TestCase):
    start_date = date(2026, 8, 19)
    fixed_time = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)

    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.plan_directory = self.root / ".local-runtime" / "plans"
        self.history_directory = self.root / "content_packages"
        self.storage = WeeklyPlanStorage(self.plan_directory)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def planner(self, **overrides):
        options = {
            "storage": self.storage,
            "content_history_directory": self.history_directory,
            "clock": lambda: self.fixed_time,
        }
        options.update(overrides)
        return ContentPlanner(**options)

    def test_generates_exactly_seven_complete_consecutive_planned_days(self):
        plan = self.planner().create_weekly_plan(self.start_date)

        self.assertEqual(plan.start_date, "2026-08-19")
        self.assertEqual(plan.created_at, "2026-08-17T12:00:00+00:00")
        self.assertEqual(plan.status, "planned")
        self.assertEqual(len(plan.days), 7)
        self.assertEqual(plan.days[0].publish_date, "2026-08-19")
        self.assertEqual(plan.days[-1].publish_date, "2026-08-25")
        for day in plan.days:
            self.assertTrue(day.topic)
            self.assertTrue(day.working_title)
            self.assertTrue(day.content_angle)
            self.assertTrue(day.objective)
            self.assertTrue(day.hook)
            self.assertIsNotNone(day.quality_score)
            self.assertIn(day.status, {"planned", "needs_review"})

    def test_configurable_pillars_never_repeat_on_consecutive_days(self):
        pillars = (ContentPillar.generic("Science"), ContentPillar.generic("Mindfulness"))
        plan = self.planner(pillars=pillars).create_weekly_plan(self.start_date)
        topics = [day.topic for day in plan.days]

        self.assertEqual(set(topics), {"Science", "Mindfulness"})
        self.assertTrue(all(first != second for first, second in zip(topics, topics[1:])))

    def test_avoids_titles_and_angles_found_in_recent_content_history(self):
        baseline_storage = WeeklyPlanStorage(self.root / "baseline")
        baseline = self.planner(storage=baseline_storage).create_weekly_plan(self.start_date)
        self.history_directory.mkdir()
        for index, day in enumerate(baseline.days):
            record = {
                "publish_date": f"2026-08-{10 + index:02d}",
                "content_package": {
                    "strategy": {"title": day.working_title, "hook": day.hook},
                    "local_editorial_angle": day.content_angle,
                },
            }
            (self.history_directory / f"history-{index}.json").write_text(
                json.dumps(record), encoding="utf-8"
            )

        planned = self.planner().create_weekly_plan(self.start_date)

        old_titles = {day.working_title.casefold() for day in baseline.days}
        old_hooks = {day.hook.casefold() for day in baseline.days}
        self.assertTrue(all(day.working_title.casefold() not in old_titles for day in planned.days))
        self.assertTrue(all(day.hook.casefold() not in old_hooks for day in planned.days))

    def test_plan_is_persisted_as_local_json(self):
        plan = self.planner().create_weekly_plan(self.start_date)
        path = self.storage.path_for(self.start_date)

        self.assertTrue(path.is_file())
        document = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(document["start_date"], plan.start_date)
        self.assertEqual(len(document["days"]), 7)

    def test_new_planner_instance_reloads_the_identical_plan(self):
        original = self.planner().create_weekly_plan(self.start_date)
        reloaded_planner = ContentPlanner(
            storage=WeeklyPlanStorage(self.plan_directory),
            content_history_directory=self.history_directory,
        )

        self.assertEqual(reloaded_planner.show_weekly_plan(self.start_date), original)

    def test_duplicate_weekly_plan_is_rejected(self):
        planner = self.planner()
        planner.create_weekly_plan(self.start_date)

        with self.assertRaises(DuplicateWeeklyPlanError):
            planner.create_weekly_plan(self.start_date)

    def test_explicit_replace_regenerates_the_plan(self):
        original = self.planner().create_weekly_plan(self.start_date)
        replacement_pillars = (
            ContentPillar.generic("Learning"),
            ContentPillar.generic("Creativity"),
            ContentPillar.generic("Wellbeing"),
        )
        replacement = self.planner(pillars=replacement_pillars).create_weekly_plan(
            self.start_date, replace=True
        )

        self.assertNotEqual([day.topic for day in replacement.days], [day.topic for day in original.days])
        self.assertEqual(self.storage.load(self.start_date), replacement)
        self.assertEqual(len(list(self.plan_directory.glob("*.json"))), 1)


if __name__ == "__main__":
    unittest.main()

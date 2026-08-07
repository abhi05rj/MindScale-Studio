import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from app.automation_runner import run_daily_automation
from app.content_engine import ContentCalendarEngine, ContentStorage


class AutomationRunnerTests(unittest.TestCase):
    def test_generates_saves_and_then_no_ops_for_the_same_date(self):
        run_date = date(2026, 8, 8)

        with tempfile.TemporaryDirectory() as directory:
            storage = ContentStorage(Path(directory))
            engine = ContentCalendarEngine(content_storage=storage)
            first_logs = []

            first_exit_code = run_daily_automation(run_date, engine, first_logs.append)

            saved_files = list(Path(directory).glob("*.json"))
            self.assertEqual(first_exit_code, 0)
            self.assertEqual(len(saved_files), 1)
            self.assertTrue(any(line.startswith("START") for line in first_logs))
            self.assertTrue(any(line.startswith("SELECTED TOPIC:") for line in first_logs))
            self.assertTrue(any(line.startswith("GENERATED CONTENT:") for line in first_logs))
            self.assertTrue(any(line.startswith("SAVED CONTENT:") for line in first_logs))
            self.assertTrue(first_logs[-1].startswith("COMPLETE"))

            record = json.loads(saved_files[0].read_text(encoding="utf-8"))
            self.assertEqual(record["publish_date"], run_date.isoformat())
            self.assertIn("pinterest_title", record["content_package"]["pinterest"])

            second_logs = []
            second_exit_code = run_daily_automation(run_date, engine, second_logs.append)

            self.assertEqual(second_exit_code, 0)
            self.assertEqual(len(list(Path(directory).glob("*.json"))), 1)
            self.assertTrue(any(line.startswith("DUPLICATE/NO-OP") for line in second_logs))
            self.assertTrue(second_logs[-1].startswith("COMPLETE"))

    def test_logs_errors_and_returns_failure(self):
        class FailingEngine:
            def __init__(self, storage):
                self.content_storage = storage

            def select_topic(self, publish_date):
                raise RuntimeError("topic selection failed")

        with tempfile.TemporaryDirectory() as directory:
            logs = []
            exit_code = run_daily_automation(
                date(2026, 8, 8),
                FailingEngine(ContentStorage(Path(directory))),
                logs.append,
            )

        self.assertEqual(exit_code, 1)
        self.assertIn("ERROR daily content automation: topic selection failed", logs)
        self.assertEqual(logs[-1], "COMPLETE daily content automation (failed)")


if __name__ == "__main__":
    unittest.main()

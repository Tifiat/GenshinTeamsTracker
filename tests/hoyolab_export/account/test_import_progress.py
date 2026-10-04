"""Progress reports completed work, including concurrent phases and failures."""
import unittest
from concurrent.futures import ThreadPoolExecutor

from hoyolab_export.import_progress import ImportProgress


class ImportProgressTest(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.clock = 0
        self.progress = ImportProgress("attempt", emit=self.events.append, clock=lambda: self.clock)

    def test_account_commit_reserves_room_for_unfinished_jobs(self):
        self.progress.update("assets", "download", 0, 100)
        self.assertAlmostEqual(self.events[-1]["progress"], .20)
        self.clock = 1000
        self.progress.update("assets", "download", 0, 100)
        self.assertAlmostEqual(self.events[-1]["progress"], .20)
        self.assertEqual(self.events[-1]["jobs"]["abyss"]["state"], "waiting")

    def test_overlapping_phases_keep_both_counters_and_ignore_late_counts(self):
        self.progress.update("abyss", "hp", 2, 10)
        self.progress.update("abyss", "icons", 5, 20)
        first = self.events[-1]["progress"]
        self.progress.update("abyss", "hp", 1, 10)
        steps = self.events[-1]["jobs"]["abyss"]["steps"]
        self.assertEqual(steps["hp"]["completed"], 2)
        self.assertEqual(steps["icons"]["completed"], 5)
        self.assertGreaterEqual(self.events[-1]["progress"], first)

    def test_terminal_states_survive_late_callbacks_and_never_claim_success_for_failures(self):
        self.progress.finish("assets", pending=True)
        self.progress.update("assets", "render", 4, 10)
        self.assertEqual(self.events[-1]["jobs"]["assets"]["state"], "pending")
        self.assertLess(self.events[-1]["progress"], .98)
        for kind in self.progress.jobs:
            if kind != "assets":
                self.progress.finish(kind)
        self.assertAlmostEqual(self.events[-1]["progress"], .98)

    def test_concurrent_reports_are_bounded_monotonic_and_observational(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda count: self.progress.update("assets", "download", count, 100), range(101)))
        self.progress.finish("assets")
        self.assertLessEqual(len(self.events), 2)
        self.assertEqual(self.events[-1]["jobs"]["assets"]["completed"], 100)
        self.assertEqual([e["progress"] for e in self.events], sorted(e["progress"] for e in self.events))
        broken = ImportProgress("attempt", emit=lambda payload: 1 / 0)
        broken.update("assets", "download", 0, 1)
        broken.finish("assets")

    def test_images_only_counts_only_image_work(self):
        progress = ImportProgress(None, images_only=True, emit=self.events.append)
        progress.finish("assets")
        self.assertEqual(set(self.events[-1]["jobs"]), {"assets"})
        self.assertAlmostEqual(self.events[-1]["progress"], .98)

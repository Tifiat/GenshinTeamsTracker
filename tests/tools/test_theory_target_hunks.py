"""Exact-context relocation fixtures; no optimizer or engine calls."""
from __future__ import annotations

import unittest

from tools.experiments.gcsim.theory_release import package_io
from tools.experiments.gcsim.theory_release.target_hunks import relocate_hunks


class TargetHunkTests(unittest.TestCase):
    def test_shifted_hunk_preserves_target_only_lines(self) -> None:
        before = b"".join(f"line-{index:02}\n".encode() for index in range(16))
        after = before.replace(b"line-07\n", b"changed\n")
        patch = package_io.make_patch("src/a.txt", before, after)
        target = b"target-prefix\n" + before + b"target-suffix\n"

        actual, audit = relocate_hunks("src/a.txt", before, target, patch)

        self.assertEqual(actual, b"target-prefix\n" + after + b"target-suffix\n")
        self.assertEqual(audit[0]["target_offset"], 5)
        self.assertEqual(audit[0]["status"], "applied")
        self.assertFalse(audit[0]["override"])

    def test_override_keeps_added_target_guard_on_both_sides(self) -> None:
        before = b"before\nold value\nafter\n"
        after = b"before\nnew value\nafter\n"
        patch = package_io.make_patch("src/a.txt", before, after)
        target = b"before\ntarget guard\nold value\nafter\n"
        override = {
            1: (
                "before\ntarget guard\nold value\nafter\n",
                "before\ntarget guard\nnew value\nafter\n",
            )
        }

        actual, audit = relocate_hunks("src/a.txt", before, target, patch, override)

        self.assertEqual(actual, b"before\ntarget guard\nnew value\nafter\n")
        self.assertEqual(audit[0]["resolved_old_sha"], package_io.sha_bytes(override[1][0].encode()))
        self.assertTrue(audit[0]["override"])

    def test_new_file_creation_and_already_after_are_explicit(self) -> None:
        after = b"created\nfile\n"
        patch = package_io.make_patch("src/new.txt", b"", after)

        created, created_audit = relocate_hunks("src/new.txt", b"", b"", patch)
        already, already_audit = relocate_hunks("src/new.txt", b"", after, patch)

        self.assertEqual(created, after)
        self.assertEqual(created_audit[0]["status"], "applied")
        self.assertEqual(already, after)
        self.assertEqual(already_audit[0]["status"], "already_after")
        with self.assertRaises(ValueError):
            relocate_hunks("src/new.txt", b"", b"", patch, {1: ("guard\n", "created\nguard\n")})

    def test_creation_collision_and_path_safety_fail(self) -> None:
        patch = package_io.make_patch("safe/new.txt", b"", b"created\n")
        with self.assertRaises(ValueError):
            relocate_hunks("safe/new.txt", b"", b"shadow\n", patch)
        with self.assertRaises(ValueError):
            relocate_hunks("../outside.txt", b"", b"", patch)
        with self.assertRaises(ValueError):
            relocate_hunks("different.txt", b"", b"", patch)

    def test_malformed_patch_and_missing_or_ambiguous_context_fail(self) -> None:
        before, after = b"before\nold\nafter\n", b"before\nnew\nafter\n"
        patch = package_io.make_patch("src/a.txt", before, after)
        malformed = patch.replace(" before\n", " changed-context\n")
        with self.assertRaises(ValueError):
            relocate_hunks("src/a.txt", before, before, malformed)
        with self.assertRaises(ValueError):
            relocate_hunks("src/a.txt", before, b"unrelated\n", patch)
        with self.assertRaises(ValueError):
            relocate_hunks("src/a.txt", before, before + b"gap\n" + before, patch)

    def test_override_rejects_context_drift_and_changed_intent(self) -> None:
        before, after = b"before\nold\nafter\n", b"before\nnew\nafter\n"
        patch = package_io.make_patch("src/a.txt", before, after)
        target = b"before\nguard\nold\nafter\n"
        drifted = {1: ("other\nguard\nold\nafter\n", "other\nguard\nnew\nafter\n")}
        changed = {1: ("before\nguard\nold\nafter\n", "before\nguard\nwrong\nafter\n")}
        with self.assertRaises(ValueError):
            relocate_hunks("src/a.txt", before, target, patch, drifted)
        with self.assertRaises(ValueError):
            relocate_hunks("src/a.txt", before, target, patch, changed)
        with self.assertRaises(ValueError):
            relocate_hunks("src/a.txt", before, target, patch, {2: ("x\n", "y\n")})

    def test_duplicate_override_entries_and_empty_context_are_rejected(self) -> None:
        before, after = b"before\nold\nafter\n", b"before\nnew\nafter\n"
        patch = package_io.make_patch("src/a.txt", before, after)

        class DuplicateOverrides(dict):
            def items(self):
                pair = ("before\nold\nafter\n", "before\nnew\nafter\n")
                return [(1, pair), (1, pair)]

        with self.assertRaises(ValueError):
            relocate_hunks("src/a.txt", before, before, patch, DuplicateOverrides())

        insertion = (
            "--- a/src/a.txt\n+++ b/src/a.txt\n"
            "@@ -1,0 +2,1 @@\n+inserted\n"
        )
        with self.assertRaises(ValueError):
            relocate_hunks("src/a.txt", b"anchor\n", b"anchor\n", insertion)

    def test_target_hunks_cannot_be_out_of_order_or_overlap(self) -> None:
        before = b"first-old\n" + b"".join(f"gap-{i}\n".encode() for i in range(8)) + b"last-old\n"
        patch = (
            "--- a/src/order.txt\n+++ b/src/order.txt\n"
            "@@ -1 +1 @@\n-first-old\n+first-new\n"
            "@@ -10 +10 @@\n-last-old\n+last-new\n"
        )
        with self.assertRaises(ValueError):
            relocate_hunks("src/order.txt", before, b"last-old\nfirst-old\n", patch)

        overlap_before = b"A\nB\n" + b"".join(f"gap-{i}\n".encode() for i in range(8)) + b"B\nC\n"
        overlap_patch = (
            "--- a/src/overlap.txt\n+++ b/src/overlap.txt\n"
            "@@ -1,2 +1,2 @@\n-A\n+X\n B\n"
            "@@ -11,2 +11,2 @@\n B\n-C\n+Y\n"
        )
        with self.assertRaises(ValueError):
            relocate_hunks("src/overlap.txt", overlap_before, b"A\nB\nC\n", overlap_patch)


if __name__ == "__main__":
    unittest.main()

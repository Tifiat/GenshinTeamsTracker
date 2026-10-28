"""Frozen package I/O checks; isolated fixtures, no optimizer or engine calls."""
from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.experiments.gcsim.theory_release import package_io
from tools.experiments.gcsim.theory_release.package_io import (
    _mkdir,
    apply_file_patch,
    export_git_files,
    make_patch,
    managed_job,
    materialize_from_manifest,
    safe_relative,
    sha_bytes,
)
from tools.experiments.gcsim.theory_release.release import optimizer_slot


class OptimizerSlotTests(unittest.TestCase):
    def test_permanent_lock_file_is_preserved_and_released(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).absolute()
            lock = root / ".gtt-active.lock"
            lock.write_bytes(b"0")
            for _ in range(2):
                with optimizer_slot(root):
                    self.assertEqual(lock.stat().st_size, 1)
                self.assertEqual(lock.read_bytes(), b"0")
            self.assertEqual(list(root.iterdir()), [lock])

    def test_real_leftover_and_bad_lease_block_without_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).absolute()
            lock = root / ".gtt-active.lock"
            lock.write_bytes(b"0")
            leftover = root / "job-unfinished"
            leftover.mkdir()
            with self.assertRaises(ValueError), optimizer_slot(root):
                self.fail("leftover accepted")
            self.assertTrue(leftover.is_dir())
            leftover.rmdir()
            lock.write_bytes(b"bad")
            with self.assertRaises(ValueError), optimizer_slot(root):
                self.fail("malformed lease accepted")
            self.assertEqual(lock.read_bytes(), b"bad")

    def test_existing_process_lease_prevents_overlap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).absolute()
            (root / ".gtt-active.lock").write_bytes(b"0")
            code = "import sys;from pathlib import Path;from tools.experiments.gcsim.theory_release.release import optimizer_slot;exec('try:\\n with optimizer_slot(Path(sys.argv[2])): pass\\nexcept OSError: sys.exit(0)\\nelse: sys.exit(7)')"
            assembly = str(Path(__file__).resolve().parents[2])
            code = "import sys;sys.path.insert(0,sys.argv[1]);" + code
            with optimizer_slot(root):
                result = subprocess.run([sys.executable, "-I", "-B", "-c", code, assembly, str(root)], capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))


class PatchTests(unittest.TestCase):
    def test_existing_ancestor_directories_are_never_recreated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(Path, "mkdir", side_effect=AssertionError("existing ancestor recreated")):
                _mkdir(Path(tmp).absolute())

    def test_exact_modify_create_and_unterminated_roundtrips(self) -> None:
        pairs = [
            (b"one\ntwo\n", "one\nтри\n".encode()),
            (b"", b"created\n"),
            (b"old", b"new"),
            (b"old\n", b"new"),
            (b"old", b"new\n"),
            (b"old\n", b""),
            (b"\n", b"\n\n"),
            ("a\u2028b\n".encode(), "a\u2028c\n".encode()),
        ]
        for before, after in pairs:
            with self.subTest(before=before, after=after):
                text = make_patch("src/a.go", before, after)
                self.assertNotIn("\r", text)
                self.assertEqual(apply_file_patch("src/a.go", before, text), after)
        before = b"".join(f"line {i}\n".encode() for i in range(30))
        after = before.replace(b"line 1\n", b"first change\n").replace(b"line 25\n", b"last change\n")
        text = make_patch("multi.txt", before, after)
        self.assertEqual(text.count("@@ -"), 2)
        self.assertEqual(apply_file_patch("multi.txt", before, text), after)
        self.assertEqual(sha_bytes(b"abc"), hashlib.sha256(b"abc").hexdigest())

    def test_paths_are_canonical_and_portable(self) -> None:
        self.assertEqual(safe_relative("folder with spaces/file.go"), PurePosixPath("folder with spaces/file.go"))
        for value in ("", "/outside", "C:/outside", "C:outside", "a\\b", "..", "a/../b", "./a",
                      "a//b", "a/", "a\nb", "a:stream", "NUL.txt", "dir./file"):
            with self.subTest(path=value), self.assertRaises(ValueError):
                safe_relative(value)

    def test_bad_context_missing_duplicate_truncated_and_extra_content_fail(self) -> None:
        before, after = b"one\ntwo\n", b"one\nthree\n"
        text = make_patch("a.txt", before, after)
        malformed = [
            text.replace(" one\n", " wrong\n"),
            "".join(text.splitlines(keepends=True)[:2]),
            text + text,
            text.replace("+three\n", ""),
            text.replace("--- a/a.txt", "--- a/other.txt"),
            text.replace("+++ b/a.txt", "+++ /dev/null"),
            text.replace("@@ -1,2 +1,2 @@", "@@ -1,1 +1,2 @@"),
            text + "diff --git a/hidden b/hidden\n",
            text.replace(" one\n", " one\n\\ No newline at end of file\n"),
            "GIT binary patch\n",
            text[:-1],
        ]
        for bad in malformed:
            with self.subTest(patch=bad), self.assertRaises(ValueError):
                apply_file_patch("a.txt", before, bad)
        with self.assertRaises(ValueError):
            make_patch("a.txt", before, before)
        for binary in (b"crlf\r\n", b"nul\x00\n", b"\xff"):
            with self.subTest(data=binary), self.assertRaises((ValueError, UnicodeError)):
                make_patch("a.txt", binary, after)


class BatchReadTests(unittest.TestCase):
    @staticmethod
    def object_id(data: bytes, algorithm: str = "sha1") -> str:
        return hashlib.new(algorithm, b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()

    def response(self, data: bytes, *, algorithm: str = "sha1") -> tuple[str, bytes]:
        blob = self.object_id(data, algorithm)
        return blob, f"{blob} blob {len(data)}\n".encode() + data + b"\n"

    def test_batch_parses_binary_empty_and_sha256_blobs_with_exact_framing(self) -> None:
        for algorithm in ("sha1", "sha256"):
            a, first = self.response(b"binary\0\nheader-like blob 100\n", algorithm=algorithm)
            b, second = self.response(b"", algorithm=algorithm)
            self.assertEqual(package_io._parse_blob_batch([a, b], first + second),
                             {a: b"binary\0\nheader-like blob 100\n", b: b""})

    def test_malformed_batch_identity_type_length_truncation_and_extra_bytes_fail(self) -> None:
        blob, good = self.response(b"abc")
        other, another = self.response(b"other")
        cases = [
            good.replace(b" blob ", b" tree ", 1),
            good.replace(blob.encode(), other.encode(), 1),
            good.replace(b" blob 3\n", b" blob 4\n", 1),
            good.replace(b" blob 3\n", b" blob 03\n", 1),
            good.replace(b"abc\n", b"xyz\n", 1),
            good.replace(blob.encode(), blob.upper().encode(), 1),
            good[:-2],
            good[:-1],
            good + another,
            blob.encode() + b" missing\n",
        ]
        for response in cases:
            with self.subTest(response=response), self.assertRaises(ValueError):
                package_io._parse_blob_batch([blob], response)
        with self.assertRaises(ValueError):
            package_io._parse_blob_batch([blob, other], another + good)
        with self.assertRaises(ValueError):
            package_io._parse_blob_batch([blob, blob], good + good)

    def test_many_declared_paths_use_one_metadata_read_and_one_unique_blob_batch(self) -> None:
        data = b"shared source\n"
        blob, batch = self.response(data)
        paths = [f"src/file-{n}.go" for n in range(128)]
        tree = b"".join(f"100644 blob {blob}\t{path}\0".encode() for path in paths)
        with patch.object(package_io, "_git", side_effect=[b"commit\n", tree, batch]) as read:
            files, records = package_io._base_files(Path.cwd().absolute(), "a" * 40, paths)
        self.assertEqual(set(files), set(paths))
        self.assertTrue(all(value == data for value in files.values()))
        self.assertTrue(all(row["base_git_blob"] == blob for row in records.values()))
        self.assertEqual(read.call_count, 3)
        self.assertEqual(read.call_args_list[1].args[1:4], ("ls-tree", "-r", "-z"))
        self.assertEqual(read.call_args_list[2].args[1:], ("cat-file", "--batch"))
        self.assertEqual(read.call_args_list[2].kwargs["input_data"], (blob + "\n").encode())

    def test_tree_metadata_rejects_truncation_duplicates_and_mode_type_mismatch(self) -> None:
        blob = self.object_id(b"abc")
        good = f"100644 blob {blob}\ta.txt\0".encode()
        self.assertEqual(package_io._parse_git_tree(good), {"a.txt": ("100644", "blob", blob)})
        for malformed in (good[:-1], good + good, good.replace(b"100644 blob", b"100644 commit"),
                          good.replace(b"\ta.txt", b"a.txt")):
            with self.subTest(metadata=malformed), self.assertRaises(ValueError):
                package_io._parse_git_tree(malformed)
        entries = package_io._parse_git_tree(good)
        self.assertIsNone(package_io._entry(entries, "missing.txt"))
        with self.assertRaises(ValueError):
            package_io._entry({"dir/a.txt": ("100644", "blob", blob)}, "dir")


@unittest.skipUnless(shutil.which("git"), "Git is required for isolated object fixtures")
class GitPackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="theory-package-io-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).absolute()
        self.repo, self.bundle = self.root / "repo", self.root / "bundle"
        self.repo.mkdir()
        self.bundle.mkdir()
        self.git("init", "-q")
        (self.repo / "a.txt").write_bytes(b"one\ntwo\n")
        (self.repo / "kept.txt").write_bytes(b"keep\n")
        self.git("add", "--", "a.txt", "kept.txt")
        self.commit()
        self.base = self.git("rev-parse", "HEAD").decode().strip()
        self.manifest = {
            "base_head": self.base,
            "base_files": [
                {"path": name, "sha256": sha_bytes(data), "git_blob": self.git("rev-parse", f"{self.base}:{name}").decode().strip()}
                for name, data in (("a.txt", b"one\ntwo\n"), ("kept.txt", b"keep\n"))
            ],
            "patches": [self.payload("a.txt", b"one\ntwo\n", b"one\nchanged\n"),
                        self.payload("new.txt", b"", b"frozen new\n")],
        }

    def git(self, *args: str) -> bytes:
        return subprocess.run(["git", "-C", str(self.repo), *args], check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout

    def commit(self) -> None:
        self.git("-c", "user.name=Theory fixture", "-c", "user.email=fixture@example.invalid",
                 "-c", "commit.gpgSign=false", "-c", f"core.hooksPath={self.root / 'no-hooks'}",
                 "commit", "-qm", "isolated fixture")

    def payload(self, name: str, before: bytes, after: bytes) -> dict:
        relative = f"own/{name}.patch"
        target = self.bundle / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        data = make_patch(name, before, after).encode("utf-8")
        target.write_bytes(data)
        return {"path": name, "payload": relative, "payload_sha256": sha_bytes(data),
                "before_sha256": sha_bytes(before), "after_sha256": sha_bytes(after)}

    def test_export_and_materialize_ignore_dirty_live_source(self) -> None:
        (self.repo / "a.txt").write_bytes(b"dirty live text\n")
        (self.repo / "kept.txt").unlink()
        (self.repo / "new.txt").write_bytes(b"dirty untracked text\n")
        exported = self.root / "exported"
        rows = export_git_files(self.repo, self.base, ["a.txt", "kept.txt"], exported)
        self.assertEqual((exported / "a.txt").read_bytes(), b"one\ntwo\n")
        self.assertEqual((exported / "kept.txt").read_bytes(), b"keep\n")
        self.assertEqual(rows["a.txt"]["base_git_blob"], self.manifest["base_files"][0]["git_blob"])
        dest = self.root / "assembled"
        rows = materialize_from_manifest(self.repo, self.manifest, self.bundle, dest)
        self.assertEqual((dest / "a.txt").read_bytes(), b"one\nchanged\n")
        self.assertEqual((dest / "new.txt").read_bytes(), b"frozen new\n")
        self.assertEqual((dest / "kept.txt").read_bytes(), b"keep\n")
        self.assertEqual(set(rows), {"a.txt", "kept.txt", "new.txt"})
        self.assertEqual(rows["new.txt"]["base_bytes"], 0)
        self.assertEqual(rows["a.txt"]["after_sha256"], sha_bytes(b"one\nchanged\n"))

    def test_manifest_failures_are_detected_before_destination_writes(self) -> None:
        cases = []
        for scope, field in (("patches", "payload_sha256"), ("patches", "before_sha256"),
                             ("patches", "after_sha256"), ("base_files", "sha256")):
            value = deepcopy(self.manifest)
            value[scope][0][field] = "0" * 64
            cases.append(value)
        value = deepcopy(self.manifest)
        value["base_files"][0]["git_blob"] = "0" * 40
        cases.append(value)
        for scope in ("base_files", "patches"):
            value = deepcopy(self.manifest)
            value[scope].append(deepcopy(value[scope][0]))
            cases.append(value)
        value = deepcopy(self.manifest)
        value["patches"][1]["payload"] = value["patches"][0]["payload"]
        cases.append(value)
        value = deepcopy(self.manifest)
        value["base_files"] = value["base_files"][1:]
        cases.append(value)
        value = deepcopy(self.manifest)
        value["patches"][0]["payload"] = "own/missing.patch"
        cases.append(value)
        value = deepcopy(self.manifest)
        del value["patches"][0]["after_sha256"]
        cases.append(value)
        for field in ("path", "payload"):
            value = deepcopy(self.manifest)
            value["patches"][0][field] = "../outside"
            cases.append(value)
        for scope, field, value_text in (("base_files", "path", "A.txt"),
                                         ("patches", "path", "A.txt"),
                                         ("patches", "payload", "own/A.txt.patch"),
                                         ("patches", "payload", "OWN/new.txt.patch")):
            value = deepcopy(self.manifest)
            if scope == "base_files":
                row = deepcopy(value[scope][0])
                row[field] = value_text
                value[scope].append(row)
            else:
                value[scope][1][field] = value_text
            cases.append(value)
        for i, value in enumerate(cases):
            dest = self.root / f"rejected-{i}"
            with self.subTest(case=i), self.assertRaises(ValueError):
                materialize_from_manifest(self.repo, value, self.bundle, dest)
            self.assertFalse(dest.exists())

    def test_unlisted_patch_content_cannot_pass_with_a_valid_payload_hash(self) -> None:
        value = deepcopy(self.manifest)
        row = value["patches"][0]
        target = self.bundle / row["payload"]
        data = target.read_bytes() + make_patch("hidden.txt", b"", b"hidden\n").encode()
        target.write_bytes(data)
        row["payload_sha256"] = sha_bytes(data)
        dest = self.root / "rejected-extra"
        with self.assertRaises(ValueError):
            materialize_from_manifest(self.repo, value, self.bundle, dest)
        self.assertFalse(dest.exists())

    def test_bundle_inventory_rejects_extra_omitted_and_empty_unlisted_directories(self) -> None:
        extra = self.bundle / "extra.patch"
        extra.write_bytes(b"unlisted bytes")
        with self.assertRaises(ValueError):
            materialize_from_manifest(self.repo, self.manifest, self.bundle, self.root / "extra-output")
        extra.unlink()
        extra_directory = self.bundle / "empty-unlisted"
        extra_directory.mkdir()
        with self.assertRaises(ValueError):
            materialize_from_manifest(self.repo, self.manifest, self.bundle, self.root / "extra-directory-output")
        extra_directory.rmdir()
        (self.bundle / self.manifest["patches"][1]["payload"]).unlink()
        with self.assertRaises(ValueError):
            materialize_from_manifest(self.repo, self.manifest, self.bundle, self.root / "omitted-output")
        self.assertFalse(any(self.root.glob("*-output")))

    def test_git_export_rejects_duplicate_missing_unsafe_and_executable_files(self) -> None:
        for paths in (["a.txt", "a.txt"], ["a.txt", "A.txt"], ["a.txt", "a.txt/child"],
                      ["missing.txt"], ["../a.txt"]):
            dest = self.root / "invalid-export"
            with self.subTest(paths=paths), self.assertRaises(ValueError):
                export_git_files(self.repo, self.base, paths, dest)
            self.assertFalse(dest.exists())
        self.git("update-index", "--chmod=+x", "a.txt")
        self.commit()
        executable_base = self.git("rev-parse", "HEAD").decode().strip()
        with self.assertRaises(ValueError):
            export_git_files(self.repo, executable_base, ["a.txt"], self.root / "executable-export")

    def link(self, path: Path, target: Path, *, directory: bool) -> None:
        try:
            path.symlink_to(target, target_is_directory=directory)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlinks unavailable: {exc}")

    def test_linked_bundle_and_destination_cannot_escape(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "sentinel").write_bytes(b"preserve\n")
        linked_dest = self.root / "linked-dest"
        self.link(linked_dest, outside, directory=True)
        with self.assertRaises(ValueError):
            materialize_from_manifest(self.repo, self.manifest, self.bundle, linked_dest)
        self.assertEqual(list(outside.iterdir()), [outside / "sentinel"])
        row = self.manifest["patches"][0]
        payload = self.bundle / row["payload"]
        frozen = outside / "frozen.patch"
        frozen.write_bytes(payload.read_bytes())
        payload.unlink()
        self.link(payload, frozen, directory=False)
        with self.assertRaises(ValueError):
            materialize_from_manifest(self.repo, self.manifest, self.bundle, self.root / "linked-payload-output")
        self.assertEqual((outside / "sentinel").read_bytes(), b"preserve\n")

    def test_linked_bundle_directory_is_rejected_without_reading_its_contents(self) -> None:
        outside = self.root / "outside-directory"
        outside.mkdir()
        (outside / "sentinel").write_bytes(b"preserve\n")
        self.link(self.bundle / "linked-extra", outside, directory=True)
        with self.assertRaises(ValueError):
            materialize_from_manifest(self.repo, self.manifest, self.bundle, self.root / "linked-directory-output")
        self.assertFalse((self.root / "linked-directory-output").exists())
        self.assertEqual((outside / "sentinel").read_bytes(), b"preserve\n")


class ManagedJobTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="theory-owned-job-")
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name).absolute()
        self.root = self.parent / "scratch"
        self.sibling = self.parent / "sibling.txt"
        self.sibling.write_bytes(b"preserve sibling\n")

    def assert_clean(self, record: dict, expected_bytes: int) -> None:
        self.assertTrue(record["cleaned"])
        self.assertEqual(record["removed_bytes"], expected_bytes)
        self.assertEqual(list(self.root.iterdir()), [])
        self.assertEqual(self.sibling.read_bytes(), b"preserve sibling\n")

    def test_success_error_and_cancel_clean_owned_bytes_and_preserve_sibling(self) -> None:
        for failure in (None, RuntimeError("body failure"), KeyboardInterrupt()):
            record = None
            try:
                with managed_job(self.root) as record:
                    nested = record["path"] / "nested"
                    nested.mkdir()
                    (nested / "a.bin").write_bytes(b"abc")
                    (record["path"] / "b.bin").write_bytes(b"12345")
                    if failure is not None:
                        raise failure
            except BaseException as exc:
                self.assertIs(exc, failure)
            else:
                self.assertIsNone(failure)
            self.assert_clean(record, 8)

    def test_leftovers_and_concurrent_lease_block_without_removal(self) -> None:
        self.root.mkdir()
        leftover = self.root / "leftover"
        leftover.write_bytes(b"preserve leftover")
        with self.assertRaises(ValueError):
            with managed_job(self.root):
                self.fail("leftover scratch was reused")
        self.assertEqual(leftover.read_bytes(), b"preserve leftover")
        leftover.unlink()
        with managed_job(self.root) as record:
            with self.assertRaises(ValueError):
                with managed_job(self.root):
                    self.fail("concurrent scratch was reused")
        self.assert_clean(record, 0)

    def test_missing_job_blocks_cleanup_and_does_not_remove_outside_target(self) -> None:
        moved = self.parent / "moved-outside-root"
        with self.assertRaises(ValueError):
            with managed_job(self.root) as record:
                (record["path"] / "data").write_bytes(b"keep moved data")
                record["path"].rename(moved)
        self.assertFalse(record["cleaned"])
        self.assertEqual(record["removed_bytes"], 0)
        self.assertEqual((moved / "data").read_bytes(), b"keep moved data")
        with self.assertRaises(ValueError):
            with managed_job(self.root):
                self.fail("abandoned lease was reused")

    def test_changed_lease_blocks_cleanup_before_removal(self) -> None:
        with self.assertRaises(ValueError):
            with managed_job(self.root) as record:
                (record["path"] / "data").write_bytes(b"preserve owned data")
                (self.root / ".theory-release.lease").write_bytes(b"other owner\n")
        self.assertFalse(record["cleaned"])
        self.assertEqual((record["path"] / "data").read_bytes(), b"preserve owned data")
        self.assertEqual(record["removed_bytes"], 0)

    def test_linked_job_child_blocks_cleanup_and_preserves_outside_bytes(self) -> None:
        outside = self.parent / "outside"
        outside.mkdir()
        (outside / "data").write_bytes(b"preserve outside")
        with self.assertRaises(ValueError):
            with managed_job(self.root) as record:
                (record["path"] / "own").write_bytes(b"preserve until audited cleanup")
                try:
                    (record["path"] / "link").symlink_to(outside, target_is_directory=True)
                except (OSError, NotImplementedError) as exc:
                    self.skipTest(f"symlinks unavailable: {exc}")
        self.assertFalse(record["cleaned"])
        self.assertEqual(record["removed_bytes"], 0)
        self.assertEqual((outside / "data").read_bytes(), b"preserve outside")
        self.assertTrue((record["path"] / "own").exists())
        with self.assertRaises(ValueError):
            with managed_job(self.root):
                self.fail("linked residue was reused")

    def test_windows_reparse_attribute_is_rejected_before_root_creation(self) -> None:
        info = SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
        with patch.object(Path, "lstat", return_value=info), self.assertRaises(ValueError):
            with managed_job(self.root):
                self.fail("reparse root was allowed")
        self.assertFalse(self.root.exists())


if __name__ == "__main__":
    unittest.main()

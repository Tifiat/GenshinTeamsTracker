"""Transactional checks for the temporary search-schedule consumer install."""
from contextlib import ExitStack, redirect_stdout
import io
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.experiments.gcsim.parametric_effects import install_search_schedule as installer


class SearchScheduleInstallTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.consumer = self.root / "native/gcsim_optimizer/gtt-optimizer.exe"
        self.consumer.parent.mkdir(parents=True)
        self.original_consumer = b"installed optimizer before test"
        self.consumer.write_bytes(self.original_consumer)

        self.job = self.root / "scratch/job"
        self.job.mkdir(parents=True)
        self.candidate = self.job / "gtt-optimizer.exe"
        self.engine = SimpleNamespace(
            engine_id="gcsim-test-engine",
            artifact_sha256="a" * 64,
        )

        self.install_json = self.root / (
            "docs/optimizer-evidence/all-sets-inventory-20260919/install.json"
        )
        self.install_json.parent.mkdir(parents=True)
        self.original_install_json = b'{"owner":"original matrix install"}\n'
        self.install_json.write_bytes(self.original_install_json)
        self.real_copy2 = shutil.copy2

    def _fake_execute(self, *, candidate_bytes=b"new optimizer", fail=None, after_build=None):
        calls = []

        def execute(command, *, cwd, timeout):
            calls.append((command, cwd, timeout))
            if command[1] == "test":
                if fail == "test":
                    raise subprocess.CalledProcessError(1, command)
                return "native tests passed"
            if command[1] == "build":
                if fail == "build":
                    raise subprocess.CalledProcessError(1, command)
                output = Path(command[command.index("-o") + 1])
                output.write_bytes(candidate_bytes)
                if after_build is not None:
                    after_build()
                return "candidate built"
            self.fail(f"unexpected command: {command!r}")

        return execute, calls

    def _invoke(self, execute, *, active_contexts=None, copy2_side_effect=None, oracle_error=None):
        if active_contexts is None:
            active_contexts = [self.engine, self.engine]
        with ExitStack() as stack:
            stack.enter_context(patch.object(installer, "ROOT", self.root))
            stack.enter_context(patch.object(installer, "owned_job", return_value=self.job))
            stack.enter_context(patch.object(installer, "execute", side_effect=execute))
            stack.enter_context(patch.object(installer, "validate_active_source_oracle", side_effect=oracle_error))
            stack.enter_context(patch.object(
                installer, "load_active_gcsim_optimizer_engine_context",
                side_effect=active_contexts,
            ))
            stack.enter_context(patch.object(installer.shutil, "which", return_value="go-test-double"))
            if copy2_side_effect is not None:
                stack.enter_context(patch.object(
                    installer.shutil, "copy2", side_effect=copy2_side_effect,
                ))
            with redirect_stdout(io.StringIO()):
                return installer.main()

    def test_success_installs_candidate_and_preserves_unrelated_install_json(self):
        execute, _ = self._fake_execute(candidate_bytes=b"validated optimizer")

        self._invoke(execute)

        self.assertEqual(self.consumer.read_bytes(), b"validated optimizer")
        self.assertEqual(self.install_json.read_bytes(), self.original_install_json)

    def test_native_or_build_failure_leaves_consumer_unchanged(self):
        for failing_command in ("test", "build"):
            with self.subTest(command=failing_command):
                execute, calls = self._fake_execute(fail=failing_command)
                with self.assertRaises(subprocess.CalledProcessError):
                    self._invoke(execute)
                self.assertEqual(self.consumer.read_bytes(), self.original_consumer)
                self.assertEqual(len(calls), 1 if failing_command == "test" else 2)

    def test_active_source_oracle_failure_leaves_consumer_unchanged(self):
        execute, calls = self._fake_execute()
        with self.assertRaisesRegex(RuntimeError, 'oracle failed'):
            self._invoke(execute, oracle_error=RuntimeError('oracle failed'))
        self.assertEqual(self.consumer.read_bytes(), self.original_consumer)
        self.assertEqual(len(calls), 1)

    def test_active_source_gate_checks_effects_then_coordinator(self):
        engine = SimpleNamespace(engine_root=self.root / "active-engine",
            artifact_path=self.root / "active-engine/engine.exe",
            artifact_sha256="a" * 64, capabilities=())
        manifest = SimpleNamespace(metadata={"source_manifest_body_sha256": "b" * 64})
        with patch("run_workspace.gcsim.engine_store.load_engine_manifest", return_value=manifest), \
             patch("run_workspace.gcsim.optimizer_go_all_sources.prepare_all_set_effect_sources", return_value={"test": True}) as sources, \
             patch.object(installer, "execute", return_value="pass") as execute, \
             redirect_stdout(io.StringIO()):
            installer.validate_active_source_oracle(self.job, engine, "go", self.root)
        self.assertEqual(execute.call_count, 2)
        effects, coordinator = execute.call_args_list
        self.assertIn("./internal/seteffects", effects.args[0])
        self.assertIn("./internal/allsets", coordinator.args[0])
        for call in execute.call_args_list:
            self.assertEqual(call.kwargs["env"]["GTT_RULE_SOURCE_BUNDLE"],
                             str(self.job / "rule-sources.json"))
        self.assertEqual(sources.call_args.args[0], engine.engine_root)
        self.assertTrue(sources.call_args.kwargs["include_neutral_rules"])

    def test_active_engine_change_during_preparation_is_rejected(self):
        changed_engine = SimpleNamespace(
            engine_id="different-engine",
            artifact_sha256="b" * 64,
        )
        execute, _ = self._fake_execute()

        with self.assertRaisesRegex(ValueError, "Installed engine/consumer changed during build"):
            self._invoke(execute, active_contexts=[self.engine, changed_engine])

        self.assertEqual(self.consumer.read_bytes(), self.original_consumer)

    def test_consumer_change_during_preparation_is_rejected(self):
        concurrent_consumer = b"consumer changed while preparing"
        execute, _ = self._fake_execute(
            after_build=lambda: self.consumer.write_bytes(concurrent_consumer),
        )

        with self.assertRaisesRegex(ValueError, "Installed engine/consumer changed during build"):
            self._invoke(execute)

        self.assertEqual(self.consumer.read_bytes(), concurrent_consumer)
        self.assertNotEqual(self.consumer.read_bytes(), self.candidate.read_bytes())

    def test_corrupted_or_failed_candidate_copy_restores_consumer(self):
        for failure in ("corrupt", "copy"):
            with self.subTest(failure=failure):
                execute, _ = self._fake_execute(candidate_bytes=b"candidate optimizer")

                def copy_with_fault(source, destination, *args, **kwargs):
                    source, destination = Path(source), Path(destination)
                    if source == self.candidate and destination == self.consumer:
                        destination.write_bytes(b"corrupted copy" if failure == "corrupt" else b"partial copy")
                        if failure == "copy":
                            raise OSError("injected copy failure")
                        return destination
                    return self.real_copy2(source, destination, *args, **kwargs)

                expected_error = ValueError if failure == "corrupt" else OSError
                with self.assertRaises(expected_error):
                    self._invoke(execute, copy2_side_effect=copy_with_fault)

                self.assertEqual(self.consumer.read_bytes(), self.original_consumer)


if __name__ == "__main__":
    unittest.main()

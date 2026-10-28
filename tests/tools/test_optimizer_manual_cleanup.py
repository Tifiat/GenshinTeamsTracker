"""Read-only checks for the user-run N0 cleanup helper. Never run -Apply here."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(shutil.which("powershell.exe"), "Windows PowerShell required")
class ManualCleanupTest(unittest.TestCase):
    def run_ps(self, source):
        result = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "RemoteSigned",
                                 "-Command", source], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_research_preview_and_unsafe_path_guards(self):
        output = self.run_ps("""
            . ./tools/cleanup_optimizer_caches.ps1 -Research
            $badPaths = @($cleanupRoot, (Join-Path $cleanupRoot 'data'),
                          (Join-Path $cleanupRoot '.codex_tmp/history-design'),
                          (Join-Path $cleanupRoot '../outside'))
            foreach ($bad in $badPaths) {
                $blocked = $false
                try { Assert-SafeCachePath $bad } catch { $blocked = $true }
                if (-not $blocked) { throw "Unsafe path accepted: $bad" }
            }
            Write-Output 'GUARDS PASS'
        """)
        self.assertIn("PREVIEW ONLY", output)
        self.assertIn("GUARDS PASS", output)

    def test_registered_worktree_cannot_be_removed(self):
        output = self.run_ps("""
            . ./tools/cleanup_optimizer_caches.ps1
            function git { $global:LASTEXITCODE = 0; "worktree $cleanupRoot/.codex_tmp/example/source" }
            $blocked = $false
            try { Assert-NoRuntimeOrWorktreeDependency @((Join-Path $cleanupRoot '.codex_tmp/example')) }
            catch { $blocked = $true }
            if (-not $blocked) { throw 'Registered worktree accepted for cleanup' }
            Write-Output 'WORKTREE PASS'
        """)
        self.assertIn("WORKTREE PASS", output)

    def test_deep_preview_preserves_active_and_rollback_engines(self):
        output = self.run_ps("""
            . ./tools/cleanup_optimizer_caches.ps1 -Deep
            $state = Get-Content data/gcsim/engines/active_engine.json -Raw | ConvertFrom-Json
            foreach ($id in @($state.active_engine_id, $state.rollback_engine_id)) {
                $blocked = $false
                $engine = Join-Path $cleanupRoot ("data/gcsim/engines/engines/" + $id)
                try { Assert-NoRuntimeOrWorktreeDependency @($engine) } catch { $blocked = $true }
                if (-not $blocked) { throw 'Protected engine accepted' }
            }
            Write-Output 'DEEP GUARDS PASS'
        """)
        self.assertIn("PREVIEW ONLY", output)
        self.assertIn("DEEP GUARDS PASS", output)

    def test_binary_preview_and_exact_file_guards(self):
        output = self.run_ps("""
            . ./tools/cleanup_optimizer_binaries.ps1
            $badPaths = @($cleanupRoot, (Join-Path $cleanupRoot 'data/artifacts.db'),
                          (Join-Path $cleanupRoot '.codex_tmp/unknown.exe'),
                          (Join-Path $cleanupRoot '.codex_tmp/gob10-performance-audit'),
                          (Join-Path $cleanupRoot '../outside.exe'))
            foreach ($bad in $badPaths) {
                $blocked = $false
                try { Assert-SafeBinaryPath $bad } catch { $blocked = $true }
                if (-not $blocked) { throw "Unsafe binary path accepted: $bad" }
            }
            Write-Output 'BINARY GUARDS PASS'
        """)
        self.assertIn("Inspected binaries present:", output)
        self.assertIn("206964736", output)
        self.assertIn("PREVIEW ONLY", output)
        self.assertIn("BINARY GUARDS PASS", output)


class ResearchAllowlistTest(unittest.TestCase):
    def test_manifest_is_exact_unique_and_matches_audited_bytes(self):
        body = json.loads((ROOT / "tools/optimizer_research_cleanup.json").read_bytes())
        paths = [row["path"] for row in body["targets"]]
        self.assertEqual(len(paths), len(set(paths)))
        self.assertEqual(sum(row["audited_bytes"] for row in body["targets"]), body["audited_target_bytes"])
        for path in paths:
            self.assertEqual(Path(path).parent.as_posix(), ".codex_tmp")
            self.assertNotIn("..", path)
            self.assertNotIn("*", path)


if __name__ == "__main__":
    unittest.main()

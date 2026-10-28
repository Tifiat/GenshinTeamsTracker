# One-off removal of five obsolete optimizer experiment binaries audited on 2026-09-17.
# Preview is the default. Pass -Apply to delete only these exact files.
# This helper writes no logs or temporary files; output goes to the console.
[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'Medium')]
param([switch]$Apply)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$cleanupRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$cleanupPrefix = $cleanupRoot.TrimEnd('\') + '\'
if (-not (Test-Path -LiteralPath (Join-Path $cleanupRoot 'CODEX.md') -PathType Leaf) -or
    -not (Test-Path -LiteralPath (Join-Path $cleanupRoot 'run_workspace\gcsim\optimizer_go_selected.py') -PathType Leaf)) {
    throw 'This script must remain in the GenshinTeamsTracker tools directory.'
}

$cleanupRelativePaths = @(
    '.codex_tmp\gcsim-trace-provenance-v2.exe',
    '.codex_tmp\gob10-performance-audit\gtt-gcsim-fastpath-event-overlay.exe',
    '.codex_tmp\gob10-performance-audit\gtt-gcsim-fastpath-overlay.exe',
    '.codex_tmp\gob10-performance-audit\gtt-gcsim-fastpath.exe',
    '.codex_tmp\gob10-performance-audit\search-main-baseline.test.exe'
)
$expectedAuditedBytes = [int64]206964736

function Assert-SafeBinaryPath([string]$BinaryPath) {
    $absolute = [System.IO.Path]::GetFullPath($BinaryPath)
    if (-not $absolute.StartsWith($cleanupPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Target is outside the project: $absolute"
    }
    $relative = $absolute.Substring($cleanupPrefix.Length)
    if ($cleanupRelativePaths -notcontains $relative) {
        throw "Target is not on the inspected binary allowlist: $absolute"
    }
    if ($relative.Contains('..') -or $relative -match '[*?]' -or
        $relative -notmatch '^\.codex_tmp\\(?:gcsim-trace-provenance-v2\.exe|gob10-performance-audit\\(?:gtt-gcsim-fastpath(?:-event-overlay|-overlay)?\.exe|search-main-baseline\.test\.exe))$') {
        throw "Invalid binary allowlist entry: $relative"
    }

    # Refuse linked files and any linked/junction ancestor. Never follow a link.
    $item = Get-Item -LiteralPath $absolute -Force -ErrorAction SilentlyContinue
    if ($null -ne $item) {
        if ($item.PSIsContainer) { throw "Binary target is a directory: $absolute" }
        if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
            throw "Refusing a linked file: $absolute"
        }
    }
    $ancestor = [System.IO.DirectoryInfo]::new([System.IO.Path]::GetDirectoryName($absolute))
    while ($null -ne $ancestor) {
        $ancestor.Refresh()
        if ($ancestor.Exists -and ($ancestor.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
            throw "Refusing a linked/junction directory: $($ancestor.FullName)"
        }
        $ancestor = $ancestor.Parent
    }
    return $absolute
}

function Assert-NoBuildInProgress {
    $busy = @(Get-Process -Name 'go', 'compile', 'link', 'gtt-optimizer', 'gtt-gcsim' -ErrorAction SilentlyContinue)
    if ($busy.Count -gt 0) {
        $description = ($busy | ForEach-Object { '{0} (PID {1})' -f $_.ProcessName, $_.Id }) -join ', '
        throw "Close running builds/optimizer/simulations before cleanup: $description"
    }
}

$targets = @()
$presentBytes = [int64]0
foreach ($relative in $cleanupRelativePaths) {
    $absolute = Assert-SafeBinaryPath (Join-Path $cleanupRoot $relative)
    if (Test-Path -LiteralPath $absolute -PathType Leaf) {
        $item = Get-Item -LiteralPath $absolute -Force
        $presentBytes += [int64]$item.Length
        $targets += $absolute
    } else {
        Write-Host "Already absent: $absolute"
    }
}

Write-Host "Project: $cleanupRoot"
Write-Host "Inspected binaries present: $($targets.Count)"
Write-Host ('Present bytes: {0} ({1:N2} MiB); audited total when all five are present: {2} bytes.' -f
    $presentBytes, ($presentBytes / 1MB), $expectedAuditedBytes)
foreach ($absolute in $targets) { Write-Host "  $absolute" }
Write-Host 'Account data, source files, active engines, archives and the dirty worktree are NOT deletion targets.'

if (-not $Apply) {
    Write-Host 'PREVIEW ONLY: nothing was deleted. Add -Apply to delete only these five reviewed files permanently.'
    return
}

Assert-NoBuildInProgress
$removedCount = 0
$removedBytes = [int64]0
foreach ($absolute in $targets) {
    Assert-NoBuildInProgress
    $checkedPath = Assert-SafeBinaryPath $absolute
    $length = [int64](Get-Item -LiteralPath $checkedPath -Force).Length
    if ($PSCmdlet.ShouldProcess($checkedPath, 'Permanently delete inspected obsolete binary')) {
        Remove-Item -LiteralPath $checkedPath -Force -ErrorAction Stop
        if (Test-Path -LiteralPath $checkedPath) { throw "Deletion verification failed: $checkedPath" }
        $removedCount++
        $removedBytes += $length
        Write-Host "Removed: $checkedPath"
    }
}
Write-Host ('Finished. Removed binaries: {0}; bytes: {1} ({2:N2} MiB).' -f
    $removedCount, $removedBytes, ($removedBytes / 1MB))

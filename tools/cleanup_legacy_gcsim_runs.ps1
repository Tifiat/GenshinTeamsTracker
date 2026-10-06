# Windows PowerShell 5.1+. Preview by default; -Apply sends only the old
# project-root data/gcsim/runs directory to the Windows Recycle Bin.
[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'Medium')]
param([switch]$Apply)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-LegacyCleanupPath {
    param([string]$Root, [string]$Path)
    $full = [IO.Path]::GetFullPath($Path)
    $prefix = $Root.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
    if ($full -ne $Root -and -not $full.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Cleanup path escapes the project root.'
    }
    $current = $full
    while ($true) {
        $item = Get-Item -LiteralPath $current -Force -ErrorAction SilentlyContinue
        if ($null -ne $item -and ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw "Link/junction is not allowed: $current"
        }
        if ($current -eq $Root) { break }
        $current = [IO.Path]::GetDirectoryName($current)
    }
}

function Get-LegacyCleanupInventory {
    param([string]$Root, [string]$Target)
    Assert-LegacyCleanupPath $Root $Target
    if (-not (Test-Path -LiteralPath $Target)) { return $null }
    if (-not (Test-Path -LiteralPath $Target -PathType Container)) {
        throw 'Legacy runs target must be a directory.'
    }
    $pending = New-Object 'System.Collections.Generic.Stack[string]'
    $pending.Push($Target)
    [long]$files = 0
    [long]$bytes = 0
    while ($pending.Count -gt 0) {
        $directory = $pending.Pop()
        Assert-LegacyCleanupPath $Root $directory
        foreach ($item in Get-ChildItem -LiteralPath $directory -Force) {
            Assert-LegacyCleanupPath $Root $item.FullName
            if ($item.PSIsContainer) { $pending.Push($item.FullName) }
            else { $files++; $bytes += $item.Length }
        }
    }
    return [pscustomobject]@{ Files = $files; Bytes = $bytes }
}

function Assert-LegacyCleanupProfile {
    param([string]$Root)
    foreach ($relative in @('CODEX.md', 'run_workspace/profile_legacy.py')) {
        $marker = Join-Path $Root $relative
        Assert-LegacyCleanupPath $Root $marker
        if (-not (Test-Path -LiteralPath $marker -PathType Leaf)) {
            throw 'Script must remain in the tools directory of this project.'
        }
    }
    $profiles = Join-Path $Root 'data/profiles'
    $registryPath = Join-Path $profiles 'registry.json'
    Assert-LegacyCleanupPath $Root $registryPath
    $registry = Get-Content -LiteralPath $registryPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($registry.schema_version -ne 1 -or $registry.active_profile_id -cnotmatch '^[0-9a-f]{32}$') {
        throw 'A valid selected account profile is required; no cleanup performed.'
    }
    $entries = @($registry.profiles)
    $seen = @{}
    foreach ($entry in $entries) {
        if ($entry.id -cnotmatch '^[0-9a-f]{32}$' -or $seen.ContainsKey($entry.id)) {
            throw 'Malformed profile registry; no cleanup performed.'
        }
        $seen[$entry.id] = $true
    }
    if (-not $seen.ContainsKey($registry.active_profile_id)) {
        throw 'Selected profile is not registered; no cleanup performed.'
    }
    # Include unregistered physical roots: an interrupted migration must not
    # lose its source just because its registry entry is unavailable.
    foreach ($item in Get-ChildItem -LiteralPath $profiles -Force) {
        if ($item.Name -cmatch '^[0-9a-f]{32}$') {
            Assert-LegacyCleanupPath $Root $item.FullName
            $journal = Join-Path $item.FullName '.legacy-migration.json'
            Assert-LegacyCleanupPath $Root $journal
            if (Test-Path -LiteralPath $journal) {
                throw 'Unfinished legacy migration found; resolve it before cleanup.'
            }
        }
    }
    $database = Join-Path $profiles ($registry.active_profile_id + '/data/artifacts.db')
    Assert-LegacyCleanupPath $Root $database
    if (-not (Test-Path -LiteralPath $database -PathType Leaf)) {
        throw 'Selected profile has no account database; preserve legacy runs for recovery.'
    }
    foreach ($relative in @('data/artifacts.db', 'data/artifacts.db-wal', 'data/artifacts.db-shm')) {
        $source = Join-Path $Root $relative
        Assert-LegacyCleanupPath $Root $source
        if (Test-Path -LiteralPath $source) {
            throw 'Legacy account database/sidecar found; preserve legacy runs for migration.'
        }
    }
}

function Move-LegacyRunsToRecycleBin {
    param([string]$Target)
    Add-Type -AssemblyName Microsoft.VisualBasic
    [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory(
        $Target,
        [Microsoft.VisualBasic.FileIO.UIOption]::OnlyErrorDialogs,
        [Microsoft.VisualBasic.FileIO.RecycleOption]::SendToRecycleBin,
        [Microsoft.VisualBasic.FileIO.UICancelOption]::ThrowException
    )
    # Deliberately no permanent-delete fallback.
}

function Invoke-LegacyRunsCleanup {
    [CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'Medium')]
    param([string]$ProjectRoot, [switch]$Apply)
    $root = [IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\', '/')
    if (-not (Test-Path -LiteralPath $root -PathType Container)) { throw 'Project root does not exist.' }
    $target = [IO.Path]::GetFullPath((Join-Path $root 'data/gcsim/runs'))
    Assert-LegacyCleanupPath $root $target
    if (-not (Test-Path -LiteralPath $target)) {
        Write-Host 'Nothing to clean: project-root data/gcsim/runs is absent.'
        return
    }
    Assert-LegacyCleanupProfile $root
    $inventory = Get-LegacyCleanupInventory $root $target
    Write-Host ("Legacy runs only: {0} file(s), {1} byte(s)." -f $inventory.Files, $inventory.Bytes)
    Write-Host "Target: $target"
    Write-Host 'Profile data, engines, other runs and source files will not be changed.'
    if (-not $Apply) {
        Write-Host 'Preview only. Close the application and run this script with -Apply to recycle this directory.'
        return
    }
    if (-not $PSCmdlet.ShouldProcess($target, 'Send legacy runs to Windows Recycle Bin')) { return }
    $leases = New-Object 'System.Collections.Generic.List[System.IO.FileStream]'
    try {
        # Same fixed paths as profile_control.py and account_profiles.py.
        # FileShare.None plus a byte lock excludes the application's Python
        # handles and prevents a new supervisor/import/registry writer.
        foreach ($name in @('profile-supervisor.lock', 'profile-operations.lock', 'account_profiles.lock')) {
            $lockPath = Join-Path $root ('data/' + $name)
            Assert-LegacyCleanupPath $root $lockPath
            try {
                $lease = [IO.File]::Open($lockPath, [IO.FileMode]::OpenOrCreate,
                    [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
                $leases.Add($lease)
                $lease.Lock(0, 1)
            }
            catch { throw 'Application or account operation is running, or its lock cannot be acquired. Close it and retry.' }
        }
        # Recheck under the leases, not just against the earlier preview.
        Assert-LegacyCleanupProfile $root
        $inventory = Get-LegacyCleanupInventory $root $target
        if ($null -eq $inventory) { Write-Host 'Nothing to clean: legacy runs are already absent.'; return }
        Move-LegacyRunsToRecycleBin $target
        if (Test-Path -LiteralPath $target) { throw 'Recycle operation did not remove the target; cleanup is not confirmed.' }
        Write-Host 'Done. Only legacy data/gcsim/runs was sent to Windows Recycle Bin; it can be restored there.'
    }
    finally {
        foreach ($lease in $leases) { $lease.Dispose() }
    }
}

# Dot sourcing exposes the functions for isolated tests; it never runs cleanup.
if ($MyInvocation.InvocationName -ne '.') {
    Invoke-LegacyRunsCleanup -ProjectRoot (Join-Path $PSScriptRoot '..') -Apply:$Apply
}

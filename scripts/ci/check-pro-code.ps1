param(
    [string]$BaseRef = "origin/main",
    [string]$HeadRef = "HEAD"
)

$ErrorActionPreference = "Stop"

$found = $false
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")

function Report-ProHit {
    param([string]$Message)
    Write-Error $Message
    $script:found = $true
}

$proDirs = @(
    "backend/app/pro",
    "license-server"
)

foreach ($dir in $proDirs) {
    $path = Join-Path $repoRoot $dir
    if (Test-Path -LiteralPath $path) {
        Report-ProHit "$dir found; PRO code must not be in the public Core repo."
    }
}

$mergeBase = git -C $repoRoot merge-base $BaseRef $HeadRef
$changedFiles = git -C $repoRoot diff --name-only "$mergeBase..$HeadRef"

$proFilePattern = '^(backend/app/pro/|license-server/)'
$proFiles = $changedFiles | Where-Object { $_ -match $proFilePattern }

if ($proFiles) {
    Report-ProHit "Diff contains PRO-only paths:`n$($proFiles -join "`n")"
}

if ($found) {
    exit 1
}

Write-Host "No PRO code detected; public Core repo is clean."

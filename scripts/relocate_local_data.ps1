param([switch]$Apply)

# Keep existing absolute paths usable while storing large local data outside Git.
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$storageRoot = Join-Path (Split-Path $projectRoot -Parent) 'immune-repertoire-web-data'
$entries = @(
    @{ Source = '_reference'; Target = '_reference' },
    @{ Source = 'test_data'; Target = 'test_data' },
    @{ Source = 'flask_app\data\results'; Target = 'results' }
)

foreach ($entry in $entries) {
    $source = [IO.Path]::GetFullPath((Join-Path $projectRoot $entry.Source))
    $target = [IO.Path]::GetFullPath((Join-Path $storageRoot $entry.Target))
    if (-not $source.StartsWith($projectRoot + '\', [StringComparison]::OrdinalIgnoreCase) -or
        -not $target.StartsWith($storageRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Path is outside the expected project or storage directory.'
    }
    $item = Get-Item -LiteralPath $source -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        if ($item.LinkType -eq 'Junction' -and
            [IO.Path]::GetFullPath([string]$item.Target).TrimEnd('\') -eq $target.TrimEnd('\')) {
            Write-Output "Already relocated: $source -> $target"
            continue
        }
        throw "Unexpected reparse point: $source"
    }
    if (Test-Path -LiteralPath $target) { throw "Destination already exists: $target" }
    Write-Output "Move directory: $source -> $target; retain original path as a junction"
}

if (-not $Apply) {
    Write-Output 'Preview only. Pass -Apply to move the three directories.'
    exit 0
}

# Same-volume moves do not copy or delete the data contents.
New-Item -ItemType Directory -Path $storageRoot -Force | Out-Null
foreach ($entry in $entries) {
    $source = [IO.Path]::GetFullPath((Join-Path $projectRoot $entry.Source))
    $target = [IO.Path]::GetFullPath((Join-Path $storageRoot $entry.Target))
    if (-not $source.StartsWith($projectRoot + '\', [StringComparison]::OrdinalIgnoreCase) -or
        -not $target.StartsWith($storageRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Move path validation failed.'
    }
    if ((Get-Item -LiteralPath $source -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
        continue
    }
    Move-Item -LiteralPath $source -Destination $target
    try {
        New-Item -ItemType Junction -Path $source -Target $target | Out-Null
    } catch {
        if (-not (Test-Path -LiteralPath $source)) {
            Move-Item -LiteralPath $target -Destination $source
        }
        throw
    }
    Get-Item -LiteralPath $source -Force | Select-Object FullName, LinkType, Target
}

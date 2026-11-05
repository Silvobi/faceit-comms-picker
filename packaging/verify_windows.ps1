$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$testRoot = Join-Path $env:RUNNER_TEMP 'faceit-comms-picker-check'
New-Item -ItemType Directory -Path $testRoot -Force | Out-Null
$packages = Join-Path $projectRoot 'dist\packages'
$installer = @(Get-ChildItem -LiteralPath $packages -Filter '*-Setup.exe')
$portable = @(Get-ChildItem -LiteralPath $packages -Filter '*-portable.zip')
if ($installer.Count -ne 1 -or $portable.Count -ne 1) { throw 'Expected one installer and one portable ZIP' }

function Test-App([string]$executable, [string]$report) {
    $process = Start-Process -FilePath $executable -ArgumentList @('--smoke-test', "`"$report`"") -WindowStyle Hidden -PassThru
    if (-not $process.WaitForExit(90000)) { $process.Kill(); throw 'App smoke test timed out' }
    if ($process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $report)) { throw 'App smoke test failed' }
    $data = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
    if (-not $data.frozen -or -not $data.parser_help) { throw 'Bundle or parser check failed' }
}

Expand-Archive -LiteralPath $portable[0].FullName -DestinationPath (Join-Path $testRoot 'portable') -Force
$portableRoot = Join-Path $testRoot 'portable\FACEIT-Comms-Picker'
if (-not (Test-Path -LiteralPath (Join-Path $portableRoot 'portable.txt'))) { throw 'Portable marker missing' }
Test-App (Join-Path $portableRoot 'FACEIT-Comms-Picker.exe') (Join-Path $testRoot 'portable-smoke.json')

$installRoot = Join-Path $testRoot 'installed'
$process = Start-Process -FilePath $installer[0].FullName -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', "/DIR=`"$installRoot`"") -WindowStyle Hidden -Wait -PassThru
if ($process.ExitCode -ne 0) { throw 'Installer failed' }
try {
    $shortcut = Join-Path ([Environment]::GetFolderPath('Programs')) 'FACEIT Comms Picker.lnk'
    if (-not (Test-Path -LiteralPath $shortcut)) { throw 'Start menu shortcut missing' }
    if (Test-Path -LiteralPath (Join-Path $installRoot 'portable.txt')) { throw 'Installer must use normal user settings' }
    $target = (New-Object -ComObject WScript.Shell).CreateShortcut($shortcut).TargetPath
    if ($target -ne (Join-Path $installRoot 'FACEIT-Comms-Picker.exe')) { throw 'Start shortcut points to wrong file' }
    Test-App $target (Join-Path $testRoot 'installed-smoke.json')
} finally {
    $uninstaller = Join-Path $installRoot 'unins000.exe'
    $process = Start-Process -FilePath $uninstaller -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART') -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw 'Uninstaller failed' }
}
if (Test-Path -LiteralPath $shortcut) { throw 'Uninstaller left a Start menu shortcut' }
Write-Output 'Installer, Start menu, bundled parser, portable ZIP, and uninstaller verified.'

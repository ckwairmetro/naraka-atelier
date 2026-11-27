param(
    [Parameter(Mandatory)] [string] $Version,
    [Parameter(Mandatory)] [string] $InnoCompiler,
    [Parameter(Mandatory)] [string] $ChineseMessages,
    [string] $Python = 'python',
    [string] $UpdateFeed,
    [string] $ReleasePage
)

$ErrorActionPreference = 'Stop'
if ($Version -notmatch '^[0-9]{1,6}(\.[0-9]{1,6}){2,3}$') {
    throw 'Use a numeric Atelier version, for example 0.2.9.3.'
}
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$compiler = (Resolve-Path -LiteralPath $InnoCompiler).Path
$messages = (Resolve-Path -LiteralPath $ChineseMessages).Path
$output = Join-Path $root "releases/v$Version"
$payload = Join-Path $output 'payload'
$build = @((Join-Path $root 'app/package_app.py'), '--version', $Version, '--output', $payload)
if ($UpdateFeed) { $build += @('--update-feed', $UpdateFeed) }
if ($ReleasePage) { $build += @('--release-page', $ReleasePage) }

& $Python @build
if ($LASTEXITCODE -ne 0) { throw "Atelier packaging failed ($LASTEXITCODE)." }

$compile = @(
    "/DAtelierVersion=$Version"
    "/DPayloadDir=$(Join-Path $payload 'NarakaAtelier')"
    "/DChineseMessages=$messages"
    "/O$output"
    (Join-Path $PSScriptRoot 'Atelier.iss')
)
& $compiler @compile
if ($LASTEXITCODE -ne 0) { throw "Setup compilation failed ($LASTEXITCODE)." }

$installer = "NarakaAtelier-v$Version-Setup-x64.exe"
$release = @{ version = $Version; installer = $installer }
if ($ReleasePage) { $release.download_page = $ReleasePage }
$release | ConvertTo-Json -Compress |
    Set-Content -LiteralPath (Join-Path $output 'latest.json') -Encoding utf8
Get-Item -LiteralPath (Join-Path $output $installer)

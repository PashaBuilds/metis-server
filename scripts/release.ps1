<#
.SYNOPSIS
  METIS sürümünü yerel Windows bilgisayarda derler ve (gerçek Windows'ta denendikten sonra) GitHub release'e koyar.

.DESCRIPTION
  Yayımlanan ZIP, CI'da değil bu bilgisayarda derlenip çift tıklamayla denenmiş ZIP'in kendisidir.

    1. powershell -ExecutionPolicy Bypass -File scripts\release.ps1 -Derle
         main temiz ve origin/main ile aynı mı, sürüm daha önce yayımlanmış mı denetlenir; ruff, eslint, OpenAPI
         sözleşmesi ve tam pytest (yerel PostgreSQL, masaüstü testi dahil) çalışır; paket dist\ altına derlenir (tsc +
         vite dahil); ZIP'in SHA-256'sı dist\aday.json'a yazılır. Başta aynı commit için GitHub'da CI başlatılır (uçtan uca
         Playwright + temiz Windows Server'da çevrimdışı kurulum/yükseltme; yerelde yapılamayanlar) ve paralel koşar.
    2. ZIP'i ayrı bir klasöre aç, METIS-Baslat.exe'ye çift tıkla (kurulum/yükseltme, Chrome, sol menüde sürüm).
    3. powershell -ExecutionPolicy Bypass -File scripts\release.ps1 -Yayimla
         Aday ZIP değişmemiş mi, commit hâlâ origin/main mi, o commit'te CI yeşil mi denetlenir; gh release create ile
         etiket (sunucu tarafında) ve release oluşturulur, yüklenen dosyanın özeti karşılaştırılır.

  Önkoşul: gh auth login, .venv, npm install, PostgreSQL 16 (METIS_TEST_ADMIN_DSN; CLAUDE.md "Windows'ta").
#>
[CmdletBinding()]
param(
  [switch]$Derle,
  [switch]$Yayimla,
  [string]$PgBin = "C:\Program Files\PostgreSQL\16\bin"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Py = Join-Path $Root ".venv\Scripts\python.exe"
$Candidate = Join-Path $Root "dist\aday.json"

function Invoke-Native([string]$Exe, [string[]]$Arguments) {
  # Windows PowerShell 5.1: Stop + yönlendirilmiş stderr sonlandırıcı hata olur (pip/npm/gh stderr'e de yazar);
  # yerel araçlarda yalnız çıkış koduna bakılır. Değişken bu işlevin kapsamındadır.
  $ErrorActionPreference = "Continue"
  & $Exe @Arguments 2>&1 | ForEach-Object { "$_" }
  if ($LASTEXITCODE -ne 0) { throw "başarısız ($LASTEXITCODE): $Exe $($Arguments -join ' ')" }
}

function Get-Sha256([string]$Path) {
  $s = [IO.File]::OpenRead($Path)
  try { return (([Security.Cryptography.SHA256]::Create().ComputeHash($s)) | ForEach-Object { $_.ToString("x2") }) -join "" } finally { $s.Dispose() }
}

function Assert-PushedMain {
  if (git status --porcelain) { throw "Çalışma ağacı temiz değil; önce commit + push et." }
  if ((git rev-parse --abbrev-ref HEAD) -ne "main") { throw "main dalında değilsin." }
  Invoke-Native git @("fetch", "-q", "origin", "main") | Out-Null
  $head = (git rev-parse HEAD).Trim()
  if ($head -ne (git rev-parse origin/main).Trim()) { throw "HEAD origin/main ile aynı değil; önce push et (release o commit'e bağlanır)." }
  return $head
}

function Get-ReleaseTag {
  $tag = (Get-Content (Join-Path $Root "deploy\RELEASE") -TotalCount 1).Trim()
  if ($tag -notmatch '^v\d+\.\d+\.\d+$') { throw "deploy/RELEASE geçersiz: $tag" }
  $ErrorActionPreference = "Continue"  # yayımlanmamışsa gh stderr'e 'release not found' yazar
  gh release view $tag *> $null
  if ($LASTEXITCODE -eq 0) { throw "$tag zaten yayımlanmış; deploy/RELEASE ve __version__'ı yükselt." }
  return $tag
}

if ($Derle -eq $Yayimla) { throw "-Derle ya da -Yayimla seç (biri)." }

if ($Derle) {
  $commit = Assert-PushedMain
  $tag = Get-ReleaseTag
  $version = $tag.Substring(1)
  # CI push'ta çalışmaz (ürün sahibinin kararı 2026-10-19); sürüm adayı başına bir kez, yerel derlemeyle paralel.
  Write-Host "==> CI başlatılıyor ($commit): uçtan uca + temiz Windows Server; -Yayimla yeşilini bekler" -ForegroundColor Cyan
  Invoke-Native gh @("workflow", "run", "CI", "--ref", "main") | Out-Null
  Write-Host "==> $tag ($commit) denetimler" -ForegroundColor Cyan
  Invoke-Native $Py @("-m", "ruff", "check", "services", "tests", "evals", "deploy")
  Invoke-Native npm @("run", "lint", "--workspace", "apps/web")
  # OpenAPI sözleşmesi: apps/web/openapi.json sunucunun ürettiğiyle aynı olmalı (arayüz tipleri ondan üretilir).
  $oapi = Join-Path $env:TEMP "metis-openapi-check.json"
  $env:METIS_ENV = "development"
  Invoke-Native $Py @("scripts\export_openapi.py", $oapi) | Out-Null
  Remove-Item Env:METIS_ENV
  if ((Get-Content -Raw $oapi) -ne (Get-Content -Raw (Join-Path $Root "apps\web\openapi.json"))) { throw "apps/web/openapi.json güncel değil: scripts/export_openapi.py ve openapi-typescript çalıştır." }
  if (-not $env:METIS_TEST_ADMIN_DSN) { $env:METIS_TEST_ADMIN_DSN = "postgresql://metisdev:metis-dev@127.0.0.1:5432/postgres" }
  $env:METIS_PG_BIN = $PgBin
  $env:Path = "$PgBin;$env:Path"  # testler pg_dump'ı PATH'te arar
  $env:METIS_DESKTOP_TEST = "1"  # başlatıcı ileti kutusu gerçek masaüstünde en üstte mi
  Invoke-Native $Py @("-m", "pytest", "-q")
  Write-Host "==> paket derleniyor" -ForegroundColor Cyan
  Invoke-Native $Py @("deploy\build-bundle.py", "--target", "win64", "--locked", "--require-launcher")
  $zip = Join-Path $Root "dist\METIS-$version-server-win64.zip"
  if (-not (Test-Path $zip)) { throw "ZIP üretilmedi: $zip" }
  $info = [ordered]@{ tag = $tag; commit = $commit; zip = (Split-Path -Leaf $zip); sha256 = (Get-Sha256 $zip); derlendi = (Get-Date).ToString("s") }
  [IO.File]::WriteAllText($Candidate, ($info | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))
  Write-Host ""
  Write-Host "Aday hazır: $zip" -ForegroundColor Green
  Write-Host "Şimdi ZIP'i AYRI bir klasöre aç ve METIS-Baslat.exe'ye çift tıklayarak dene. Sonra: scripts\release.ps1 -Yayimla"
  exit 0
}

# -Yayimla
if (-not (Test-Path $Candidate)) { throw "dist\aday.json yok; önce -Derle." }
$info = Get-Content -Raw $Candidate | ConvertFrom-Json
$commit = Assert-PushedMain
if ($commit -ne $info.commit) { throw "Aday $($info.commit) commit'inden derlendi, HEAD $commit. Yeniden -Derle ve dene." }
$tag = Get-ReleaseTag
if ($tag -ne $info.tag) { throw "Aday $($info.tag), deploy/RELEASE $tag." }
$zip = Join-Path $Root "dist\$($info.zip)"
if ((Get-Sha256 $zip) -ne $info.sha256) { throw "ZIP denendikten sonra değişmiş; yeniden -Derle." }
$green = (gh run list --workflow CI --commit $commit --json conclusion --jq '[.[] | select(.conclusion == \"success\")] | length').Trim()
if ($green -eq "0") {
  $active = (gh run list --workflow CI --commit $commit --json status,databaseId --jq '[.[] | select(.status != \"completed\")][0].databaseId // \"\"').Trim()
  if ($active) { throw "Bu commit'in CI koşusu sürüyor; bitmesini bekle: gh run watch $active" }
  throw "Bu commit'te yeşil CI koşusu yok (uçtan uca + temiz Windows Server). Kırmızıysa düzelt; hiç yoksa: gh workflow run CI --ref main"
}
$notes = Join-Path $Root "deploy\RELEASE_NOTES.md"
$ghArgs = @("release", "create", $tag, $zip, "$zip.sha256", "--target", $commit, "--title", "METIS $tag", "--notes-file", $notes)
Write-Host "==> gh $($ghArgs -join ' ')" -ForegroundColor Cyan
Invoke-Native gh $ghArgs
$asset = (gh release view $tag --json assets | ConvertFrom-Json).assets | Where-Object { $_.name -eq $info.zip }
if (-not $asset) { throw "Release'te ZIP görünmüyor." }
if ($asset.digest -and $asset.digest -ne "sha256:$($info.sha256)") { throw "Yüklenen ZIP'in özeti farklı: $($asset.digest)" }
Write-Host "Yayımlandı: $tag ($($info.zip), sha256 $($info.sha256))" -ForegroundColor Green

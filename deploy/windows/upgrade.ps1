<#
.SYNOPSIS
  Kurulu METIS'i bu paketteki sürüme yükseltir (internetsiz).

.DESCRIPTION
  Yeni paketin klasöründen yönetici PowerShell ile:
      powershell -ExecutionPolicy Bypass -File .\upgrade.ps1

  Adımlar:
   1. Paket bütünlüğü doğrulanır; kurulu sürüm okunur.
   2. Yükseltme öncesi yedek alınır (başarısızsa yükseltme yapılmaz).
   3. Yeni sürüm C:\METIS\app\<yeni> altına, eskisinin yanına kurulur (servisler çalışmaya devam eder).
   4. Servisler durur → app\current yeni sürüme döner → metis migrate → servisler başlar → sağlık kontrolü.
   5. Başarısızlıkta app\current eski sürüme döner ve eski servisler başlatılır. Şema yükseltmesi uygulanmışsa
      ekrana yazılan yedekten geri yükleme talimatı verilir (migration'lar yalnız ileri yönlüdür).
   6. En yeni iki sürüm saklanır, daha eskiler silinir.
#>
[CmdletBinding()]
param(
  [string]$InstallRoot = "C:\METIS",
  [int]$ApiPort = 8000,
  [switch]$SkipServices,
  [switch]$SkipBackup
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$Bundle = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $Bundle "metis-common.ps1")

if (-not $SkipServices) { Assert-Admin }
Test-BundleIntegrity $Bundle
$envFile = Join-Path $InstallRoot "config\metis.env"
if (-not (Test-Path $envFile)) { throw "Kurulu METIS bulunamadı ($envFile). İlk kurulum için install-offline.ps1 kullan." }
$env:METIS_CONFIG = $envFile
$oldDir = Get-CurrentAppDir $InstallRoot
if (-not $oldDir) { throw "app\current bulunamadı; kurulum bozuk." }
$oldVersion = (Get-Content (Join-Path $oldDir ".installed") -TotalCount 1).Trim()
$newVersion = Get-BundleVersion $Bundle
Write-Step "Yükseltme: $oldVersion → $newVersion"
if ($oldVersion -eq $newVersion) { Write-Host "Bu sürüm zaten kurulu; işlem yok."; exit 0 }

$backupFile = $null
if (-not $SkipBackup) {
  Write-Step "Yükseltme öncesi yedek"
  Invoke-Metis -AppDir $oldDir -Arguments @("backup") | Out-Null
  $backupFile = (Get-Content -Raw (Join-Path $InstallRoot "data\backups\last-backup.json") | ConvertFrom-Json).file
  Write-Host "  yedek: $backupFile"
}

$newDir = Install-AppVersion -Bundle $Bundle -InstallRoot $InstallRoot -Version $newVersion

if (-not $SkipServices) { Write-Step "Servisler durduruluyor"; Stop-MetisServices $InstallRoot }
Set-CurrentVersion -InstallRoot $InstallRoot -AppDir $newDir
$migrated = $false
try {
  Write-Step "Şema yükseltiliyor"
  Invoke-Metis -AppDir $newDir -Arguments @("migrate") | Out-Host
  $migrated = $true
  if (-not $SkipServices) {
    Start-MetisServices $InstallRoot
    Wait-Healthy -Port $ApiPort -Seconds 90
  }
  Invoke-Metis -AppDir $newDir -Arguments @("doctor") -AllowFailure | Out-Host
} catch {
  Write-Warning "Yükseltme başarısız: $($_.Exception.Message)"
  Write-Step "Önceki sürüme dönülüyor ($oldVersion)"
  if (-not $SkipServices) { Stop-MetisServices $InstallRoot }
  Set-CurrentVersion -InstallRoot $InstallRoot -AppDir $oldDir
  if ($migrated -and $backupFile) {
    Write-Warning "Şema yeni sürüme yükseltilmişti. Eski sürümle çalışmak için yedeği boş bir veritabanına geri yükle:"
    Write-Warning "  C:\METIS\bin\metis restore `"$backupFile`"   (KURULUM.md, 'Geri yükleme' bölümü)"
  }
  if (-not $SkipServices) { Start-MetisServices $InstallRoot }
  throw
}

Write-Step "Eski sürümler temizleniyor (en yeni iki sürüm kalır)"
Get-ChildItem (Join-Path $InstallRoot "app") -Directory | Where-Object { $_.Name -ne "current" -and (Test-Path (Join-Path $_.FullName ".installed")) } |
  Sort-Object LastWriteTime -Descending | Select-Object -Skip 2 | ForEach-Object { Remove-Item -Recurse -Force $_.FullName; Write-Host "  silindi: $($_.Name)" }
Write-Step "Yükseltme tamamlandı: METIS $newVersion"

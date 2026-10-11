<#
.SYNOPSIS
  METIS'i bu bilgisayardan kaldırır (deneme kurulumlarını temizlemek için de kullanılır).

.DESCRIPTION
  Yönetici PowerShell ile, paket klasöründen çalıştırılır:
      powershell -ExecutionPolicy Bypass -File .\uninstall.ps1               # servisler, görevler, program dosyaları
      powershell -ExecutionPolicy Bypass -File .\uninstall.ps1 -RemoveAll    # + veritabanı, ayarlar, ana anahtar, veriler, yedekler

  Varsayılan kaldırma verileri KORUR: C:\METIS\config (ayarlar, ana anahtar), C:\METIS\data (dosyalar, yedekler)
  ve 'metis' veritabanı yerinde kalır; aynı paketle yeniden kurulumda kaldığı yerden devam eder.
  -RemoveAll geri alınamaz: 'metis' veritabanı ve metis_owner / metis_app rolleri silinir, C:\METIS tümüyle kaldırılır.
  PostgreSQL'in kendisi kaldırılmaz (Windows "Uygulamalar" bölümünden ayrıca kaldırılabilir).
#>
[CmdletBinding()]
param(
  [string]$InstallRoot = "C:\METIS",
  [string]$PgBin = "C:\Program Files\PostgreSQL\16\bin",
  [string]$PgHost = "127.0.0.1",
  [int]$PgPort = 5432,
  [string]$PgSuperUser = "postgres",
  [switch]$RemoveAll
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$Bundle = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $Bundle "metis-common.ps1")

Assert-Admin
if (-not (Test-Path $InstallRoot)) { throw "Kurulum bulunamadı: $InstallRoot" }
Write-Step "METIS kaldırılıyor ($InstallRoot)"

Write-Step "Servisler durduruluyor ve kaldırılıyor"
Stop-MetisServices $InstallRoot
foreach ($name in @("metis-worker", "metis-api")) {
  $exe = Join-Path $InstallRoot "services\$name.exe"
  if ((Get-Service -Name $name -ErrorAction SilentlyContinue) -and (Test-Path $exe)) {
    & $exe uninstall | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "$name servisi kaldırılamadı." }
  }
  # Hizmet Denetimi Yöneticisi silmeyi hemen bitirmeyebilir; kayıt kalkana kadar bekle.
  $deadline = (Get-Date).AddSeconds(30)
  while ((Get-Service -Name $name -ErrorAction SilentlyContinue) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 500 }
  if (Get-Service -Name $name -ErrorAction SilentlyContinue) { throw "$name servisi hâlâ kayıtlı; bilgisayarı yeniden başlatıp tekrar dene." }
  Write-Host "  $name kaldırıldı."
}

Write-Step "Zamanlanmış görevler siliniyor"
foreach ($task in @("METIS gece yedeği", "METIS geri yükleme tatbikatı")) {
  if (Get-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $task -Confirm:$false
    Write-Host "  '$task' silindi."
  }
}

if ($RemoveAll) {
  Write-Step "Veritabanı ve roller siliniyor"
  $psql = Join-Path $PgBin "psql.exe"
  if (-not (Test-Path $psql)) { throw "psql bulunamadı: $PgBin (-PgBin ile yolu ver). Hiçbir dosya silinmedi; servisler ve görevler kaldırıldı." }
  $superPw = $env:METIS_PG_SUPERUSER_PASSWORD
  if (-not $superPw) {
    $sec = Read-Host -AsSecureString "PostgreSQL '$PgSuperUser' parolası (kaydedilmez)"
    $superPw = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
  }
  $sql = @"
DROP DATABASE IF EXISTS metis WITH (FORCE);
DROP ROLE IF EXISTS metis_app;
DROP ROLE IF EXISTS metis_owner;
"@
  Invoke-Psql $psql $PgHost $PgPort $PgSuperUser $superPw "postgres" $sql | Out-Null
  $superPw = $null
  Write-Host "  'metis' veritabanı, metis_app ve metis_owner silindi."

  Write-Step "Tüm dosyalar siliniyor ($InstallRoot)"
  $cur = Join-Path $InstallRoot "app\current"
  if (Test-Path $cur) { (Get-Item $cur).Delete() }  # önce bağlantı: içeriği iki kez gezilmesin
  Remove-Item -LiteralPath $InstallRoot -Recurse -Force
  Write-Step "METIS tümüyle kaldırıldı"
} else {
  Write-Step "Program dosyaları siliniyor (ayarlar, veriler ve veritabanı korunuyor)"
  $cur = Join-Path $InstallRoot "app\current"
  if (Test-Path $cur) { (Get-Item $cur).Delete() }
  foreach ($dir in @("app", "services", "bin")) {
    $p = Join-Path $InstallRoot $dir
    if (Test-Path $p) { Remove-Item -LiteralPath $p -Recurse -Force }
  }
  Write-Step "METIS kaldırıldı"
  Write-Host "Korunanlar: $InstallRoot\config (ana anahtar dahil), $InstallRoot\data (dosyalar, yedekler), 'metis' veritabanı."
  Write-Host "Her şeyi silmek için: powershell -ExecutionPolicy Bypass -File .\uninstall.ps1 -RemoveAll"
}

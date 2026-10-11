<#
.SYNOPSIS
  METIS sunucusunu internetsiz kurar (Windows Server 2019/2022, PowerShell 5.1+).

.DESCRIPTION
  Bu betik paket klasöründen (ZIP'i açtığın yer) yönetici PowerShell ile çalıştırılır:
      powershell -ExecutionPolicy Bypass -File .\install-offline.ps1 -PublicUrl https://metis.sirket.local

  Yaptıkları:
   1. Paket bütünlüğü (SHA256SUMS) doğrulanır.
   2. PostgreSQL 16 istemci araçları aranır (EDB kurucusunu bu betik çalıştırmaz; KURULUM.md 2. adım).
   3. Gömülü Python 3.12 + hash-kilitli tekerlekler C:\METIS\app\<sürüm> altına kurulur (--no-index: ağ kullanılmaz).
   4. İlk kurulumda: ana anahtar, veritabanı rolleri (metis_owner, metis_app) ve 'metis' veritabanı oluşturulur;
      ayarlar C:\METIS\config\metis.env dosyasına yazılır (yalnız SYSTEM ve Administrators okuyabilir).
   5. Şema yükseltilir (metis migrate), 'metis doctor' çalışır.
   6. WinSW ile iki servis kurulur ve başlatılır: metis-api (127.0.0.1:8000), metis-worker.
   7. Zamanlanmış görevler: her gece yedek (14 gün saklanır), her pazar geri yükleme tatbikatı.
   8. Sağlık kontrolü; yönetici yoksa tek kullanımlık kurulum kodu yazdırılır.

  Tekrar çalıştırmak güvenlidir: var olan ayarlar, anahtar ve veritabanı korunur.
#>
[CmdletBinding()]
param(
  [string]$InstallRoot = "C:\METIS",
  [string]$PublicUrl = "",
  [string]$PgBin = "C:\Program Files\PostgreSQL\16\bin",
  [string]$PgHost = "127.0.0.1",
  [int]$PgPort = 5432,
  [string]$PgSuperUser = "postgres",
  [int]$ApiPort = 8000,
  [int]$ApiWorkers = 2,
  [int]$WorkerSlots = 2,
  [string]$EndpointAllowlist = "",
  [switch]$SkipServices,
  [switch]$SkipScheduledTasks,
  [switch]$AllowHttp
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$Bundle = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $Bundle "metis-common.ps1")

Write-Step "METIS kurulumu başlıyor ($(Get-BundleVersion $Bundle))"
if (-not $SkipServices) { Assert-Admin }
Test-BundleIntegrity $Bundle

# ------------------------------------------------------------ PostgreSQL
$psql = Join-Path $PgBin "psql.exe"
if (-not (Test-Path $psql)) {
  throw "PostgreSQL istemci araçları bulunamadı: $PgBin. Önce PostgreSQL 16'yı EDB çevrimdışı kurucusuyla kur (KURULUM.md, 2. adım) veya -PgBin ile yolu ver."
}

# ------------------------------------------------------------ uygulama dosyaları
$version = Get-BundleVersion $Bundle
$appDir = Install-AppVersion -Bundle $Bundle -InstallRoot $InstallRoot -Version $version
Set-CurrentVersion -InstallRoot $InstallRoot -AppDir $appDir

# ------------------------------------------------------------ yapılandırma (ilk kurulum)
$configDir = Join-Path $InstallRoot "config"
$dataDir = Join-Path $InstallRoot "data"
$envFile = Join-Path $configDir "metis.env"
New-Item -ItemType Directory -Force -Path $configDir, $dataDir | Out-Null
if (-not (Test-Path $envFile)) {
  if (-not $PublicUrl) { throw "İlk kurulumda -PublicUrl gerekli (ör. https://metis.sirket.local)." }
  if (-not $PublicUrl.StartsWith("https://") -and -not $AllowHttp) { throw "-PublicUrl https:// ile başlamalı (TLS IIS/ARR'de sonlanır). Yalnız deneme için -AllowHttp." }
  Write-Step "Ana anahtar ve veritabanı rolleri oluşturuluyor"
  $keyFile = Join-Path $configDir "master.key"
  if (-not (Test-Path $keyFile)) {
    [IO.File]::WriteAllText($keyFile, [Convert]::ToBase64String((New-RandomBytes 32)))
  }
  $ownerPw = New-RandomSecret
  $appPw = New-RandomSecret
  $superPw = $env:METIS_PG_SUPERUSER_PASSWORD
  if (-not $superPw) {
    $sec = Read-Host -AsSecureString "PostgreSQL '$PgSuperUser' parolası (yalnız rolleri oluşturmak için kullanılır, kaydedilmez)"
    $superPw = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
  }
  Initialize-Database -Psql $psql -PgHost $PgHost -PgPort $PgPort -SuperUser $PgSuperUser -SuperPassword $superPw -OwnerPassword $ownerPw -AppPassword $appPw
  $superPw = $null
  $profile = if ($PublicUrl.StartsWith("https://")) { "production" } else { "development" }
  $lines = @(
    "# METIS yapılandırması — yalnız SYSTEM ve Administrators okuyabilir. Parolaları paylaşma.",
    "METIS_ENV=$profile",
    "METIS_PUBLIC_URL=$PublicUrl",
    "METIS_DATABASE_URL=postgresql+psycopg://metis_app:$appPw@${PgHost}:$PgPort/metis",
    "METIS_OWNER_DATABASE_URL=postgresql+psycopg://metis_owner:$ownerPw@${PgHost}:$PgPort/metis",
    "METIS_DATA_DIR=$dataDir",
    "METIS_MASTER_KEY_FILE=$keyFile",
    "METIS_STATIC_DIR=$(Join-Path $InstallRoot 'app\current\web')",
    "METIS_PG_BIN=$PgBin",
    "METIS_ENDPOINT_ALLOWLIST=$EndpointAllowlist",
    "METIS_TRUSTED_PROXIES=127.0.0.1,::1"
  )
  [IO.File]::WriteAllLines($envFile, $lines, (New-Object Text.UTF8Encoding($false)))
  Protect-ConfigDir $configDir
} else {
  Write-Step "Var olan yapılandırma korunuyor: $envFile"
}
$env:METIS_CONFIG = $envFile

# ------------------------------------------------------------ şema + denetim
Write-Step "Veritabanı şeması yükseltiliyor"
Invoke-Metis -AppDir $appDir -Arguments @("migrate")
Write-Step "metis doctor"
Invoke-Metis -AppDir $appDir -Arguments @("doctor") -AllowFailure | Out-Host

# ------------------------------------------------------------ servisler
if (-not $SkipServices) {
  Write-Step "Servisler kuruluyor (WinSW)"
  Install-MetisServices -Bundle $Bundle -InstallRoot $InstallRoot -ApiPort $ApiPort -ApiWorkers $ApiWorkers -WorkerSlots $WorkerSlots -EnvFile $envFile
  Wait-Healthy -Port $ApiPort -Seconds 90
} else {
  Write-Warning "Servis kurulumu atlandı (-SkipServices)."
}
if (-not $SkipScheduledTasks -and -not $SkipServices) {
  Register-MetisTasks -InstallRoot $InstallRoot -EnvFile $envFile
}

# ------------------------------------------------------------ ilk yönetici
Write-Step "Kurulum tamamlandı: METIS $version"
Write-Host "Sonraki adımlar:"
Write-Host "  1. IIS/ARR ters vekilini KURULUM.md 5. adıma göre yapılandır ($PublicUrl → http://127.0.0.1:$ApiPort)."
Write-Host "  2. İlk yönetici için kurulum kodu (24 saat, tek kullanım):"
Invoke-Metis -AppDir $appDir -Arguments @("setup-code") -AllowFailure | Out-Host
Write-Host "  3. Tarayıcıdan $PublicUrl adresini aç, kurulum kodunu gir."
Write-Host "  4. Ana anahtarı ($configDir\master.key) şirket kasasına yedekle. Anahtar olmadan yedekler geri yüklenemez."

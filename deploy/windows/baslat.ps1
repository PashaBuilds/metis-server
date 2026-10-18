<#
.SYNOPSIS
  METIS başlatıcısı: METIS-Baslat.exe bu betiği çalıştırır. Komut yazmadan kurar, yükseltir, başlatır, tarayıcıda açar.

.DESCRIPTION
  Çift tıklayınca durumu kendisi anlar:
   - PostgreSQL 16 yoksa: ne yapılacağını söyler (PostgreSQL'i bu paket kurmaz).
   - METIS kurulu değilse: onay ister, yönetici izni (UAC) alır, deneme modunda kurar (yalnız bu bilgisayardan,
     http://localhost:8000), isterse kurgusal örnek içeriği ekler, kurulum kodunu hazırlayıp tarayıcıda açar.
   - Kurulu sürüm bu paketten eskiyse: yükseltmeyi önerir (önce yedek alınır).
   - Servisler kapalıysa başlatır; ilk yönetici henüz yoksa yeni kurulum kodu üretir.
   - Sonunda METIS'i Chrome'da (yoksa varsayılan tarayıcıda) açar.
  Yönetici izni yalnız gerektiğinde istenir. Ağ üzerinden erişilecek sunucu kurulumu için KURULUM.md (IIS + TLS).

  Otomasyon/CI için: -Onayla (soru sormaz), -DemoYok, -TarayiciAcma, -SonucDosyasi (durumu JSON yazar), -Durum
  (yalnız durumu yazar, bir şey değiştirmez).
#>
[CmdletBinding()]
param(
  [string]$InstallRoot = "C:\METIS",
  [string]$PgBin = "C:\Program Files\PostgreSQL\16\bin",
  [int]$ApiPort = 8000,
  [switch]$Durum,
  [switch]$Onayla,
  [switch]$DemoYok,
  [switch]$TarayiciAcma,
  [string]$SonucDosyasi = "",
  # Yalnız yükseltilmiş (yönetici) alt süreç için:
  [ValidateSet("", "kur", "yukselt", "servis", "kod")]
  [string]$Islem = "",
  [string]$KodDosyasi = "",
  [switch]$Demo
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$Bundle = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $Bundle "metis-common.ps1")
try { $Host.UI.RawUI.WindowTitle = "METIS başlatıcı" } catch { }

function Test-IsAdmin {
  $id = [Security.Principal.WindowsIdentity]::GetCurrent()
  return (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Show-Message([string]$Text, [string]$Kind = "Information", [string]$Buttons = "OK") {
  if ($Onayla) { Write-Host $Text; return "Yes" }
  Add-Type -AssemblyName System.Windows.Forms
  # Başlatıcının penceresi gizli: ileti kutusu başka pencerelerin arkasında kalmasın diye en üstte duran bir sahibe bağlanır.
  $owner = New-Object System.Windows.Forms.Form -Property @{ TopMost = $true; ShowInTaskbar = $false }
  try { return [string][System.Windows.Forms.MessageBox]::Show($owner, $Text, "METIS", $Buttons, $Kind) } finally { $owner.Dispose() }
}

function Get-InstalledVersion {
  $dir = Get-CurrentAppDir $InstallRoot
  if (-not $dir) { return $null }
  $marker = Join-Path $dir ".installed"
  if (-not (Test-Path $marker)) { return $null }
  return (Get-Content $marker -TotalCount 1).Trim()
}

function Get-VersionKey([string]$Version) {
  # "2.0.0-rc.7+ci2" → (2,0,0, 7, "+ci2"); son sürüm (rc'siz) aynı tabandaki tüm rc'lerden yenidir.
  $m = [regex]::Match($Version, '^(\d+)\.(\d+)\.(\d+)(?:-rc\.(\d+))?(.*)$')
  if (-not $m.Success) { return $null }
  $rc = if ($m.Groups[4].Success) { [int]$m.Groups[4].Value } else { [int]::MaxValue }
  return @([int]$m.Groups[1].Value, [int]$m.Groups[2].Value, [int]$m.Groups[3].Value, $rc, $m.Groups[5].Value)
}

function Compare-MetisVersion([string]$A, [string]$B) {
  # -1: A eski, 0: aynı, 1: A yeni. Okunamayan sürüm "farklı ama sırası bilinmiyor" sayılır (2).
  if ($A -eq $B) { return 0 }
  $ka = Get-VersionKey $A; $kb = Get-VersionKey $B
  if (-not $ka -or -not $kb) { return 2 }
  for ($i = 0; $i -lt 4; $i++) {
    if ($ka[$i] -lt $kb[$i]) { return -1 }
    if ($ka[$i] -gt $kb[$i]) { return 1 }
  }
  return 2  # yalnız derleme eki farklı (ör. +ci2): yükseltilebilir, sıra bilinmiyor
}

function Get-PublicUrl {
  $file = Join-Path $InstallRoot "adres.txt"
  if (Test-Path $file) {
    $url = (Get-Content $file -TotalCount 1).Trim()
    if ($url) { return $url.TrimEnd("/") }
  }
  return "http://localhost:$ApiPort"
}

function Get-Health {
  try { return (Get-LocalUrl "http://127.0.0.1:$ApiPort/api/v1/health/ready").Status -eq 200 } catch { return $false }
}

function Get-NeedsSetup {
  try {
    $r = Get-LocalUrl "http://127.0.0.1:$ApiPort/api/v1/setup/status"
    if ($r.Status -eq 200) { return [bool]($r.Body | ConvertFrom-Json).needs_setup }
  } catch { }
  return $false
}

function Get-State {
  $installed = [bool](Get-Service -Name "metis-api" -ErrorAction SilentlyContinue)
  $healthy = if ($installed) { Get-Health } else { $false }
  return [ordered]@{
    paket_surumu    = Get-BundleVersion $Bundle
    kurulu_surum    = if ($installed) { Get-InstalledVersion } else { $null }
    postgresql      = (Test-Path (Join-Path $PgBin "psql.exe"))
    kurulu          = $installed
    calisiyor       = $healthy
    kurulum_gerekli = if ($healthy) { Get-NeedsSetup } else { $false }
    adres           = Get-PublicUrl
  }
}

function Write-Result($State, [string]$Note) {
  if (-not $SonucDosyasi) { return }
  $State["sonuc"] = $Note
  [IO.File]::WriteAllText($SonucDosyasi, ($State | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))
}

function Invoke-Elevated([string]$Action, [string]$CodeFile = "", [switch]$WithDemo) {
  $named = [ordered]@{ "-Islem" = $Action; "-InstallRoot" = $InstallRoot; "-PgBin" = $PgBin; "-ApiPort" = "$ApiPort" }
  if ($CodeFile) { $named["-KodDosyasi"] = $CodeFile }
  $flags = @()
  if ($WithDemo) { $flags += "-Demo" }
  if ($Onayla) { $flags += "-Onayla" }
  if ($Onayla -and (Test-IsAdmin)) {
    # Otomasyon (CI): soru yok, zaten yönetici; aynı süreçte çalış (PowerShell argümanları kendisi tırnaklar).
    $direct = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $PSCommandPath)
    foreach ($k in $named.Keys) { $direct += @($k, $named[$k]) }
    & powershell.exe @($direct + $flags) | Out-Host  # çıktı ekrana; işlevin dönüş değeri yalnız çıkış kodu olsun
    return $LASTEXITCODE
  }
  # Start-Process argümanları boşlukla birleştirir: boşluk içeren değerler elle tırnaklanır.
  $line = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
  foreach ($k in $named.Keys) { $line += " $k `"$($named[$k])`"" }
  if ($flags) { $line += " " + ($flags -join " ") }
  try {
    # Her zaman görünür bir pencere: kurulumda PostgreSQL parolası orada sorulur, ilerleme orada görünür.
    # Zaten yöneticiysek (exe "yönetici olarak" açıldıysa) UAC istenmez.
    if (Test-IsAdmin) { $p = Start-Process -FilePath "powershell.exe" -ArgumentList $line -Wait -PassThru }
    else { $p = Start-Process -FilePath "powershell.exe" -ArgumentList $line -Verb RunAs -Wait -PassThru }
    return $p.ExitCode
  } catch {
    Show-Message "Yönetici izni verilmedi; METIS kurulamadı ya da başlatılamadı." "Warning" | Out-Null
    return 1223
  }
}

function Open-Browser([string]$Url) {
  if ($TarayiciAcma) { Write-Host "Tarayıcı açılmadı (-TarayiciAcma): $Url"; return }
  $chrome = $null
  foreach ($hive in @("HKCU:", "HKLM:")) {
    $key = "$hive\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"
    if (Test-Path $key) { $chrome = (Get-ItemProperty $key).'(default)'; if ($chrome) { break } }
  }
  if ($chrome -and (Test-Path $chrome)) { Start-Process -FilePath $chrome -ArgumentList $Url }
  else { Start-Process $Url }
}

function Read-CodeFile([string]$File) {
  if (-not (Test-Path $File)) { return "" }
  $code = (Get-Content $File -TotalCount 1).Trim()
  Remove-Item -Force $File -ErrorAction SilentlyContinue
  return $code
}

function New-CodeFile { return Join-Path ([IO.Path]::GetTempPath()) ("metis-kod-" + [guid]::NewGuid().ToString("N") + ".txt") }

# ======================================================================= yönetici alt süreci
if ($Islem) {
  $env:METIS_CONFIG = Join-Path $InstallRoot "config\metis.env"
  try {
    switch ($Islem) {
      "kur" {
        & (Join-Path $Bundle "install-offline.ps1") -InstallRoot $InstallRoot -PublicUrl "http://localhost:$ApiPort" -AllowHttp -PgBin $PgBin -ApiPort $ApiPort -SetupCodeFile $KodDosyasi
        $wantDemo = $Demo -or (-not $Onayla -and (Show-Message "METIS kuruldu.`n`nDenemek için kurgusal örnek içerik (sayfalar, kaynaklar, örnek kullanıcılar) eklensin mi?`n`nŞirketin gerçek bilgilerini gireceğin kurulumda 'Hayır' de." "Question" "YesNo") -eq "Yes")
        if ($wantDemo) {
          Write-Step "Kurgusal örnek içerik ekleniyor"
          & (Join-Path $InstallRoot "bin\metis.cmd") demo | Out-Host
          if ($LASTEXITCODE -ne 0) { throw "Kurgusal örnek içerik eklenemedi." }
        }
      }
      "yukselt" { & (Join-Path $Bundle "upgrade.ps1") -InstallRoot $InstallRoot -ApiPort $ApiPort }
      "servis" {
        Write-Step "Servisler başlatılıyor"
        Start-MetisServices $InstallRoot
        Wait-Healthy -Port $ApiPort -Seconds 90
      }
      "kod" {
        $code = Get-SetupCode (Get-CurrentAppDir $InstallRoot)
        if ($KodDosyasi -and $code) { [IO.File]::WriteAllText($KodDosyasi, $code) }
      }
    }
    exit 0
  } catch {
    Write-Host ""
    Write-Host "HATA: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Günlükler: $InstallRoot\data\logs. Bu pencereyi kapatmadan önce mesajı not al."
    if (-not $Onayla) { Read-Host "Kapatmak için Enter'a bas" | Out-Null }
    exit 1
  }
}

# ======================================================================= kullanıcı tarafı
# Başlatıcı penceresi gizlidir: beklenmeyen bir hata sessiz kalmasın, ileti kutusuyla gösterilsin.
trap {
  Show-Message "Beklenmeyen hata: $($_.Exception.Message)`n`nPaket klasöründe KURULUM.md 'Sorun giderme' bölümüne bak." "Error" | Out-Null
  Write-Result ([ordered]@{}) "hata: $($_.Exception.Message)"
  exit 1
}
foreach ($f in Get-ChildItem -Path $Bundle -Recurse -File -ErrorAction SilentlyContinue) {
  Unblock-File -Path $f.FullName -ErrorAction SilentlyContinue  # internetten inen ZIP'in "engellendi" işareti
}
$state = Get-State
if ($Durum) { Write-Result $state "durum"; $state | ConvertTo-Json | Write-Host; exit 0 }

$bundleVersion = $state.paket_surumu
if (-not $state.kurulu) {
  if (-not $state.postgresql) {
    Show-Message ("PostgreSQL 16 bulunamadı ($PgBin).`n`nÖnce PostgreSQL 16 kurucusunu çalıştır:`n" +
      "  • Locale adımında 'English, United States' seç`n  • 'postgres' parolasını not al (kurulumda bir kez sorulur)`n" +
      "  • Son ekranda Stack Builder işaretini kaldır`n`nSonra METIS-Baslat'ı yeniden aç. Ayrıntı: KURULUM.md, 2. bölüm.") "Warning" | Out-Null
    Write-Result $state "postgresql_yok"; exit 2
  }
  $ok = Show-Message ("METIS $bundleVersion bu bilgisayara kurulacak (deneme modu: yalnız bu bilgisayardan, http://localhost:$ApiPort).`n`n" +
    "Yönetici izni istenecek; açılan pencerede PostgreSQL 'postgres' parolası bir kez sorulacak. Birkaç dakika sürer.`n`nDevam edilsin mi?") "Question" "YesNo"
  if ($ok -ne "Yes") { Write-Result $state "vazgecildi"; exit 0 }
  $codeFile = New-CodeFile
  # Soru sormadan (-Onayla) kurulumda örnek içerik eklenir; -DemoYok ile eklenmez. Etkileşimli kurulumda sorulur.
  $rc = Invoke-Elevated "kur" $codeFile -WithDemo:($Onayla -and -not $DemoYok)
  $code = Read-CodeFile $codeFile
  $state = Get-State
  if ($rc -ne 0 -or -not $state.calisiyor) { Write-Result $state "kurulum_basarisiz"; exit 1 }
  $url = Get-PublicUrl
  Open-Browser $(if ($code) { "$url/kurulum#kod=$code" } else { $url })
  Write-Result $state "kuruldu"; exit 0
}

$installedVersion = $state.kurulu_surum
if ($installedVersion -and $installedVersion -ne $bundleVersion) {
  $cmp = Compare-MetisVersion $bundleVersion $installedVersion
  if ($cmp -eq -1) {
    Show-Message "Bu paket ($bundleVersion) kurulu sürümden ($installedVersion) eski; yükseltme yapılmadı. Kurulu METIS açılıyor." "Information" | Out-Null
  } else {
    $ok = Show-Message ("Kurulu sürüm: $installedVersion`nBu paket: $bundleVersion`n`nMETIS bu pakete yükseltilsin mi? Önce yedek alınır; sorun çıkarsa eski sürüme dönülür.") "Question" "YesNo"
    if ($ok -eq "Yes") {
      $rc = Invoke-Elevated "yukselt"
      $state = Get-State
      if ($rc -ne 0) { Show-Message "Yükseltme tamamlanamadı. Ayrıntı açılan pencerede ve $InstallRoot\data\logs altında." "Error" | Out-Null; Write-Result $state "yukseltme_basarisiz"; exit 1 }
    }
  }
}

if (-not $state.calisiyor) {
  $rc = Invoke-Elevated "servis"
  $state = Get-State
  if ($rc -ne 0 -or -not $state.calisiyor) {
    Show-Message "METIS başlatılamadı. Günlükler: $InstallRoot\data\logs\service" "Error" | Out-Null
    Write-Result $state "baslatilamadi"; exit 1
  }
}

$url = Get-PublicUrl
if ($state.kurulum_gerekli) {
  # Kurulum yarım kalmış (ilk yönetici yok): yeni tek kullanımlık kod üret ve kurulum sayfasını aç.
  $codeFile = New-CodeFile
  Invoke-Elevated "kod" $codeFile | Out-Null
  $code = Read-CodeFile $codeFile
  Open-Browser $(if ($code) { "$url/kurulum#kod=$code" } else { "$url/kurulum" })
} else {
  Open-Browser $url
}
Write-Result $state "acildi"
exit 0

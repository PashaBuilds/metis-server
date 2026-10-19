<#
.SYNOPSIS
  Kurulu METIS'i şirket ağından http://<makine-tam-adı>/metis adresinde açar: IIS, 80 portunda /metis altına gelen
  istekleri METIS'e (127.0.0.1:8000) iletir. Kök (/) ve diğer yollar makinedeki başka işlere kalır.

.DESCRIPTION
  METIS-Baslat.exe ile (ya da install-offline.ps1 -AllowHttp ile) kurulmuş bir METIS'e, aynı makinede yönetici
  PowerShell ile:
      powershell -ExecutionPolicy Bypass -File .\ag-erisimi.ps1

  Adımlar (tekrar çalıştırılabilir; yapılmış adımı atlar):
   1. IIS açılır (Windows 10/11: Windows özelliği; Windows Server: Web-Server rolü).
   2. IIS URL Rewrite 2.1 ve Application Request Routing 3.0 kurulu değilse, bu klasördeki ya da İndirilenler'deki
      rewrite_amd64*.msi ve requestRouter_amd64*.msi kurulur (dosyalar Microsoft'tan bir kez indirilir).
   3. Vekil açılır, yanıt tamponu kapatılır (Mentor akışı parça parça gelsin).
   4. Default Web Site (80) altında /metis uygulaması kurulur; web.config yazılır. 2.0.12'nin kökü kaplayan "METIS"
      sitesi varsa kaldırılır ve Default Web Site yeniden başlatılır.
   5. METIS_PUBLIC_URL http://<ad>.<alan-adı>/metis olur; servisler yeniden başlar. Başka yol için: -Yol /bilgi
   6. Güvenlik duvarında 80 portu (etki alanı ve özel ağ) açılır; adres bu makineden denenir.

  http şifresizdir: deneme profili (development) içindir. Kalıcı kullanımda şirket sertifikasıyla https'e geçilir
  (KURULUM.md, 5. adım).
#>
[CmdletBinding()]
param(
  [string]$InstallRoot = "C:\METIS",
  [string]$Adres = "",
  [string]$KurucuKlasoru = "",
  [int]$ApiPort = 8000,
  [string]$SiteKlasoru = "C:\inetpub\metis",
  [string]$Yol = "/metis"
)

$ErrorActionPreference = "Stop"
$Bundle = $PSScriptRoot
. (Join-Path $Bundle "metis-common.ps1")

$appcmd = Join-Path $env:windir "system32\inetsrv\appcmd.exe"

function Invoke-AppCmd([string[]]$Arguments, [switch]$AllowFailure) {
  $ErrorActionPreference = "Continue"
  $out = & $appcmd @Arguments 2>&1
  if ($LASTEXITCODE -ne 0 -and -not $AllowFailure) { throw "appcmd $($Arguments -join ' ') başarısız: $out" }
  return ($out | Out-String)
}

function Get-FullName {
  # Makinenin DNS'teki tam adı (ör. vm-adi.sirket.com.tr); şirket DNS'i bu adı diğer bilgisayarlara çözer.
  $name = [System.Net.Dns]::GetHostEntry($env:COMPUTERNAME).HostName
  if (-not $name) { $name = $env:COMPUTERNAME }
  return $name.ToLowerInvariant()
}

function Find-Installer([string]$Pattern) {
  $dirs = @($KurucuKlasoru, $Bundle, (Join-Path $env:USERPROFILE "Downloads")) | Where-Object { $_ -and (Test-Path $_) }
  foreach ($d in $dirs) {
    $f = Get-ChildItem -Path $d -Filter $Pattern -File -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($f) { return $f.FullName }
  }
  return $null
}

function Install-Msi([string]$Pattern, [string]$Name) {
  $msi = Find-Installer $Pattern
  if (-not $msi) {
    throw ("$Name kurulu değil ve kurucusu bulunamadı ($Pattern).`n" +
      "Microsoft'un sitesinden indir (64 bit), bu klasöre ya da İndirilenler'e koy ve betiği yeniden çalıştır:`n" +
      "  - IIS URL Rewrite 2.1: rewrite_amd64_tr-TR.msi (ya da _en-US)`n" +
      "  - Application Request Routing 3.0: requestRouter_amd64.msi")
  }
  Write-Host "  kuruluyor: $msi"
  $p = Start-Process msiexec.exe -ArgumentList @("/i", "`"$msi`"", "/qn", "/norestart") -Wait -PassThru
  if ($p.ExitCode -notin @(0, 3010)) { throw "$Name kurulamadı (msiexec çıkış kodu $($p.ExitCode))." }
}

function Set-EnvValue([string]$File, [string]$Key, [string]$Value) {
  $lines = @(Get-Content $File)
  $found = $false
  $lines = $lines | ForEach-Object {
    if ($_ -like "$Key=*") { $found = $true; "$Key=$Value" } else { $_ }
  }
  if (-not $found) { $lines += "$Key=$Value" }
  [IO.File]::WriteAllLines($File, [string[]]$lines, (New-Object Text.UTF8Encoding $false))
}

function Get-EnvValue([string]$File, [string]$Key) {
  $line = Get-Content $File | Where-Object { $_ -like "$Key=*" } | Select-Object -First 1
  if ($line) { return $line.Substring($Key.Length + 1).Trim() }
  return ""
}

try {
  Assert-Admin
  $envFile = Join-Path $InstallRoot "config\metis.env"
  if (-not (Test-Path $envFile)) { throw "Kurulu METIS bulunamadı ($envFile). Önce METIS-Baslat.exe ile kur." }
  if ((Get-EnvValue $envFile "METIS_ENV") -eq "production") {
    throw "Bu METIS https (production) profilinde kurulu; bu betik http deneme kurulumları içindir. KURULUM.md 5. adıma bak."
  }
  if (-not $Adres) { $Adres = Get-FullName }
  $Adres = $Adres.Trim().TrimEnd("/") -replace "^https?://", ""
  $Yol = "/" + $Yol.Trim().Trim("/")
  if ($Yol -notmatch '^/[A-Za-z0-9._-]+$') { throw "-Yol tek bir alt yol olmalı (ör. /metis)." }
  $publicUrl = "http://$Adres$Yol"
  Write-Host "Adres: $publicUrl"

  Write-Step "IIS açılıyor"
  if (-not (Test-Path $appcmd)) {
    $os = Get-CimInstance Win32_OperatingSystem
    if ($os.ProductType -eq 1) {
      $features = @("IIS-WebServerRole", "IIS-WebServer", "IIS-CommonHttpFeatures", "IIS-StaticContent",
        "IIS-DefaultDocument", "IIS-HttpErrors", "IIS-RequestFiltering", "IIS-HttpCompressionStatic", "IIS-ManagementConsole")
      Enable-WindowsOptionalFeature -Online -FeatureName $features -All -NoRestart | Out-Null
    } else {
      Install-WindowsFeature Web-Server -IncludeManagementTools | Out-Null
    }
  }
  if (-not (Test-Path $appcmd)) {
    Write-Host ""
    Write-Host "IIS açıldı; Windows'un bunu tamamlaması için yeniden başlatma gerekiyor." -ForegroundColor Yellow
    Write-Host "Makineyi yeniden başlat, sonra bu betiği aynı komutla tekrar çalıştır (yapılan adımlar atlanır)." -ForegroundColor Yellow
    exit 3
  }
  Write-Host "  IIS hazır."

  Write-Step "URL Rewrite ve Application Request Routing"
  if (-not (Test-Path (Join-Path $env:windir "system32\inetsrv\rewrite.dll"))) { Install-Msi "rewrite_amd64*.msi" "IIS URL Rewrite 2.1" }
  if (-not (Test-Path (Join-Path $env:ProgramFiles "IIS\Application Request Routing\requestRouter.dll"))) {
    Install-Msi "requestRouter_amd64*.msi" "Application Request Routing 3.0"
  }
  Write-Host "  ikisi de kurulu."

  Write-Step "Vekil ayarları (yanıt tamponu kapalı: Mentor akışı)"
  Invoke-AppCmd @("set", "config", "-section:system.webServer/proxy", "/enabled:True", "/preserveHostHeader:True", "/timeout:00:10:00", "/responseBufferLimit:0", "/commit:apphost") | Out-Null
  $vars = Invoke-AppCmd @("list", "config", "-section:system.webServer/rewrite/allowedServerVariables")
  if ($vars -notmatch "HTTP_X_FORWARDED_PROTO") {
    Invoke-AppCmd @("set", "config", "-section:system.webServer/rewrite/allowedServerVariables", "/+[name='HTTP_X_FORWARDED_PROTO']", "/commit:apphost") | Out-Null
  }

  Write-Step "METIS uygulaması: Default Web Site$Yol (80 portu)"
  New-Item -ItemType Directory -Force -Path $SiteKlasoru | Out-Null
  $webConfig = @"
<?xml version="1.0" encoding="UTF-8"?>
<!-- ag-erisimi.ps1 yazdı: http://<ad>$Yol → METIS (127.0.0.1:$ApiPort$Yol). Yalnız bu IIS uygulamasına ($Yol) uygulanır. -->
<configuration>
  <system.webServer>
    <rewrite>
      <rules>
        <rule name="METIS" stopProcessing="true">
          <match url="(.*)" />
          <serverVariables>
            <set name="HTTP_X_FORWARDED_PROTO" value="http" />
          </serverVariables>
          <action type="Rewrite" url="http://127.0.0.1:$ApiPort$Yol/{R:1}" />
        </rule>
      </rules>
    </rewrite>
    <urlCompression doStaticCompression="true" doDynamicCompression="false" />
    <security>
      <requestFiltering>
        <requestLimits maxAllowedContentLength="12582912" />
      </requestFiltering>
    </security>
  </system.webServer>
</configuration>
"@
  [IO.File]::WriteAllText((Join-Path $SiteKlasoru "web.config"), $webConfig, (New-Object Text.UTF8Encoding $false))
  $sites = Invoke-AppCmd @("list", "site")
  if ($sites -match '"METIS"') {
    # 2.0.12 METIS'i ayrı bir sitede kökten yayınlıyor, Default Web Site'ı durduruyordu; kök artık diğer işlere kalır.
    Write-Host "  önceki kök 'METIS' sitesi kaldırılıyor"
    Invoke-AppCmd @("stop", "site", "METIS") -AllowFailure | Out-Null
    Invoke-AppCmd @("delete", "site", "METIS") | Out-Null
  }
  if ($sites -notmatch '"Default Web Site"') {
    $root = Join-Path $env:SystemDrive "inetpub\wwwroot"
    New-Item -ItemType Directory -Force -Path $root | Out-Null
    Invoke-AppCmd @("add", "site", "/name:Default Web Site", "/bindings:http/*:80:", "/physicalPath:$root") | Out-Null
  }
  Invoke-AppCmd @("set", "site", "Default Web Site", "/serverAutoStart:true") | Out-Null
  Invoke-AppCmd @("start", "site", "Default Web Site") -AllowFailure | Out-Null
  $appId = "Default Web Site$Yol"
  if ((Invoke-AppCmd @("list", "app", $appId) -AllowFailure) -match [regex]::Escape("`"$appId`"")) {
    Invoke-AppCmd @("set", "app", $appId, "/[path='/'].physicalPath:$SiteKlasoru") | Out-Null
  } else {
    Invoke-AppCmd @("add", "app", "/site.name:Default Web Site", "/path:$Yol", "/physicalPath:$SiteKlasoru") | Out-Null
  }

  Write-Step "METIS adresi: $publicUrl"
  Set-EnvValue $envFile "METIS_PUBLIC_URL" $publicUrl
  Write-PublicUrlFile $InstallRoot $envFile
  Stop-MetisServices $InstallRoot
  Start-MetisServices $InstallRoot
  Wait-Healthy $ApiPort 120

  Write-Step "Güvenlik duvarı (80, etki alanı ve özel ağ)"
  if (-not (Get-NetFirewallRule -DisplayName "METIS HTTP (80)" -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName "METIS HTTP (80)" -Direction Inbound -Protocol TCP -LocalPort 80 -Action Allow -Profile Domain, Private | Out-Null
  }
  Write-Host "  kural hazır."

  Write-Step "Adres deneniyor: $publicUrl/api/v1/health/ready"
  $ok = $false
  for ($i = 0; $i -lt 20 -and -not $ok; $i++) {
    try { $ok = (Get-LocalUrl "$publicUrl/api/v1/health/ready").Status -eq 200 } catch { }
    if (-not $ok) { Start-Sleep -Seconds 2 }
  }
  if (-not $ok) {
    throw "METIS çalışıyor ama $publicUrl bu makineden açılmadı. IIS Yöneticisi'nde METIS sitesini ve C:\inetpub\logs'u kontrol et."
  }
  Write-Host ""
  Write-Host "Hazır. Şirket ağındaki bilgisayarlardan aç: $publicUrl" -ForegroundColor Green
  Write-Host "Adresi her zaman bu tam adla yaz (kısa ad ya da IP ile giriş yapılamaz). Kök (/) ve diğer yollar METIS'in değil."
  exit 0
} catch {
  Write-Host ""
  Write-Host "HATA: $($_.Exception.Message)" -ForegroundColor Red
  exit 1
}

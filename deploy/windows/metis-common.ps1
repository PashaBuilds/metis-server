# install-offline.ps1 ve upgrade.ps1 tarafından ortak kullanılan yardımcılar. Doğrudan çalıştırılmaz.

function Write-Step([string]$Text) { Write-Host ""; Write-Host "==> $Text" -ForegroundColor Cyan }

function Assert-Admin {
  $id = [Security.Principal.WindowsIdentity]::GetCurrent()
  $p = New-Object Security.Principal.WindowsPrincipal($id)
  if (-not $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Bu betik yönetici olarak çalıştırılmalı (PowerShell → Yönetici olarak çalıştır)."
  }
}

function Get-BundleVersion([string]$Bundle) { (Get-Content (Join-Path $Bundle "VERSION") -TotalCount 1).Trim() }

function Test-BundleIntegrity([string]$Bundle) {
  Write-Step "Paket bütünlüğü doğrulanıyor (SHA256SUMS)"
  $sums = Join-Path $Bundle "SHA256SUMS"
  if (-not (Test-Path $sums)) { throw "SHA256SUMS bulunamadı; paket eksik." }
  $bad = @()
  $n = 0
  foreach ($line in Get-Content $sums) {
    if (-not $line.Trim()) { continue }
    $hash, $rel = $line -split "  ", 2
    $file = Join-Path $Bundle ($rel -replace "/", [IO.Path]::DirectorySeparatorChar)
    $n++
    if (-not (Test-Path -LiteralPath $file)) { $bad += "eksik: $rel"; continue }
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $file).Hash.ToLowerInvariant()
    if ($actual -ne $hash) { $bad += "değişmiş: $rel" }
  }
  if ($bad.Count -gt 0) { throw ("Paket bütünlüğü bozuk; kurulum durduruldu:`n  " + ($bad -join "`n  ")) }
  Write-Host "  $n dosya doğrulandı."
}

function New-RandomBytes([int]$Count) {
  $b = New-Object byte[] $Count
  [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
  return $b
}

function New-RandomSecret { ((New-RandomBytes 24) | ForEach-Object { $_.ToString("x2") }) -join "" }

function Get-PythonExe([string]$AppDir) {
  $win = Join-Path $AppDir "python\python.exe"
  if (Test-Path $win) { return $win }
  return (Join-Path $AppDir "python/bin/python")  # yalnız Linux üzerinde betik testi
}

function Install-AppVersion([string]$Bundle, [string]$InstallRoot, [string]$Version) {
  $appDir = Join-Path $InstallRoot "app\$Version"
  if (Test-Path (Join-Path $appDir ".installed")) {
    Write-Step "Sürüm $Version zaten kurulu: $appDir"
    return $appDir
  }
  Write-Step "Uygulama dosyaları kuruluyor: $appDir"
  if (Test-Path $appDir) { Remove-Item -Recurse -Force $appDir }
  New-Item -ItemType Directory -Force -Path $appDir | Out-Null
  $pyDir = Join-Path $appDir "python"
  Expand-Archive -Path (Join-Path $Bundle "runtime\python-embed-amd64.zip") -DestinationPath $pyDir | Out-Null
  # Gömülü Python site-packages'ı varsayılan olarak yüklemez; ._pth dosyasında açılır.
  $pth = Get-ChildItem -Path $pyDir -Filter "python*._pth" | Select-Object -First 1
  $zipName = (Get-ChildItem -Path $pyDir -Filter "python*.zip" | Select-Object -First 1).Name
  [IO.File]::WriteAllLines($pth.FullName, @($zipName, ".", "Lib\site-packages", "import site"))
  $py = Join-Path $pyDir "python.exe"
  & $py (Join-Path $Bundle "runtime\pip.pyz") install --no-index --find-links (Join-Path $Bundle "wheelhouse") `
      --require-hashes -r (Join-Path $Bundle "requirements.lock") --no-warn-script-location --disable-pip-version-check | Out-Host
  if ($LASTEXITCODE -ne 0) { throw "Tekerlek kurulumu başarısız (pip çıkış kodu $LASTEXITCODE)." }
  Copy-Item -Recurse -Path (Join-Path $Bundle "web") -Destination (Join-Path $appDir "web") | Out-Null
  Set-Content -Path (Join-Path $appDir ".installed") -Value $Version
  # PowerShell işlevleri boru hattındaki tüm çıktıyı döndürür; yalnız yol dönsün diye yukarıdaki çıktılar Out-Host/Out-Null'a gider.
  return $appDir
}

function Get-CurrentAppDir([string]$InstallRoot) {
  $cur = Join-Path $InstallRoot "app\current"
  if (-not (Test-Path $cur)) { return $null }
  $item = Get-Item $cur
  if ($item.LinkType -eq "Junction" -or $item.LinkType -eq "SymbolicLink") { return [string]($item.Target | Select-Object -First 1) }
  return $cur
}

function Set-CurrentVersion([string]$InstallRoot, [string]$AppDir) {
  $cur = Join-Path $InstallRoot "app\current"
  if (Test-Path $cur) { (Get-Item $cur).Delete() }
  New-Item -ItemType Junction -Path $cur -Target $AppDir | Out-Null
  Write-Host "  app\current → $AppDir"
}

function Invoke-Metis([string]$AppDir, [string[]]$Arguments, [switch]$AllowFailure) {
  $py = Get-PythonExe $AppDir
  $out = & $py -m metis.cli @Arguments 2>&1
  $code = $LASTEXITCODE
  if ($code -ne 0 -and -not $AllowFailure) {
    throw ("metis $($Arguments -join ' ') başarısız (kod $code):`n" + ($out | Out-String))
  }
  return $out
}

function Invoke-Psql([string]$Psql, [string]$PgHost, [int]$PgPort, [string]$User, [string]$Password, [string]$Database, [string]$Sql) {
  # Çağıranın PGPASSWORD değeri korunur (betik aynı PowerShell oturumunda çalıştırılabilir).
  $previous = $env:PGPASSWORD
  $env:PGPASSWORD = $Password
  try {
    # SQL stdin'den verilir: parolalar komut satırında (süreç listesinde) görünmez. -w: parola asla sorulmaz.
    $out = $Sql | & $Psql -X -q -w -v ON_ERROR_STOP=1 -h $PgHost -p $PgPort -U $User -d $Database -t -A -f - 2>&1
    if ($LASTEXITCODE -ne 0) { throw "psql hatası: $($out | Out-String)" }
    return ($out | Out-String).Trim()
  } finally {
    if ($null -ne $previous) { $env:PGPASSWORD = $previous } else { Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue }
  }
}

function Initialize-Database([string]$Psql, [string]$PgHost, [int]$PgPort, [string]$SuperUser, [string]$SuperPassword, [string]$OwnerPassword, [string]$AppPassword) {
  $roles = @"
DO `$`$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'metis_owner') THEN
    CREATE ROLE metis_owner LOGIN CREATEDB PASSWORD '$OwnerPassword';
  ELSE
    ALTER ROLE metis_owner LOGIN CREATEDB PASSWORD '$OwnerPassword';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'metis_app') THEN
    CREATE ROLE metis_app LOGIN PASSWORD '$AppPassword';
  ELSE
    ALTER ROLE metis_app LOGIN PASSWORD '$AppPassword';
  END IF;
END `$`$;
"@
  Invoke-Psql $Psql $PgHost $PgPort $SuperUser $SuperPassword "postgres" $roles | Out-Null
  $exists = Invoke-Psql $Psql $PgHost $PgPort $SuperUser $SuperPassword "postgres" "SELECT 1 FROM pg_database WHERE datname = 'metis';"
  if ($exists -ne "1") {
    Invoke-Psql $Psql $PgHost $PgPort $SuperUser $SuperPassword "postgres" "CREATE DATABASE metis OWNER metis_owner ENCODING 'UTF8' TEMPLATE template0;" | Out-Null
  }
  $schema = @"
CREATE EXTENSION IF NOT EXISTS pg_trgm;
ALTER SCHEMA public OWNER TO metis_owner;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO metis_app;
"@
  Invoke-Psql $Psql $PgHost $PgPort $SuperUser $SuperPassword "metis" $schema | Out-Null
  Write-Host "  roller metis_owner (migration/yedek) ve metis_app (çalışma zamanı) hazır; veritabanı 'metis'."
}

function Get-SetupCode([string]$AppDir) {
  # Tek kullanımlık ilk yönetici kodu (XXXX-XXXX-XXXX-XXXX). Yönetici zaten varsa boş döner.
  $out = Invoke-Metis -AppDir $AppDir -Arguments @("setup-code") -AllowFailure
  $m = $out | ForEach-Object { "$_".Trim() } | Where-Object { $_ -match '^[A-Z2-9]{4}(-[A-Z2-9]{4}){3}$' } | Select-Object -Last 1
  if ($m) { return [string]$m }
  return ""
}

function Write-PublicUrlFile([string]$InstallRoot, [string]$EnvFile) {
  # Başlatıcı, yönetici izni olmadan hangi adresi açacağını buradan okur (metis.env yalnız yöneticilere açık).
  # Gizli değildir: yalnız METIS_PUBLIC_URL.
  $line = Get-Content $EnvFile | Where-Object { $_ -like "METIS_PUBLIC_URL=*" } | Select-Object -First 1
  if ($line) {
    [IO.File]::WriteAllText((Join-Path $InstallRoot "adres.txt"), $line.Substring("METIS_PUBLIC_URL=".Length).Trim())
  }
}

function Protect-ConfigDir([string]$Dir) {
  # SID'ler dil bağımsızdır (Türkçe Windows'ta 'Yöneticiler'). Kalıtım kaldırılır: yalnız SYSTEM + Administrators.
  & icacls $Dir /inheritance:r /grant:r "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F" | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "Yapılandırma klasörünün izinleri ayarlanamadı: $Dir" }
}

function Write-MetisCmd([string]$InstallRoot, [string]$EnvFile) {
  $bin = Join-Path $InstallRoot "bin"
  New-Item -ItemType Directory -Force -Path $bin | Out-Null
  $cmd = @(
    "@echo off",
    "set METIS_CONFIG=$EnvFile",
    "`"$(Join-Path $InstallRoot 'app\current\python\python.exe')`" -m metis.cli %*"
  )
  [IO.File]::WriteAllLines((Join-Path $bin "metis.cmd"), $cmd)
  return (Join-Path $bin "metis.cmd")
}

function Install-MetisServices([string]$Bundle, [string]$InstallRoot, [int]$ApiPort, [int]$ApiWorkers, [int]$WorkerSlots, [string]$EnvFile) {
  $svcDir = Join-Path $InstallRoot "services"
  New-Item -ItemType Directory -Force -Path $svcDir, (Join-Path $InstallRoot "data\logs\service") | Out-Null
  Write-MetisCmd $InstallRoot $EnvFile | Out-Null
  foreach ($name in @("metis-api", "metis-worker")) {
    $exe = Join-Path $svcDir "$name.exe"
    $xml = Join-Path $svcDir "$name.xml"
    if (Get-Service -Name $name -ErrorAction SilentlyContinue) {
      & $exe stop | Out-Null
      & $exe uninstall | Out-Null
      Start-Sleep -Seconds 2
    }
    Copy-Item -Force (Join-Path $Bundle "runtime\WinSW-x64.exe") $exe
    $template = Get-Content -Raw (Join-Path $Bundle "$name.xml")
    $content = $template.Replace("{{ROOT}}", $InstallRoot).Replace("{{PORT}}", "$ApiPort").Replace("{{WORKERS}}", "$ApiWorkers").Replace("{{SLOTS}}", "$WorkerSlots").Replace("{{ENV}}", $EnvFile)
    [IO.File]::WriteAllText($xml, $content, (New-Object Text.UTF8Encoding($false)))
    & $exe install
    if ($LASTEXITCODE -ne 0) { throw "$name servisi kurulamadı." }
    & $exe start
    if ($LASTEXITCODE -ne 0) { throw "$name servisi başlatılamadı; günlük: $InstallRoot\data\logs\service" }
    Write-Host "  $name kuruldu ve başlatıldı."
  }
}

function Stop-MetisServices([string]$InstallRoot) {
  # WinSW "stop" süreç kapanmadan döner; beklemeden devam edilirse sonraki "start" "zaten çalışıyor" deyip
  # hiçbir şey yapmaz ve süreç ardından kapanınca servis kapalı kalır. Durma tamamlanana kadar bekle.
  foreach ($name in @("metis-worker", "metis-api")) {
    $svc = Get-Service -Name $name -ErrorAction SilentlyContinue
    if ($svc) {
      if ($svc.Status -ne 'Stopped') {
        & (Join-Path $InstallRoot "services\$name.exe") stop | Out-Null
      }
      $svc.WaitForStatus('Stopped', [TimeSpan]::FromSeconds(90))
    }
  }
}

function Start-MetisServices([string]$InstallRoot) {
  foreach ($name in @("metis-api", "metis-worker")) {
    $svc = Get-Service -Name $name
    # Önceki bir durdurma hâlâ sürüyorsa önce onun bitmesini bekle.
    if ($svc.Status -eq 'StopPending') { $svc.WaitForStatus('Stopped', [TimeSpan]::FromSeconds(90)) }
    $svc.Refresh()
    if ($svc.Status -ne 'Running') {
      & (Join-Path $InstallRoot "services\$name.exe") start | Out-Null
    }
    $svc.WaitForStatus('Running', [TimeSpan]::FromSeconds(90))
  }
}

function Get-LocalUrl([string]$Url) {
  # Yerel (127.0.0.1) istekler vekil sunucuyu ASLA kullanmaz: şirket sunucularında sistem/ortam vekili
  # (HTTP_PROXY) tanımlıysa Invoke-WebRequest yerel adresi de vekile gönderebilir. PS 5.1 ve 7'de çalışır.
  Add-Type -AssemblyName System.Net.Http -ErrorAction SilentlyContinue
  $handler = New-Object System.Net.Http.HttpClientHandler
  $handler.UseProxy = $false
  $client = New-Object System.Net.Http.HttpClient($handler)
  $client.Timeout = [TimeSpan]::FromSeconds(5)
  try {
    $resp = $client.GetAsync($Url).GetAwaiter().GetResult()
    return @{ Status = [int]$resp.StatusCode; Body = $resp.Content.ReadAsStringAsync().GetAwaiter().GetResult() }
  } finally { $client.Dispose() }
}

function Wait-Healthy([int]$Port, [int]$Seconds) {
  Write-Step "Sağlık kontrolü bekleniyor (http://127.0.0.1:$Port/api/v1/health/ready)"
  $deadline = (Get-Date).AddSeconds($Seconds)
  while ((Get-Date) -lt $deadline) {
    try {
      $r = Get-LocalUrl "http://127.0.0.1:$Port/api/v1/health/ready"
      if ($r.Status -eq 200) { Write-Host "  hazır: $($r.Body)"; return }
    } catch { }
    Start-Sleep -Seconds 2
  }
  throw "METIS $Seconds saniyede hazır olmadı. Günlükler: data\logs ve data\logs\service"
}

function Register-MetisTasks([string]$InstallRoot, [string]$EnvFile) {
  Write-Step "Zamanlanmış görevler: gece yedeği ve haftalık geri yükleme tatbikatı"
  $cmd = Write-MetisCmd $InstallRoot $EnvFile
  $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
  $backup = New-ScheduledTaskAction -Execute $cmd -Argument "backup --keep-days 14"
  Register-ScheduledTask -TaskName "METIS gece yedeği" -Action $backup -Principal $principal -Force `
    -Trigger (New-ScheduledTaskTrigger -Daily -At "02:15") | Out-Null
  $rehearsal = New-ScheduledTaskAction -Execute $cmd -Argument "restore --rehearsal latest"
  Register-ScheduledTask -TaskName "METIS geri yükleme tatbikatı" -Action $rehearsal -Principal $principal -Force `
    -Trigger (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At "03:30") | Out-Null
  Write-Host "  'METIS gece yedeği' (02:15) ve 'METIS geri yükleme tatbikatı' (pazar 03:30) kaydedildi."
}

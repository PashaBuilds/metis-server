<#
.SYNOPSIS
  Aday ZIP'le kurulu METIS'i yükseltir: "METIS-Deneme-Yukseltme" zamanlanmış görevi bunu yönetici olarak çalıştırır.

.DESCRIPTION
  Yalnız geliştirme bilgisayarı içindir (kur.ps1 kurar, kaldir.ps1 kaldırır). Kullanıcı (ajan) istek\istek.json'a
  { "zip": "<yol>\METIS-x.y.z-server-win64.zip", "sha256": "<özet>" } yazar ve görevi başlatır; bu betik:
    - isteği okur ve siler (tek kullanımlık),
    - adı METIS-x.y.z-server-win64.zip değilse, ZIP'in yöneticiye ait kopyasının SHA-256'sı tutmazsa ya da METIS kurulu
      değilse (yalnız yükseltme; ilk kurulum PostgreSQL parolası ister) hiçbir şey açmadan reddeder,
    - kopyayı yöneticiye ait paket\ klasörüne açar ve başlatıcıyı otomasyon kipinde çalıştırır
      (baslat.ps1 -Onayla -TarayiciAcma: çift tıklamadaki soru ve UAC yerine; yükseltmenin kendisi aynıdır),
    - sonucu istek\sonuc.json'a yazar (kurulu sürüm ve /health/ready sürümü dahil). Günlük: istek\deneme.log.
  Çift tıklamadaki ileti kutusu ve UAC adımı bu yolda denenmez.
#>
[CmdletBinding()]
param(
  [string]$Base = "",
  [int]$ApiPort = 8000,
  [string]$InstallRoot = "C:\METIS"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
if (-not $Base) { $Base = Split-Path -Parent $MyInvocation.MyCommand.Path }
$RequestDir = Join-Path $Base "istek"
$Request = Join-Path $RequestDir "istek.json"
$ResultFile = Join-Path $RequestDir "sonuc.json"
$Work = Join-Path $Base "paket"
New-Item -ItemType Directory -Force -Path $RequestDir | Out-Null
try { Start-Transcript -Path (Join-Path $RequestDir "deneme.log") -Force | Out-Null } catch { }

$result = [ordered]@{ basarili = $false; baslangic = (Get-Date).ToString("s"); bitis = $null; zip = $null; surum = $null; hata = $null }

function Get-Sha256([string]$Path) {
  $s = [IO.File]::OpenRead($Path)
  try { return (([Security.Cryptography.SHA256]::Create().ComputeHash($s)) | ForEach-Object { $_.ToString("x2") }) -join "" } finally { $s.Dispose() }
}

function Get-ReadyVersion {
  try {
    $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 10 "http://127.0.0.1:$ApiPort/api/v1/health/ready"
    return ($r.Content | ConvertFrom-Json).version
  } catch { return $null }
}

try {
  if (-not (Test-Path $Request)) { throw "İstek yok: $Request" }
  $req = Get-Content -Raw -Encoding UTF8 $Request | ConvertFrom-Json
  Remove-Item -Force $Request
  $zip = [string]$req.zip
  $want = ([string]$req.sha256).ToLowerInvariant()
  $name = Split-Path -Leaf $zip
  $result.zip = $name
  $m = [regex]::Match($name, '^METIS-(\d+\.\d+\.\d+)-server-win64\.zip$')
  if (-not $m.Success) { throw "Beklenen ad METIS-x.y.z-server-win64.zip; gelen: $name" }
  $version = $m.Groups[1].Value
  $result.surum = $version
  if (-not (Test-Path -LiteralPath $zip -PathType Leaf)) { throw "ZIP yok: $zip" }
  if ($want -notmatch '^[0-9a-f]{64}$') { throw "SHA-256 geçersiz" }

  # Özet, kullanıcının değiştiremeyeceği kopyada hesaplanır (denetim ile açma arasında dosya değiştirilemesin).
  if (Test-Path $Work) { Remove-Item -Recurse -Force $Work }
  New-Item -ItemType Directory -Force -Path $Work | Out-Null
  $copy = Join-Path $Work $name
  Copy-Item -LiteralPath $zip -Destination $copy
  $got = Get-Sha256 $copy
  if ($got -ne $want) { Remove-Item -Force $copy; throw "SHA-256 tutmuyor: beklenen $want, gelen $got" }
  if (-not (Get-Service -Name "metis-api" -ErrorAction SilentlyContinue)) { Remove-Item -Force $copy; throw "METIS kurulu değil; bu görev yalnız yükseltme dener." }

  $dir = Join-Path $Work "METIS-$version"
  Expand-Archive -LiteralPath $copy -DestinationPath $dir -Force
  $starter = Join-Path $dir "METIS-$version-server-win64\baslat.ps1"
  if (-not (Test-Path $starter)) { throw "Pakette baslat.ps1 yok: $starter" }
  $inner = Join-Path $Work "baslat-sonuc.json"
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $starter -Onayla -TarayiciAcma -InstallRoot $InstallRoot -ApiPort $ApiPort -SonucDosyasi $inner | Out-Host
  $result.baslat_cikis = $LASTEXITCODE
  if (Test-Path $inner) { $result.baslat = Get-Content -Raw -Encoding UTF8 $inner | ConvertFrom-Json }
  $result.saglik_surumu = Get-ReadyVersion
  $result.basarili = ($result.baslat_cikis -eq 0 -and $result.saglik_surumu -eq $version)
  if (-not $result.basarili) { $result.hata = "Yükseltme doğrulanamadı (çıkış $($result.baslat_cikis), çalışan sürüm $($result.saglik_surumu))" }
} catch {
  $result.hata = $_.Exception.Message
}
$result.bitis = (Get-Date).ToString("s")
[IO.File]::WriteAllText($ResultFile, ($result | ConvertTo-Json -Depth 5), (New-Object Text.UTF8Encoding($false)))
try { Stop-Transcript | Out-Null } catch { }
if ($result.basarili) { exit 0 } else { exit 1 }

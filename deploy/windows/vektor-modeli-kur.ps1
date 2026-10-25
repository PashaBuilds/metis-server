<#
  METIS vektör arama modelini kurar (2.0.20'den beri). Yönetici PowerShell ile, model ZIP'inin açıldığı klasörde:

      powershell -ExecutionPolicy Bypass -File .\vektor-modeli-kur.ps1

  - Paket bütünlüğünü SHA256SUMS ile doğrular.
  - Modeli <METIS kökü>\models\multilingual-e5-base klasörüne kopyalar (varsayılan C:\METIS; METIS bu yolu kendiliğinden
    bulur, metis.env'e dokunmak gerekmez).
  - metis-api ve metis-worker servislerini yeniden başlatır. Worker yayımlanmış bölümlerin vektörlerini arka planda hesaplar;
    durum: Ayarlar → Sistem durumu → Vektör arama. Model kurulmasa da METIS yalnız kelime aramasıyla çalışır.
  - İnternet gerekmez. Kaldırmak için klasörü silip servisleri yeniden başlatmak yeter.
#>
param(
  [string]$MetisRoot = "C:\METIS"
)

$ErrorActionPreference = "Stop"

function Step([string]$m) { Write-Host "==> $m" -ForegroundColor Cyan }

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  throw "Yönetici PowerShell ile çalıştırın (sağ tık → Yönetici olarak çalıştır)."
}
if (-not (Test-Path (Join-Path $MetisRoot "app\current"))) { throw "METIS bulunamadı: $MetisRoot (önce METIS kurulmalı)." }

$here = $PSScriptRoot
$source = Join-Path $here "multilingual-e5-base"
if (-not (Test-Path (Join-Path $source "MODEL.json"))) { throw "Model klasörü bulunamadı: $source" }

Step "Paket bütünlüğü doğrulanıyor (SHA256SUMS)"
$sums = Join-Path $here "SHA256SUMS"
if (-not (Test-Path $sums)) { throw "SHA256SUMS yok." }
$n = 0
foreach ($line in Get-Content -LiteralPath $sums -Encoding UTF8) {
  if (-not $line.Trim()) { continue }
  $parts = $line -split "\s+", 2
  $file = Join-Path $here ($parts[1].Trim() -replace "/", "\")
  if (-not (Test-Path -LiteralPath $file)) { throw "Eksik dosya: $($parts[1])" }
  $actual = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($actual -ne $parts[0].ToLowerInvariant()) { throw "Özet tutmuyor: $($parts[1])" }
  $n++
}
Write-Host "  $n dosya doğrulandı."

Step "Model kopyalanıyor"
$models = Join-Path $MetisRoot "models"
$dest = Join-Path $models "multilingual-e5-base"
New-Item -ItemType Directory -Force $models | Out-Null
if (Test-Path $dest) { Remove-Item -LiteralPath $dest -Recurse -Force }
Copy-Item -LiteralPath $source -Destination $dest -Recurse
Write-Host "  $dest"

Step "Servisler yeniden başlatılıyor"
foreach ($svc in "metis-worker", "metis-api") {
  if (Get-Service $svc -ErrorAction SilentlyContinue) {
    Restart-Service $svc -Force
    Write-Host "  $svc yeniden başladı."
  }
}

Write-Host ""
Write-Host "Vektör arama modeli kuruldu. Worker bölümlerin vektörlerini arka planda hesaplar (büyük bilgi havuzunda" -ForegroundColor Green
Write-Host "dakikalar sürebilir). Durum: Ayarlar → Sistem durumu → Vektör arama." -ForegroundColor Green

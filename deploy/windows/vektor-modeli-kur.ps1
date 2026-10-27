<#
  METIS vektör arama modelini kurar (2.0.20'den beri; 2.0.25'ten beri hangi model paketi olursa). Yönetici PowerShell
  ile, model ZIP'inin açıldığı klasörde:

      powershell -ExecutionPolicy Bypass -File .\vektor-modeli-kur.ps1

  - Paket bütünlüğünü SHA256SUMS ile doğrular.
  - Paketteki model klasörünü (MODEL.json'u olan tek klasör) <METIS kökü>\models\vektor-modeli klasörüne kopyalar
    (varsayılan C:\METIS; METIS bu yolu kendiliğinden bulur, metis.env'e dokunmak gerekmez). Önceden kurulmuş bir model
    varsa yerine geçer.
  - METIS 2.0.25 ya da sonrasını ister; metis.env'de METIS_EMBEDDING_MODEL_DIR ayarlıysa uyarır.
  - metis-api ve metis-worker servislerini kopyalamadan önce durdurur, sonra başlatır. Worker yayımlanmış bölümlerin vektörlerini yeni modelle arka
    planda hesaplar (vektörü henüz olmayan bölüm o sırada yalnız kelime aramasıyla bulunur); durum: Ayarlar → Sistem
    durumu → Vektör arama. Model kurulmasa da METIS yalnız kelime aramasıyla çalışır.
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
$current = Join-Path $MetisRoot "app\current"
if (-not (Test-Path $current)) { throw "METIS bulunamadı: $MetisRoot (önce METIS kurulmalı)." }
# models\vektor-modeli klasörünü METIS 2.0.25'ten beri okur; daha eski sürüm bu modeli kullanmaz.
$target = (Get-Item -LiteralPath $current).Target | Select-Object -First 1
$installed = $null
if ($target -and [version]::TryParse((Split-Path $target -Leaf), [ref]$installed) -and $installed -lt [version]"2.0.25") {
  throw "Kurulu METIS $installed; bu model paketi METIS 2.0.25 ya da sonrasını gerektirir. Önce METIS'i yükseltin."
}
$envFile = Join-Path $MetisRoot "config\metis.env"
if ((Test-Path $envFile) -and (Select-String -LiteralPath $envFile -Pattern '^\s*METIS_EMBEDDING_MODEL_DIR\s*=\s*\S' -Quiet)) {
  Write-Warning "metis.env'de METIS_EMBEDDING_MODEL_DIR ayarlı; METIS o klasörü kullanır, bu kurulumu değil. Satırı silin ya da bu klasörü gösterin."
}

$here = $PSScriptRoot
$found = @(Get-ChildItem -LiteralPath $here -Directory | Where-Object { Test-Path (Join-Path $_.FullName "MODEL.json") })
if ($found.Count -ne 1) { throw "Paket klasöründe MODEL.json'u olan tek bir model klasörü bekleniyordu ($($found.Count) bulundu)." }
$source = $found[0].FullName

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

$services = @("metis-worker", "metis-api") | Where-Object { Get-Service $_ -ErrorAction SilentlyContinue }
Step "Servisler durduruluyor (model dosyaları açıkken değiştirilmez)"
foreach ($svc in $services) {
  Stop-Service $svc -Force
  Write-Host "  $svc durdu."
}

try {
  Step "Model kopyalanıyor ($($found[0].Name))"
  $models = Join-Path $MetisRoot "models"
  $dest = Join-Path $models "vektor-modeli"
  New-Item -ItemType Directory -Force $models | Out-Null
  if (Test-Path $dest) { Remove-Item -LiteralPath $dest -Recurse -Force }
  Copy-Item -LiteralPath $source -Destination $dest -Recurse
  Write-Host "  $dest"
  $old = Join-Path $models "multilingual-e5-base"
  if (Test-Path $old) {
    Write-Host "  Önceki e5-base kurulumu ($old) artık kullanılmaz; yer açmak için silinebilir."
  }
} finally {
  Step "Servisler başlatılıyor"
  foreach ($svc in @("metis-api", "metis-worker")) {
    if ($services -contains $svc) {
      Start-Service $svc
      Write-Host "  $svc başladı."
    }
  }
}

Write-Host ""
Write-Host "Vektör arama modeli kuruldu. Worker bölümlerin vektörlerini arka planda hesaplar (büyük bilgi havuzunda" -ForegroundColor Green
Write-Host "dakikalar ya da saatler sürebilir; vektörü henüz hesaplanmamış bölümler o sırada yalnız kelime aramasıyla" -ForegroundColor Green
Write-Host "bulunur). Durum: Ayarlar → Sistem durumu → Vektör arama." -ForegroundColor Green

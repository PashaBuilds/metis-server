<#
.SYNOPSIS
  kur.ps1'in kurduğu "METIS-Deneme-Yukseltme" görevini ve C:\ProgramData\METIS-Deneme klasörünü kaldırır (yönetici).
  Kurulu METIS'e dokunmaz.
#>
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$id = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  throw "Yönetici PowerShell'de çalıştır."
}
$TaskName = "METIS-Deneme-Yukseltme"
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) { Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false }
$Base = Join-Path $env:ProgramData "METIS-Deneme"
if (Test-Path $Base) { Remove-Item -Recurse -Force $Base }
Write-Host "Kaldırıldı: $TaskName ve $Base" -ForegroundColor Green

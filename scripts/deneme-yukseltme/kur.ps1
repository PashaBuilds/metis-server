<#
.SYNOPSIS
  Geliştirme bilgisayarında ajanın aday ZIP'le yükseltmeyi UAC sorusu olmadan denemesi için zamanlanmış görev kurar.

.DESCRIPTION
  Bir kez, yönetici PowerShell'de çalıştırılır:
    powershell -ExecutionPolicy Bypass -File scripts\deneme-yukseltme\kur.ps1
  Kurulan:
    - C:\ProgramData\METIS-Deneme\calistir.ps1: yalnız Administrators/SYSTEM yazabilir (görevin ne çalıştırdığı
      kullanıcı tarafından değiştirilemez);
    - C:\ProgramData\METIS-Deneme\istek\: kullanıcı istek yazar, sonucu okur;
    - "METIS-Deneme-Yukseltme" görevi: kullanıcının oturumunda, en yüksek yetkiyle, yalnız elle başlatılınca çalışır
      (tetikleyici yok); kullanıcı başlatabilir (schtasks /run), değiştiremez.
  Bilinçli ödün: bu kullanıcı hesabıyla çalışan herhangi bir süreç, METIS-x.y.z-server-win64.zip adlı bir ZIP'i (kurulu
  METIS varken) yönetici olarak açtırabilir. Yalnız geliştirme/deneme bilgisayarında kurun; sunucuda kurmayın.
  Kaldırmak için: scripts\deneme-yukseltme\kaldir.ps1 (yönetici).
#>
[CmdletBinding()]
param(
  [string]$Kullanici = "$env:USERDOMAIN\$env:USERNAME"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$id = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  throw "Yönetici PowerShell'de çalıştır (Başlat → PowerShell → sağ tık → Yönetici olarak çalıştır)."
}
$TaskName = "METIS-Deneme-Yukseltme"
$Base = Join-Path $env:ProgramData "METIS-Deneme"
$sid = (New-Object Security.Principal.NTAccount($Kullanici)).Translate([Security.Principal.SecurityIdentifier]).Value

# Klasör: kalıtım yok; Administrators + SYSTEM tam, kullanıcı yalnız okur. istek\: kullanıcı değiştirebilir.
New-Item -ItemType Directory -Force -Path (Join-Path $Base "istek") | Out-Null
$acl = New-Object Security.AccessControl.DirectorySecurity
$acl.SetAccessRuleProtection($true, $false)
$inherit = [Security.AccessControl.InheritanceFlags]"ContainerInherit, ObjectInherit"
$none = [Security.AccessControl.PropagationFlags]::None
foreach ($who in @("S-1-5-32-544", "S-1-5-18")) {
  $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule((New-Object Security.Principal.SecurityIdentifier($who)), "FullControl", $inherit, $none, "Allow")))
}
$acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule((New-Object Security.Principal.SecurityIdentifier($sid)), "ReadAndExecute", $inherit, $none, "Allow")))
Set-Acl -Path $Base -AclObject $acl
$req = Get-Acl (Join-Path $Base "istek")
$req.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule((New-Object Security.Principal.SecurityIdentifier($sid)), "Modify", $inherit, $none, "Allow")))
Set-Acl -Path (Join-Path $Base "istek") -AclObject $req

# Çalıştırıcı BOM'lu kopyalanır (Windows PowerShell 5.1 BOM'suz UTF-8'i ANSI okur).
$src = [IO.File]::ReadAllText((Join-Path $PSScriptRoot "calistir.ps1"), [Text.Encoding]::UTF8)
[IO.File]::WriteAllText((Join-Path $Base "calistir.ps1"), $src, (New-Object Text.UTF8Encoding($true)))

# Görev: oturum açıkken, en yüksek yetkiyle; kullanıcı okuyup başlatabilir (GRGX), yalnız yönetici değiştirir.
$svc = New-Object -ComObject "Schedule.Service"
$svc.Connect()
$def = $svc.NewTask(0)
$def.RegistrationInfo.Description = "METIS aday ZIP'iyle yükseltme denemesi (geliştirme bilgisayarı; scripts\deneme-yukseltme)."
$def.Principal.UserId = $Kullanici
$def.Principal.LogonType = 3   # TASK_LOGON_INTERACTIVE_TOKEN: parola saklanmaz, oturum açıkken çalışır
$def.Principal.RunLevel = 1    # TASK_RUNLEVEL_HIGHEST
$def.Settings.MultipleInstances = 2  # TASK_INSTANCES_IGNORE_NEW
$def.Settings.ExecutionTimeLimit = "PT1H"
$def.Settings.DisallowStartIfOnBatteries = $false
$def.Settings.StopIfGoingOnBatteries = $false
$action = $def.Actions.Create(0)
$action.Path = "powershell.exe"
$action.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$(Join-Path $Base 'calistir.ps1')`""
$sddl = "D:P(A;;FA;;;BA)(A;;FA;;;SY)(A;;GRGX;;;$sid)"
$svc.GetFolder("\").RegisterTaskDefinition($TaskName, $def, 6, $Kullanici, $null, 3, $sddl) | Out-Null

Write-Host "Kuruldu: '$TaskName' ($Kullanici, en yüksek yetki, yalnız elle başlatılır), $Base" -ForegroundColor Green
Write-Host "Ajan artık: scripts\release.ps1 -Dene (aday ZIP'le kurulu METIS'i yükseltir ve doğrular)."

& {
# MOLEKA PDV - OTIMIZAÇÃO SEGURA E REVERSÍVEL + COLETA COMPLEMENTAR (10/11/2026)
# Cole inteiro no PowerShell COMO ADMINISTRADOR. Antes de mudar qualquer coisa: salva o estado atual,
# cria um ponto de restauração e grava DESFAZER_otimizacao.ps1 na pasta Moleka-Diagnostico da Área de Trabalho.
$ErrorActionPreference = 'Continue'
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if(-not $admin){ Write-Host 'ABRA O POWERSHELL COMO ADMINISTRADOR E COLE DE NOVO. Nada foi alterado.' -ForegroundColor Red; return }
$inicio = Get-Date
$pasta = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Moleka-Diagnostico'
New-Item -ItemType Directory -Force -Path $pasta | Out-Null
$carimbo = Get-Date -Format 'yyyy-MM-dd_HHmm'
$S = New-Object System.Collections.Generic.List[string]
$ctx = @{ n = 0; etapas = 17 }
$atv = 'Moleka PDV - otimização do PC'
function Passo($t){ $ctx.n++; Write-Progress -Activity $atv -Status "$($ctx.n)/$($ctx.etapas) - $t" -PercentComplete ([int](100 * $ctx.n / $ctx.etapas)) }
function Fim(){ Write-Progress -Activity $atv -Completed }
function Ok($t){ $S.Add("OK      $t") }
function Falhou($t){ $S.Add("FALHOU  $t") }
function Info($t){ $S.Add("INFO    $t") }
function Corta($t, $n){ $t = [string]$t; if($t.Length -gt $n){ $t.Substring(0, $n) + '...' } else { $t } }
function LerValor($k, $n){ try { (Get-ItemProperty -Path $k -Name $n -ErrorAction Stop).$n } catch { $null } }
function GarantirChave($k){ $partes = $k -split '\\'; $atual = $partes[0]; for($i = 1; $i -lt $partes.Count; $i++){ $atual = $atual + '\' + $partes[$i]; if(-not (Test-Path $atual)){ New-Item -Path $atual -ErrorAction Stop | Out-Null } } }
$guidMol = '6d6f6c65-6b61-5044-5600-000000000001'
$guidHP = '8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c'
$guidEq = '381b4222-f694-41f0-9685-ff5bb260df2e'
$subUSB = '2a737441-1930-4402-8d77-b2bebba308a3'
$setUSB = '48e6b7a6-50f5-4782-a5d4-53bb8f07e226'
$kPower = 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power'
$kEdge = 'HKLM:\SOFTWARE\Policies\Microsoft\Edge'
$kChrome = 'HKLM:\SOFTWARE\Policies\Google\Chrome'
$kAdv = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced'
$kPers = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize'
$kVfx = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects'
$desde7 = (Get-Date).AddDays(-7)
$desde14 = (Get-Date).AddDays(-14)
$codigoSPI = @'
using System;
using System.Runtime.InteropServices;
public static class MolekaSPI {
    [StructLayout(LayoutKind.Sequential)]
    public struct ANIMATIONINFO { public uint cbSize; public int iMinAnimate; }
    [DllImport("user32.dll", EntryPoint = "SystemParametersInfoW", SetLastError = true)]
    public static extern bool SystemParametersInfo(uint uiAction, uint uiParam, IntPtr pvParam, uint fWinIni);
    [DllImport("user32.dll", EntryPoint = "SystemParametersInfoW", SetLastError = true)]
    public static extern bool SystemParametersInfo(uint uiAction, uint uiParam, ref ANIMATIONINFO pvParam, uint fWinIni);
}
'@

# ---------------------------------------------------------------- 1. estado atual (para o desfazer)
Passo 'Registrando o estado atual (para poder desfazer)'
$jsonAntigo = Get-ChildItem -Path $pasta -Filter 'estado_antes_*.json' -ErrorAction SilentlyContinue | Sort-Object Name | Select-Object -First 1
if($jsonAntigo){
  $antes = Get-Content -Path $jsonAntigo.FullName -Raw | ConvertFrom-Json
  Info "estado original já tinha sido salvo ($($jsonAntigo.Name)); o desfazer volta para ele"
} else {
  try {
    $m = [regex]::Match(((powercfg /getactivescheme) -join ' '), '[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}')
    $planoAtual = $guidEq
    if($m.Success -and $m.Value -ne $guidMol){ $planoAtual = $m.Value }
    $mp0 = Get-MpPreference -ErrorAction SilentlyContinue
    $ws0 = Get-CimInstance Win32_Service -Filter "Name='WSearch'" -ErrorAction SilentlyContinue
    $antes = [pscustomobject][ordered]@{
      Plano = $planoAtual
      Hiberboot = LerValor $kPower 'HiberbootEnabled'
      WSearchModo = [string]$ws0.StartMode
      WSearchAtraso = LerValor 'HKLM:\SYSTEM\CurrentControlSet\Services\WSearch' 'DelayedAutostart'
      EdgeBoost = LerValor $kEdge 'StartupBoostEnabled'
      EdgeFundo = LerValor $kEdge 'BackgroundModeEnabled'
      ChromeFundo = LerValor $kChrome 'BackgroundModeEnabled'
      TaskbarAnim = LerValor $kAdv 'TaskbarAnimations'
      Transparencia = LerValor $kPers 'EnableTransparency'
      VisualFX = LerValor $kVfx 'VisualFXSetting'
      DefenderCPU = $mp0.ScanAvgCPULoadFactor
      DefenderBaixa = $mp0.EnableLowCpuPriority
    }
    $antes | ConvertTo-Json | Out-File -FilePath (Join-Path $pasta "estado_antes_$carimbo.json") -Encoding UTF8
    Ok "estado atual salvo (estado_antes_$carimbo.json)"
  } catch {
    Falhou "não consegui registrar o estado atual: $($_.Exception.Message). NADA FOI ALTERADO."
    Fim; $S; return
  }
}

# ---------------------------------------------------------------- 2. ponto de restauração
Passo 'Ponto de restauração do Windows (pode levar alguns minutos)'
try {
  Enable-ComputerRestore -Drive "$($env:SystemDrive)\" -ErrorAction Stop
  $kSR = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\SystemRestore'
  $freq = LerValor $kSR 'SystemRestorePointCreationFrequency'
  Set-ItemProperty -Path $kSR -Name 'SystemRestorePointCreationFrequency' -Value 0 -Type DWord -ErrorAction Stop
  Checkpoint-Computer -Description 'Antes da otimizacao Moleka PDV' -RestorePointType 'MODIFY_SETTINGS' -ErrorAction Stop
  if($null -eq $freq){ Remove-ItemProperty -Path $kSR -Name 'SystemRestorePointCreationFrequency' -ErrorAction SilentlyContinue } else { Set-ItemProperty -Path $kSR -Name 'SystemRestorePointCreationFrequency' -Value $freq -Type DWord }
  $rp = Get-ComputerRestorePoint -ErrorAction SilentlyContinue | Sort-Object SequenceNumber -Descending | Select-Object -First 1
  if($rp -and $rp.Description -eq 'Antes da otimizacao Moleka PDV'){ Ok "ponto de restauração nº $($rp.SequenceNumber) criado" } else { Falhou 'ponto de restauração não confirmado (o DESFAZER continua valendo)' }
} catch { Falhou "ponto de restauração: $($_.Exception.Message) (o DESFAZER continua valendo)" }

# ---------------------------------------------------------------- 3. script de desfazer
Passo 'Gravando o script de desfazer'
try {
  $scWS = switch([string]$antes.WSearchModo){ 'Auto' { if($antes.WSearchAtraso -eq 1){ 'delayed-auto' } else { 'auto' } } 'Manual' { 'demand' } 'Disabled' { 'disabled' } default { 'delayed-auto' } }
  function LinhaReg($k, $n, $v){ if($null -eq $v){ "Remove-ItemProperty -Path '$k' -Name '$n' -ErrorAction SilentlyContinue" } else { "Set-ItemProperty -Path '$k' -Name '$n' -Value $v -Type DWord" } }
  $hbVal = 1
  if($null -ne $antes.Hiberboot){ $hbVal = $antes.Hiberboot }
  $linhaDef = ''
  if($null -ne $antes.DefenderCPU){
    $baixa = '$false'
    if($antes.DefenderBaixa -eq $true){ $baixa = '$true' }
    $linhaDef = "Set-MpPreference -ScanAvgCPULoadFactor $($antes.DefenderCPU) -EnableLowCpuPriority $baixa"
  }
  $linhaWS = ''
  if($scWS -ne 'disabled'){ $linhaWS = 'Start-Service WSearch' }
  $lEdge1 = LinhaReg $kEdge 'StartupBoostEnabled' $antes.EdgeBoost
  $lEdge2 = LinhaReg $kEdge 'BackgroundModeEnabled' $antes.EdgeFundo
  $lChrome = LinhaReg $kChrome 'BackgroundModeEnabled' $antes.ChromeFundo
  $lTask = LinhaReg $kAdv 'TaskbarAnimations' $antes.TaskbarAnim
  $lTransp = LinhaReg $kPers 'EnableTransparency' $antes.Transparencia
  $lVfx = LinhaReg $kVfx 'VisualFXSetting' $antes.VisualFX
  $desfazer = @"
& {
# DESFAZ a otimização Moleka PDV de $carimbo (volta às configurações anteriores). Cole inteiro no PowerShell COMO ADMINISTRADOR.
`$ErrorActionPreference = 'SilentlyContinue'
`$at = 'Desfazendo a otimização Moleka PDV'
Write-Progress -Activity `$at -Status '1/5 Plano de energia' -PercentComplete 10
powercfg /setactive $($antes.Plano) | Out-Null
powercfg /delete $guidMol | Out-Null
Write-Progress -Activity `$at -Status '2/5 Inicialização rápida' -PercentComplete 30
Set-ItemProperty -Path '$kPower' -Name HiberbootEnabled -Value $hbVal -Type DWord
Write-Progress -Activity `$at -Status '3/5 Windows Search' -PercentComplete 50
sc.exe config WSearch start= $scWS | Out-Null
$linhaWS
Write-Progress -Activity `$at -Status '4/5 Navegadores e antivírus' -PercentComplete 70
$lEdge1
$lEdge2
$lChrome
$linhaDef
Write-Progress -Activity `$at -Status '5/5 Efeitos visuais' -PercentComplete 90
if(-not ('MolekaSPI' -as [type])){ Add-Type -TypeDefinition @'
$codigoSPI
'@ }
foreach(`$a in 0x1003, 0x1005, 0x1007, 0x1013, 0x1015, 0x1017, 0x101B, 0x1025, 0x1043){ [void][MolekaSPI]::SystemParametersInfo([uint32]`$a, 0, [IntPtr]1, 3) }
`$ai = New-Object 'MolekaSPI+ANIMATIONINFO'; `$ai.cbSize = 8; `$ai.iMinAnimate = 1; [void][MolekaSPI]::SystemParametersInfo(0x0049, 8, [ref]`$ai, 3)
$lTask
$lTransp
$lVfx
Write-Progress -Activity `$at -Completed
'PRONTO: configurações anteriores restauradas. Reinicie o PC.'
}
"@
  $arqDesfazer = Join-Path $pasta 'DESFAZER_otimizacao.ps1'
  $desfazer | Out-File -FilePath $arqDesfazer -Encoding UTF8
  if(-not (Test-Path $arqDesfazer)){ throw 'o arquivo não foi criado' }
  Ok "script de desfazer gravado: $arqDesfazer"
} catch {
  Falhou "script de desfazer: $($_.Exception.Message). NADA FOI ALTERADO."
  Fim; $S; return
}

# ---------------------------------------------------------------- 4. plano de energia do caixa
Passo 'Plano de energia do caixa'
try {
  $base = 'já existia'
  if(-not (((powercfg /list) -join ' ') -match $guidMol)){
    powercfg -duplicatescheme $guidHP $guidMol | Out-Null
    $base = 'Alto desempenho'
    if($LASTEXITCODE -ne 0){ powercfg -duplicatescheme $guidEq $guidMol | Out-Null; $base = 'Equilibrado' }
    if($LASTEXITCODE -ne 0){ throw 'não consegui criar o plano de energia' }
    powercfg -changename $guidMol 'Moleka PDV (caixa)' 'Sem suspensao na tomada, disco sempre ligado, USB sem economia de energia' | Out-Null
  }
  powercfg /setactive $guidMol | Out-Null
  foreach($c in 'standby-timeout-ac 0', 'hibernate-timeout-ac 0', 'disk-timeout-ac 0', 'monitor-timeout-ac 15', 'standby-timeout-dc 30', 'disk-timeout-dc 0', 'monitor-timeout-dc 5'){
    $p = $c.Split(' '); powercfg /change $p[0] $p[1] | Out-Null
  }
  powercfg /setacvalueindex $guidMol $subUSB $setUSB 0 | Out-Null
  powercfg /setdcvalueindex $guidMol $subUSB $setUSB 0 | Out-Null
  powercfg /setactive $guidMol | Out-Null
  $ativo = (powercfg /getactivescheme) -join ' '
  $q = [regex]::Matches(((powercfg /query $guidMol $subUSB $setUSB) -join ' '), '0x[0-9a-fA-F]{8}')
  $usbTxt = 'economia do USB: não confirmada'
  if($q.Count -ge 2){ $usbTxt = "economia de energia do USB: tomada=$([Convert]::ToInt32($q[$q.Count - 2].Value, 16)) bateria=$([Convert]::ToInt32($q[$q.Count - 1].Value, 16)) (0 = desligada)" }
  if($ativo -match $guidMol){ Ok "plano 'Moleka PDV (caixa)' ativo (base: $base): na tomada nunca suspende, disco sempre ligado, tela apaga em 15 min | $usbTxt" } else { Falhou "plano de energia não ficou ativo: $ativo" }
} catch { Falhou "plano de energia: $($_.Exception.Message)" }

# ---------------------------------------------------------------- 5. inicialização rápida
Passo 'Inicialização rápida (passar a desligar de verdade)'
try {
  Set-ItemProperty -Path $kPower -Name 'HiberbootEnabled' -Value 0 -Type DWord -ErrorAction Stop
  if((LerValor $kPower 'HiberbootEnabled') -eq 0){ Ok 'inicialização rápida desligada: o PC passa a desligar de verdade (liga um pouco mais devagar, mas começa o dia limpo)' } else { Falhou 'inicialização rápida: valor não confirmado' }
} catch { Falhou "inicialização rápida: $($_.Exception.Message)" }

# ---------------------------------------------------------------- 6. indexação (Windows Search)
Passo 'Indexação de arquivos (Windows Search)'
try {
  Stop-Service -Name 'WSearch' -Force -ErrorAction Stop
  Set-Service -Name 'WSearch' -StartupType Disabled -ErrorAction Stop
  $w = Get-CimInstance Win32_Service -Filter "Name='WSearch'"
  if($w.StartMode -eq 'Disabled' -and $w.State -eq 'Stopped'){ Ok 'indexação do Windows Search desligada (procurar programas no Iniciar continua funcionando; procurar arquivos fica mais lento)' } else { Falhou "Windows Search ficou $($w.State)/$($w.StartMode)" }
} catch { Falhou "Windows Search: $($_.Exception.Message)" }

# ---------------------------------------------------------------- 7. navegadores rodando escondidos
Passo 'Navegadores sem rodar escondidos'
try {
  GarantirChave $kEdge
  Set-ItemProperty -Path $kEdge -Name 'StartupBoostEnabled' -Value 0 -Type DWord -ErrorAction Stop
  Set-ItemProperty -Path $kEdge -Name 'BackgroundModeEnabled' -Value 0 -Type DWord -ErrorAction Stop
  $txt = 'Edge sem pré-carregamento e sem continuar rodando depois de fechado'
  $temChrome = (Test-Path "$env:ProgramFiles\Google\Chrome\Application\chrome.exe") -or (Test-Path "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe") -or (Test-Path "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe")
  if($temChrome){
    GarantirChave $kChrome
    Set-ItemProperty -Path $kChrome -Name 'BackgroundModeEnabled' -Value 0 -Type DWord -ErrorAction Stop
    $txt = $txt + '; Chrome sem continuar rodando depois de fechado'
  }
  Ok "$txt (vale a partir da próxima vez que o navegador abrir)"
} catch { Falhou "navegadores: $($_.Exception.Message)" }

# ---------------------------------------------------------------- 8. antivírus: varredura agendada mais leve
Passo 'Antivírus: varredura agendada em prioridade baixa'
try {
  Set-MpPreference -EnableLowCpuPriority $true -ScanAvgCPULoadFactor 30 -ErrorAction Stop
  $mp1 = Get-MpPreference
  Ok "Defender: varredura agendada em prioridade baixa=$($mp1.EnableLowCpuPriority), limite médio de CPU $($mp1.ScanAvgCPULoadFactor)% (a proteção em tempo real não mudou)"
} catch { Falhou "Defender: $($_.Exception.Message)" }

# ---------------------------------------------------------------- 9. efeitos visuais
Passo 'Efeitos visuais (mantém fontes suaves e miniaturas)'
try {
  if(-not ('MolekaSPI' -as [type])){ Add-Type -TypeDefinition $codigoSPI -ErrorAction Stop }
  foreach($a in 0x1003, 0x1005, 0x1007, 0x1013, 0x1015, 0x1017, 0x101B, 0x1025, 0x1043){ [void][MolekaSPI]::SystemParametersInfo([uint32]$a, 0, [IntPtr]::Zero, 3) }
  $ai = New-Object 'MolekaSPI+ANIMATIONINFO'; $ai.cbSize = 8; $ai.iMinAnimate = 0
  [void][MolekaSPI]::SystemParametersInfo(0x0049, 8, [ref]$ai, 3)
  Set-ItemProperty -Path $kAdv -Name 'TaskbarAnimations' -Value 0 -Type DWord -ErrorAction Stop
  Set-ItemProperty -Path $kPers -Name 'EnableTransparency' -Value 0 -Type DWord -ErrorAction Stop
  GarantirChave $kVfx
  Set-ItemProperty -Path $kVfx -Name 'VisualFXSetting' -Value 3 -Type DWord -ErrorAction Stop
  $ai2 = New-Object 'MolekaSPI+ANIMATIONINFO'; $ai2.cbSize = 8
  [void][MolekaSPI]::SystemParametersInfo(0x0048, 8, [ref]$ai2, 0)
  Ok "efeitos visuais enxutos: sem animação de janelas, menus e sombras, sem transparência; fontes suaves e miniaturas mantidas (animação de janela agora: $($ai2.iMinAnimate); 0 = desligada)"
} catch { Falhou "efeitos visuais: $($_.Exception.Message)" }

# ================================================================ COLETA COMPLEMENTAR (só leitura)
# ---------------------------------------------------------------- 10. programas na inicialização
Passo 'Programas que abrem com o Windows'
try {
  $aprov = @{}
  foreach($k in 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run', 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run32', 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\StartupFolder', 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run', 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run32', 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\StartupFolder'){
    $reg = Get-ItemProperty -Path $k -ErrorAction SilentlyContinue
    if($reg){ foreach($p in $reg.PSObject.Properties){ if($p.Name -notlike 'PS*' -and $p.Value -is [byte[]] -and $p.Value.Length -gt 0){ $aprov[$p.Name] = [int]$p.Value[0] } } }
  }
  $itens = @(foreach($s in @(Get-CimInstance Win32_StartupCommand -ErrorAction SilentlyContinue)){
    $b = $aprov[[string]$s.Name]
    if($null -eq $b){ $b = $aprov[([string]$s.Name) + '.lnk'] }
    $est = 'LIGADO'
    if($null -ne $b -and ($b % 2) -eq 1){ $est = 'desligado' }
    $cmd = Corta (([string]$s.Command).Replace('"', '')) 60
    "$($s.Name) [$est] ($cmd)"
  })
  Info "INICIALIZAÇÃO ($($itens.Count)): $($itens -join ' || ')"
} catch { Falhou "inicialização: $($_.Exception.Message)" }

# ---------------------------------------------------------------- 11. memória e bateria
Passo 'Memória (pentes e encaixes) e bateria'
try {
  $arrs = @(Get-CimInstance Win32_PhysicalMemoryArray -ErrorAction SilentlyContinue)
  $arr = $arrs | Where-Object { $_.Use -eq 3 } | Select-Object -First 1
  if(-not $arr){ $arr = $arrs | Select-Object -First 1 }
  $maxKB = $arr.MaxCapacity
  if($arr.MaxCapacityEx -gt 0){ $maxKB = $arr.MaxCapacityEx }
  $pentes = @(Get-CimInstance Win32_PhysicalMemory -ErrorAction SilentlyContinue | ForEach-Object { $pn = ([string]$_.PartNumber).Trim(); "$($_.DeviceLocator)/$($_.BankLabel) $([math]::Round($_.Capacity / 1GB))GB $($_.Speed)MHz $($_.Manufacturer) $pn formato=$($_.FormFactor)" })
  Info "MEMÓRIA: encaixes informados pelo BIOS=$($arr.MemoryDevices) | máximo informado=$([math]::Round($maxKB / 1MB)) GB | instalado: $($pentes -join ' + ')"
} catch { Falhou "memória: $($_.Exception.Message)" }
try {
  $bs = Get-CimInstance -Namespace 'root\wmi' -ClassName BatteryStaticData -ErrorAction SilentlyContinue | Select-Object -First 1
  $bf = Get-CimInstance -Namespace 'root\wmi' -ClassName BatteryFullChargedCapacity -ErrorAction SilentlyContinue | Select-Object -First 1
  $bt = Get-CimInstance -Namespace 'root\wmi' -ClassName BatteryStatus -ErrorAction SilentlyContinue | Select-Object -First 1
  $wb = Get-CimInstance Win32_Battery -ErrorAction SilentlyContinue | Select-Object -First 1
  if($bs -and $bf -and $bs.DesignedCapacity -gt 0){
    $saude = [math]::Round(100 * $bf.FullChargedCapacity / $bs.DesignedCapacity)
    Info "BATERIA: capacidade original $($bs.DesignedCapacity) mWh | capacidade hoje $($bf.FullChargedCapacity) mWh | saúde $saude% | carga agora $($wb.EstimatedChargeRemaining)% | na tomada=$($bt.PowerOnline) | carregando=$($bt.Charging)"
  } elseif($wb){ Info "BATERIA: detectada, carga $($wb.EstimatedChargeRemaining)% (capacidade não informada)" } else { Info 'BATERIA: nenhuma bateria detectada' }
  powercfg /batteryreport /output (Join-Path $pasta "bateria_$carimbo.html") | Out-Null
} catch { Falhou "bateria: $($_.Exception.Message)" }

# ---------------------------------------------------------------- 12. desligamentos inesperados
Passo 'Desligamentos inesperados (14 dias)'
try {
  $ev41 = @(Get-WinEvent -FilterHashtable @{ LogName = 'System'; Id = 41; StartTime = $desde14 } -MaxEvents 30 -ErrorAction SilentlyContinue | Where-Object { $_.ProviderName -eq 'Microsoft-Windows-Kernel-Power' })
  $lin41 = @(foreach($e in $ev41){
    $d = @{}
    foreach($n in ([xml]$e.ToXml()).Event.EventData.Data){ $d[[string]$n.Name] = [string]$n.'#text' }
    $bug = 0L; [void][int64]::TryParse([string]$d['BugcheckCode'], [ref]$bug)
    $btn = 0L; [void][int64]::TryParse([string]$d['PowerButtonTimestamp'], [ref]$btn)
    $tipo = 'falta de energia ou travou'
    if($btn -ne 0){ $tipo = 'botão de ligar segurado' }
    if($bug -ne 0){ $tipo = 'tela azul (erro 0x{0:X})' -f $bug }
    "$($e.TimeCreated.ToString('dd/MM HH:mm')) $tipo"
  })
  $ev6008 = @(Get-WinEvent -FilterHashtable @{ LogName = 'System'; Id = 6008; StartTime = $desde14 } -MaxEvents 30 -ErrorAction SilentlyContinue | ForEach-Object { ("$($_.Properties[1].Value) $($_.Properties[0].Value)" -replace '[^\d/: ]', '').Trim() })
  $normais = @(Get-WinEvent -FilterHashtable @{ LogName = 'System'; Id = 6006; StartTime = $desde14 } -MaxEvents 60 -ErrorAction SilentlyContinue).Count
  $boots = @(Get-WinEvent -FilterHashtable @{ LogName = 'System'; ProviderName = 'Microsoft-Windows-Kernel-Boot'; Id = 27; StartTime = $desde14 } -MaxEvents 60 -ErrorAction SilentlyContinue | ForEach-Object {
    $vb = ([string](([xml]$_.ToXml()).Event.EventData.Data | Where-Object { $_.Name -eq 'BootType' } | Select-Object -First 1).'#text') -replace '^0x', ''
    $tp = switch($vb){ '0' { 'completo' } '1' { 'rápido' } '2' { 'volta da hibernação' } default { "tipo $vb" } }
    "$($_.TimeCreated.ToString('dd/MM HH:mm')) $tp"
  })
  Info "DESLIGAMENTOS SEM FECHAR O WINDOWS (14 dias): $($ev41.Count) | ao religar: $($lin41 -join '; ')"
  Info "HORA EM QUE CAIU (último registro antes da queda): $($ev6008 -join '; ')"
  Info "DESLIGAMENTOS NORMAIS (14 dias): $normais | PARTIDAS DO WINDOWS ($($boots.Count)): $($boots -join ', ')"
} catch { Falhou "desligamentos: $($_.Exception.Message)" }

# ---------------------------------------------------------------- 13. disco
Passo 'Disco: saúde e eventos'
try {
  $fp = Get-CimInstance -Namespace 'root\wmi' -ClassName MSStorageDriver_FailurePredictStatus -ErrorAction SilentlyContinue | Select-Object -First 1
  $rc = Get-PhysicalDisk -ErrorAction SilentlyContinue | Get-StorageReliabilityCounter -ErrorAction SilentlyContinue | Select-Object -First 1
  $prev = '—'
  if($fp){ $prev = [string]$fp.PredictFailure }
  Info "DISCO (SMART): o próprio disco prevê falha=$prev | temperatura $($rc.Temperature) C | horas ligado $($rc.PowerOnHours) | erros de leitura $($rc.ReadErrorsTotal) (sem correção $($rc.ReadErrorsUncorrected)) | erros de escrita $($rc.WriteErrorsTotal)"
  $provDisco = 'disk', 'Ntfs', 'Microsoft-Windows-Ntfs', 'storahci', 'volmgr', 'partmgr', 'iaStorA', 'iaStorAC', 'iaStorAVC', 'Microsoft-Windows-StorPort'
  $evD = @(Get-WinEvent -FilterHashtable @{ LogName = 'System'; Level = 1, 2, 3; StartTime = $desde14 } -MaxEvents 3000 -ErrorAction SilentlyContinue | Where-Object { $provDisco -contains $_.ProviderName })
  $gD = @($evD | Group-Object { "$($_.ProviderName) id $($_.Id)" } | Sort-Object Count -Descending | ForEach-Object {
    $u = $_.Group[0]
    $msg = Corta (([string]$u.Message) -replace '\s+', ' ') 100
    "$($_.Name) x$($_.Count) (último $($u.TimeCreated.ToString('dd/MM HH:mm'))): $msg"
  })
  $txtD = 'nenhum'
  if($gD.Count){ $txtD = $gD -join ' || ' }
  Info "EVENTOS DE DISCO 14 dias (avisos e erros): $txtD"
} catch { Falhou "disco: $($_.Exception.Message)" }

# ---------------------------------------------------------------- 14. SQL Server e sistema atual
Passo 'SQL Server e sistema atual da loja'
try {
  $sv = @(Get-CimInstance Win32_Service -ErrorAction SilentlyContinue | Where-Object { $_.Name -match '^(MSSQL|SQLAgent|SQLBrowser|SQLWriter|MSSQLFDLauncher|SQLTELEMETRY)' } | ForEach-Object { "$($_.Name)=$($_.State)/$($_.StartMode)" })
  $pr = @(Get-Process -Name 'sqlservr' -ErrorAction SilentlyContinue | ForEach-Object { "sqlservr usando $([math]::Round($_.WorkingSet64 / 1MB)) MB (privada $([math]::Round($_.PrivateMemorySize64 / 1MB)) MB)" })
  $bancos = New-Object System.Collections.Generic.List[string]
  $inst = Get-ItemProperty -Path 'HKLM:\SOFTWARE\Microsoft\Microsoft SQL Server\Instance Names\SQL' -ErrorAction SilentlyContinue
  if($inst){
    foreach($p in $inst.PSObject.Properties){
      if($p.Name -like 'PS*'){ continue }
      $setup = Get-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Microsoft SQL Server\$($p.Value)\Setup" -ErrorAction SilentlyContinue
      if(-not $setup.SQLDataRoot){ continue }
      Get-ChildItem -Path (Join-Path $setup.SQLDataRoot 'DATA') -Filter '*.mdf' -ErrorAction SilentlyContinue | Where-Object { $_.BaseName -notmatch '^(master|model|MSDBData|tempdb|modeldev|msdb)$' } | ForEach-Object { $bancos.Add("$($p.Name)/$($_.BaseName) $([math]::Round($_.Length / 1MB)) MB (alterado $($_.LastWriteTime.ToString('dd/MM/yyyy HH:mm')))") }
      $elog = Join-Path $setup.SQLDataRoot 'Log\ERRORLOG'
      if(Test-Path $elog){
        $nomes = @(Select-String -Path $elog -Pattern "(?:Starting up database|banco de dados) '([^']+)'" -AllMatches -ErrorAction SilentlyContinue | ForEach-Object { $_.Matches } | ForEach-Object { $_.Groups[1].Value } | Where-Object { $_ -notmatch '^(master|model|msdb|tempdb|mssqlsystemresource)$' } | Select-Object -Unique)
        if($nomes.Count){ $bancos.Add("bancos abertos desde o último início do SQL: $($nomes -join ', ')") }
      }
    }
  }
  $txtB = 'nenhum banco de usuário na pasta padrão'
  if($bancos.Count){ $txtB = $bancos -join ' | ' }
  Info "SQL SERVER: $($sv -join ', ') | $($pr -join ' ') | $txtB"
  $chavesUn = 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*', 'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*', 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*'
  $instalados = @(foreach($k in $chavesUn){ Get-ItemProperty -Path $k -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -and $_.SystemComponent -ne 1 -and ([string]$_.Publisher -notmatch 'Microsoft|Intel|Realtek|ASUS|Synaptics|ELAN|NVIDIA|Advanced Micro|Qualcomm|Atheros|Broadcom') } })
  $progs = @($instalados | Sort-Object DisplayName -Unique | ForEach-Object { "$($_.DisplayName) $($_.DisplayVersion) [$($_.Publisher)]" })
  Info "PROGRAMAS DE TERCEIROS INSTALADOS ($($progs.Count)): $($progs -join ' || ')"
  $ignorar = 'Memory Compression', 'System', 'Registry', 'Idle', 'svchost', 'csrss', 'lsass', 'smss', 'wininit', 'winlogon', 'services', 'fontdrvhost', 'dwm', 'MsMpEng', 'powershell', 'conhost', 'explorer'
  $abertos = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $ignorar -notcontains $_.ProcessName -and ([string]$_.Company -notmatch 'Microsoft|Intel|Realtek|ASUS|Synaptics|ELAN|Google') -and $_.WorkingSet64 -gt 15MB } | Sort-Object WorkingSet64 -Descending | Select-Object -First 10 | ForEach-Object { "$($_.ProcessName) $([math]::Round($_.WorkingSet64 / 1MB)) MB [$($_.Company)]" })
  Info "PROGRAMAS DE TERCEIROS ABERTOS AGORA: $($abertos -join ', ')"
} catch { Falhou "SQL e sistema atual: $($_.Exception.Message)" }

# ---------------------------------------------------------------- 15. AnyDesk, OneDrive, Windows Update
Passo 'AnyDesk, OneDrive e Windows Update'
try {
  $ad = Get-CimInstance Win32_Service -Filter "Name='AnyDesk'" -ErrorAction SilentlyContinue
  if($ad){
    $exe = [regex]::Match([string]$ad.PathName, '[A-Za-z]:\\[^"]+?\.exe').Value
    $ver = '—'
    if($exe){ $ver = (Get-Item -Path $exe -ErrorAction SilentlyContinue).VersionInfo.ProductVersion }
    Info "ANYDESK (acesso remoto): serviço $($ad.State)/$($ad.StartMode) | versão $ver | processos abertos agora: $(@(Get-Process -Name 'AnyDesk' -ErrorAction SilentlyContinue).Count)"
  } else { Info 'ANYDESK: serviço não encontrado' }
  $odAberto = @(Get-Process -Name 'OneDrive' -ErrorAction SilentlyContinue).Count -gt 0
  $odPessoal = [bool](LerValor 'HKCU:\Software\Microsoft\OneDrive\Accounts\Personal' 'UserFolder')
  $odEmpresa = [bool](LerValor 'HKCU:\Software\Microsoft\OneDrive\Accounts\Business1' 'UserFolder')
  Info "ONEDRIVE: aberto agora=$odAberto | conta pessoal conectada=$odPessoal | conta empresarial conectada=$odEmpresa"
  $sess = New-Object -ComObject Microsoft.Update.Session
  $busca = $sess.CreateUpdateSearcher()
  $total = $busca.GetTotalHistoryCount()
  $res = @{ 0 = 'não iniciada'; 1 = 'em andamento'; 2 = 'ok'; 3 = 'ok com erros'; 4 = 'FALHOU'; 5 = 'cancelada' }
  $hist = @()
  if($total -gt 0){ $hist = @($busca.QueryHistory(0, [math]::Min(150, $total))) }
  $padraoDef = 'Defender|Intelig[eê]ncia de Seguran|Security Intelligence|KB2267602'
  $sist = @($hist | Where-Object { [string]$_.Title -notmatch $padraoDef } | Select-Object -First 6 | ForEach-Object { $t = Corta ([string]$_.Title) 80; "$($_.Date.ToLocalTime().ToString('dd/MM/yyyy')) [$($res[[int]$_.ResultCode])] $t" })
  $defu = $hist | Where-Object { [string]$_.Title -match $padraoDef } | Select-Object -First 1
  $dataDef = '—'
  if($defu){ $dataDef = $defu.Date.ToLocalTime().ToString('dd/MM/yyyy') }
  $pend = (Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired') -or (Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending')
  Info "WINDOWS UPDATE: reinício pendente=$pend | antivírus atualizado em $dataDef | últimas do Windows: $($sist -join ' || ')"
} catch { Falhou "AnyDesk/OneDrive/Update: $($_.Exception.Message)" }

# ---------------------------------------------------------------- 16. impressora e teclados
Passo 'Impressora Elgin e teclados'
try {
  $filas = @(Get-Printer -ErrorAction SilentlyContinue | Where-Object { $_.Name -match 'ELGIN|i9' })
  foreach($f in $filas){
    $drv = Get-PrinterDriver -Name $f.DriverName -ErrorAction SilentlyContinue | Select-Object -First 1
    $v = [int64]$drv.DriverVersion
    $verDrv = '{0}.{1}.{2}.{3}' -f (($v -shr 48) -band 0xFFFF), (($v -shr 32) -band 0xFFFF), (($v -shr 16) -band 0xFFFF), ($v -band 0xFFFF)
    Info "IMPRESSORA '$($f.Name)': status $($f.PrinterStatus) | porta $($f.PortName) | tipo de dado $($f.Datatype) | driver $($f.DriverName) v$verDrv ($($drv.Manufacturer)) | compartilhada=$($f.Shared)"
  }
  if(-not $filas.Count){ Info 'IMPRESSORA ELGIN: nenhuma fila com ELGIN ou i9 no nome' }
  $usbImp = @(Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where-Object { ([string]$_.FriendlyName -match 'impress|print|ELGIN') -and ([string]$_.InstanceId -like 'USB*') } | ForEach-Object { $idp = ([string]$_.InstanceId -split '\\')[1]; "$($_.FriendlyName) [$($_.Status)] $idp" })
  $txtU = 'nenhum dispositivo de impressão USB presente (impressora desligada ou cabo solto?)'
  if($usbImp.Count){ $txtU = $usbImp -join '; ' }
  Info "IMPRESSORA LIGADA NO USB AGORA: $txtU"
  $tec = @(Get-PnpDevice -PresentOnly -Class Keyboard -ErrorAction SilentlyContinue | ForEach-Object { $pt = ([string]$_.InstanceId -split '\\'); "$($_.FriendlyName) [$($pt[0])\$($pt[1])]" })
  Info "TECLADOS PRESENTES ($($tec.Count)): $($tec -join '; ')"
} catch { Falhou "impressora/teclados: $($_.Exception.Message)" }

# ---------------------------------------------------------------- 17. erros de programas e serviços
Passo 'Erros de programas e serviços (7 dias)'
try {
  $apps = @(Get-WinEvent -FilterHashtable @{ LogName = 'Application'; Level = 1, 2; StartTime = $desde7 } -MaxEvents 500 -ErrorAction SilentlyContinue)
  $origens = @($apps | Group-Object ProviderName | Sort-Object Count -Descending | Select-Object -First 6 | ForEach-Object { "$($_.Name)=$($_.Count)" })
  $quebras = @($apps | Where-Object { ($_.ProviderName -eq 'Application Error' -and $_.Id -eq 1000) -or ($_.ProviderName -eq 'Application Hang' -and $_.Id -eq 1002) } | Group-Object { [string]$_.Properties[0].Value } | Sort-Object Count -Descending | Select-Object -First 8 | ForEach-Object { "$($_.Name) x$($_.Count)" })
  $txtQ = 'nenhum'
  if($quebras.Count){ $txtQ = $quebras -join ', ' }
  Info "ERROS DE PROGRAMAS 7 dias: $($origens -join ', ') | programas que travaram ou fecharam sozinhos: $txtQ"
  $scm = @(Get-WinEvent -FilterHashtable @{ LogName = 'System'; ProviderName = 'Service Control Manager'; Level = 1, 2; StartTime = $desde7 } -MaxEvents 30 -ErrorAction SilentlyContinue | ForEach-Object { Corta (([string]$_.Message) -replace '\s+', ' ') 110 } | Select-Object -Unique)
  $txtS = 'nenhum'
  if($scm.Count){ $txtS = $scm -join ' || ' }
  Info "SERVIÇOS COM ERRO 7 dias: $txtS"
  $tpm = @(Get-WinEvent -FilterHashtable @{ LogName = 'System'; Level = 1, 2; StartTime = $desde7 } -MaxEvents 1000 -ErrorAction SilentlyContinue | Where-Object { $_.ProviderName -eq 'Microsoft-Windows-TPM-WMI' } | Group-Object Id | ForEach-Object { "id $($_.Name) x$($_.Count)" })
  $txtT = 'nenhum'
  if($tpm.Count){ $txtT = $tpm -join ', ' }
  Info "TPM / INICIALIZAÇÃO SEGURA 7 dias: $txtT"
  $mpp = Get-MpPreference -ErrorAction SilentlyContinue
  $mps = Get-MpComputerStatus -ErrorAction SilentlyContinue
  Info "DEFENDER: varredura rápida agendada às $($mpp.ScanScheduleQuickScanTime) | varredura completa dia=$($mpp.ScanScheduleDay) hora=$($mpp.ScanScheduleTime) | última rápida $($mps.QuickScanEndTime) | definições de $($mps.AntivirusSignatureLastUpdated)"
  $manut = LerValor 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Schedule\Maintenance' 'Activation Boundary'
  $txtM = 'horário padrão (02:00)'
  if($manut){ $txtM = 'horário ' + $manut }
  Info "MANUTENÇÃO AUTOMÁTICA DO WINDOWS: $txtM"
} catch { Falhou "erros: $($_.Exception.Message)" }

# ---------------------------------------------------------------- resultado
Fim
$dur = [int]((Get-Date) - $inicio).TotalSeconds
$cab = "MOLEKA PDV - OTIMIZAÇÃO + COLETA - $(Get-Date -Format 'dd/MM/yyyy HH:mm') - $dur s"
$saida = @($cab) + @($S)
$saida | Out-File -FilePath (Join-Path $pasta "otimizacao_$carimbo.txt") -Encoding UTF8
''
'===== RESULTADO - COPIE DAQUI ATÉ "FIM" E COLE NO CHAT ====='
$saida
"Arquivos em: $pasta (DESFAZER_otimizacao.ps1 volta tudo como estava)"
'PRÓXIMO PASSO: reinicie o PC (Iniciar > Energia > Reiniciar) quando não houver venda em andamento.'
'===== FIM ====='
}

& {
# MOLEKA PDV — DIAGNÓSTICO DO PC (só leitura: não altera nada). Cole inteiro no PowerShell como administrador.
$ErrorActionPreference = 'SilentlyContinue'
$inicio = Get-Date
$pasta = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Moleka-Diagnostico'
New-Item -ItemType Directory -Force -Path $pasta | Out-Null
$carimbo = Get-Date -Format 'yyyy-MM-dd_HHmm'
$relatorio = Join-Path $pasta "relatorio_$carimbo.txt"
$resumoArq = Join-Path $pasta "resumo_$carimbo.txt"
$R = New-Object System.Collections.Generic.List[string]
$S = New-Object System.Collections.Generic.List[string]
$ctx = @{ n = 0; etapas = 14 }
function Sec($t){ $R.Add(''); $R.Add("===== $t =====") }
function L($t){ $R.Add([string]$t) }
function Tab($obj){ if($obj){ (($obj | Format-Table -AutoSize | Out-String -Width 220).TrimEnd()) -split "`n" | ForEach-Object { $R.Add($_.TrimEnd()) } } else { $R.Add('(nada encontrado)') } }
function Res($t){ $S.Add([string]$t) }
function Passo($t){ $ctx.n++; Write-Progress -Activity 'Diagnóstico do PC (só leitura)' -Status "$($ctx.n)/$($ctx.etapas) - $t" -PercentComplete ([int](100*$ctx.n/$ctx.etapas)) }
function Corta($lista, $max){ $a = @($lista); if($a.Count -gt $max){ ($a[0..($max-1)] -join ', ') + " ... (+$($a.Count-$max))" } else { $a -join ', ' } }
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

Passo 'Sistema'
$os = Get-CimInstance Win32_OperatingSystem; $cs = Get-CimInstance Win32_ComputerSystem; $bios = Get-CimInstance Win32_BIOS
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$uptime = (Get-Date) - $os.LastBootUpTime
$ramGB = [math]::Round($cs.TotalPhysicalMemory/1GB,1)
$mods = @(Get-CimInstance Win32_PhysicalMemory)
$gpu = @(Get-CimInstance Win32_VideoController)
$resol = ($gpu | ForEach-Object { "$($_.CurrentHorizontalResolution)x$($_.CurrentVerticalResolution)" }) -join ', '
Sec 'SISTEMA'
L "Computador: $($cs.Name) | Fabricante/Modelo: $($cs.Manufacturer) $($cs.Model) | BIOS: $($bios.SMBIOSBIOSVersion) ($($bios.ReleaseDate))"
L "Windows: $($os.Caption) $($os.Version) build $($os.BuildNumber) ($($os.OSArchitecture)) | instalado em $($os.InstallDate)"
L "Ligado há: $([int]$uptime.TotalDays) dias e $($uptime.Hours) h (último boot $($os.LastBootUpTime))"
L "CPU: $($cpu.Name) | núcleos $($cpu.NumberOfCores) / threads $($cpu.NumberOfLogicalProcessors) | clock máx $($cpu.MaxClockSpeed) MHz"
L "RAM: $ramGB GB em $($mods.Count) pente(s): $(($mods | ForEach-Object { "$([math]::Round($_.Capacity/1GB))GB@$($_.Speed)MHz" }) -join ', ')"
L "Vídeo: $(($gpu | ForEach-Object { "$($_.Name) [$($_.CurrentHorizontalResolution)x$($_.CurrentVerticalResolution)]" }) -join '; ')"
L "Executando como administrador: $admin"
Res "SISTEMA: $($cs.Manufacturer) $($cs.Model) | $($os.Caption) build $($os.BuildNumber) | CPU $($cpu.Name) ($($cpu.NumberOfCores)c/$($cpu.NumberOfLogicalProcessors)t) | RAM $ramGB GB ($($mods.Count) pente(s)) | ligado há $([int]$uptime.TotalDays)d | resolução $resol | admin=$admin"

Passo 'Discos'
$pd = @(Get-PhysicalDisk | Select-Object FriendlyName, MediaType, BusType, HealthStatus, @{n='GB';e={[math]::Round($_.Size/1GB)}})
if(-not $pd){ $pd = @(Get-CimInstance Win32_DiskDrive | Select-Object @{n='FriendlyName';e={$_.Model}}, @{n='MediaType';e={$_.MediaType}}, @{n='BusType';e={$_.InterfaceType}}, @{n='HealthStatus';e={$_.Status}}, @{n='GB';e={[math]::Round($_.Size/1GB)}}) }
Sec 'DISCOS FÍSICOS'; Tab $pd
if($admin){ $smart = Get-PhysicalDisk | Get-StorageReliabilityCounter | Select-Object DeviceId, Temperature, ReadErrorsTotal, WriteErrorsTotal, Wear, PowerOnHours; Sec 'SMART (confiabilidade)'; Tab $smart }
$vol = @(Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | Select-Object DeviceID, FileSystem, @{n='TotalGB';e={[math]::Round($_.Size/1GB,1)}}, @{n='LivreGB';e={[math]::Round($_.FreeSpace/1GB,1)}}, @{n='LivrePct';e={[math]::Round(100*$_.FreeSpace/$_.Size)}})
Sec 'VOLUMES'; Tab $vol
$c = $vol | Where-Object DeviceID -eq 'C:'
Res "DISCO: $(($pd | ForEach-Object { "$($_.FriendlyName) $($_.MediaType) $($_.BusType) $($_.GB)GB saúde=$($_.HealthStatus)" }) -join ' || ') | C: $($c.LivreGB) GB livres de $($c.TotalGB) ($($c.LivrePct)%)"

Passo 'Desempenho (amostra de 5 s)'
$h = @{}; Get-Process | ForEach-Object { $h[$_.Id] = $_.CPU }
Start-Sleep -Seconds 5
$p2 = @(Get-Process | Select-Object Id, ProcessName, CPU, WorkingSet64, Company)
$cores = [math]::Max(1, [int]$cpu.NumberOfLogicalProcessors)
$uso = foreach($p in $p2){ if($h.ContainsKey($p.Id)){ [pscustomobject]@{ Processo=$p.ProcessName; CPUpct=[math]::Round(100*($p.CPU-$h[$p.Id])/5/$cores,1); RAM_MB=[math]::Round($p.WorkingSet64/1MB); Empresa=$p.Company } } }
$perfOS = Get-CimInstance Win32_PerfFormattedData_PerfOS_Processor -Filter "Name='_Total'"
$mem = Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory
$disk = Get-CimInstance Win32_PerfFormattedData_PerfDisk_PhysicalDisk -Filter "Name='_Total'"
$pf = @(Get-CimInstance Win32_PageFileUsage)
$ramLivre = [math]::Round($mem.AvailableMBytes/1024,1)
Sec 'DESEMPENHO AGORA'
L "CPU total: $($perfOS.PercentProcessorTime)% | RAM disponível: $ramLivre GB de $ramGB | Disco: tempo ativo $($disk.PercentDiskTime)% fila $($disk.CurrentDiskQueueLength)"
L "Arquivo de paginação: $(($pf | ForEach-Object { "$($_.Name) uso $($_.CurrentUsage)MB de $($_.AllocatedBaseSize)MB" }) -join '; ')"
Sec 'TOP 15 PROCESSOS POR CPU (amostra 5 s)'; Tab ($uso | Sort-Object CPUpct -Descending | Select-Object -First 15)
Sec 'TOP 15 PROCESSOS POR RAM'; Tab ($uso | Sort-Object RAM_MB -Descending | Select-Object -First 15)
Res "AGORA: CPU $($perfOS.PercentProcessorTime)% | RAM livre $ramLivre GB | disco ativo $($disk.PercentDiskTime)% fila $($disk.CurrentDiskQueueLength) | processos $($p2.Count) | paginação $(($pf | ForEach-Object { "$($_.CurrentUsage)/$($_.AllocatedBaseSize)MB" }) -join ';')"
Res "TOP CPU: $(($uso | Sort-Object CPUpct -Descending | Select-Object -First 6 | ForEach-Object { "$($_.Processo) $($_.CPUpct)%" }) -join ', ')"
Res "TOP RAM: $(($uso | Sort-Object RAM_MB -Descending | Select-Object -First 6 | ForEach-Object { "$($_.Processo) $($_.RAM_MB)MB" }) -join ', ')"

Passo 'Programas na inicialização'
$st = @(Get-CimInstance Win32_StartupCommand | Select-Object Name, Command, Location, User)
Sec 'INICIALIZAÇÃO (registro e pasta Iniciar)'; Tab $st
$aprov = @()
foreach($k in 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run','HKLM:\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run','HKLM:\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run32','HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\StartupFolder'){
  $i = Get-ItemProperty $k; if($i){ $i.PSObject.Properties | Where-Object { $_.Name -notlike 'PS*' } | ForEach-Object { $b = $_.Value[0]; $aprov += [pscustomobject]@{ Item=$_.Name; Estado=$(if($b -eq 2 -or $b -eq 6){'ATIVADO'}elseif($b -eq 3){'desativado'}else{"?($b)"}); Chave=$k } } } }
Sec 'INICIALIZAÇÃO — estado no Gerenciador de Tarefas'; Tab $aprov
$ativos = @($aprov | Where-Object Estado -eq 'ATIVADO' | ForEach-Object { $_.Item })
Res "INICIALIZAÇÃO: $($st.Count) itens cadastrados; ativados: $(Corta $ativos 15)"

Passo 'Tarefas agendadas'
$tarefas = @(Get-ScheduledTask | Where-Object { $_.State -ne 'Disabled' -and $_.TaskPath -notlike '\Microsoft\*' } | Select-Object TaskName, TaskPath, State, Author)
Sec 'TAREFAS AGENDADAS (não Microsoft, ativas)'; Tab $tarefas
Res "TAREFAS AGENDADAS (não Microsoft): $($tarefas.Count): $(Corta ($tarefas | ForEach-Object { $_.TaskName }) 12)"

Passo 'Serviços'
$svc = @(Get-CimInstance Win32_Service | Where-Object { $_.StartMode -eq 'Auto' -and $_.PathName -notlike '*\Windows\*' } | Select-Object Name, DisplayName, State, PathName)
Sec 'SERVIÇOS AUTOMÁTICOS FORA DA PASTA WINDOWS'; Tab $svc
$chave = @(Get-Service SysMain, WSearch, wuauserv, Spooler, BITS, WinDefend | Select-Object Name, Status, StartType)
Sec 'SERVIÇOS-CHAVE'; Tab $chave
Res "SERVIÇOS de terceiros automáticos: $($svc.Count): $(Corta ($svc | ForEach-Object { "$($_.DisplayName) [$($_.State)]" }) 15)"
Res "SERVIÇOS-CHAVE: $(($chave | ForEach-Object { "$($_.Name)=$($_.Status)/$($_.StartType)" }) -join ', ')"

Passo 'Programas instalados'
$progs = @(foreach($k in 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*','HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*','HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*'){ Get-ItemProperty $k | Where-Object DisplayName | Select-Object DisplayName, DisplayVersion, Publisher, InstallDate }) | Sort-Object DisplayName -Unique
Sec "PROGRAMAS INSTALADOS ($($progs.Count))"; Tab $progs
$pesados = @($progs | Where-Object { $_.DisplayName -match 'McAfee|Norton|Avast|AVG|Kaspersky|Avira|Baidu|CCleaner|Driver ?Booster|Advanced SystemCare|PC ?Speed|Optimizer|Toolbar|WebDiscover|Warsaw|Topaz|Hao123|Search Protect|Reimage|Restoro|OneLaunch|Wave Browser|Módulo de Segurança|Modulo de Seguranca' } | ForEach-Object { $_.DisplayName })
Res "PROGRAMAS: $($progs.Count) instalados | conhecidos por pesar: $(if($pesados){ Corta $pesados 10 } else { 'nenhum da lista' })"

Passo 'Antivírus e atualizações'
$av = @(Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntiVirusProduct | Select-Object displayName, productState)
$mp = Get-MpComputerStatus
$hot = @(Get-HotFix | Sort-Object InstalledOn -Descending | Select-Object -First 5 HotFixID, Description, InstalledOn)
$wu = Get-Service wuauserv
Sec 'ANTIVÍRUS'; Tab $av
L "Defender: antivírus ativo=$($mp.AntivirusEnabled) | tempo real=$($mp.RealTimeProtectionEnabled) | assinaturas de $($mp.AntivirusSignatureLastUpdated) | última verificação rápida $($mp.QuickScanEndTime)"
Sec 'ÚLTIMAS ATUALIZAÇÕES INSTALADAS'; Tab $hot
Res "ANTIVÍRUS: $(($av | ForEach-Object { $_.displayName }) -join ', ') | Defender tempo real=$($mp.RealTimeProtectionEnabled) | última atualização instalada: $(($hot | Select-Object -First 1).InstalledOn) | Windows Update: $($wu.Status)/$($wu.StartType)"

Passo 'Energia e configurações'
$plano = (powercfg /getactivescheme) -join ' '
$fast = (Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power').HiberbootEnabled
$vfx = (Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects').VisualFXSetting
$hib = Test-Path C:\hiberfil.sys
$pfCfg = @(Get-CimInstance Win32_PageFileSetting)
Sec 'ENERGIA E CONFIGURAÇÕES'
L "Plano de energia: $plano"; L "Inicialização rápida (HiberbootEnabled): $fast | hiberfil.sys existe: $hib"
L "Efeitos visuais (VisualFXSetting; vazio/0/1=automático, 2=melhor desempenho, 3=personalizado): $vfx"
L "Arquivo de paginação configurado: $(if($pfCfg){ ($pfCfg | ForEach-Object { "$($_.Name) $($_.InitialSize)-$($_.MaximumSize)MB" }) -join '; ' } else { 'gerenciado pelo Windows' })"
Res "ENERGIA: $plano | inicialização rápida=$fast | efeitos visuais=$vfx | paginação: $(if($pfCfg){'manual'}else{'automática'})"

Passo 'Rede'
$nics = @(Get-NetAdapter | Where-Object Status -eq 'Up' | Select-Object Name, InterfaceDescription, LinkSpeed, MacAddress)
$ips = @(Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway } | Select-Object InterfaceAlias, @{n='IPv4';e={$_.IPv4Address.IPAddress}}, @{n='Gateway';e={$_.IPv4DefaultGateway.NextHop}}, @{n='DNS';e={$_.DNSServer.ServerAddresses -join ','}})
$ping = Test-Connection 8.8.8.8 -Count 3 | Measure-Object ResponseTime -Average
$dns = Resolve-DnsName www.google.com -Type A | Select-Object -First 1
Sec 'REDE'; Tab $nics; Tab $ips
L "Ping 8.8.8.8 (3x): média $([int]$ping.Average) ms ($($ping.Count) respostas) | DNS www.google.com: $(if($dns){ $dns.IPAddress } else { 'FALHOU' })"
Res "REDE: $(($nics | ForEach-Object { "$($_.Name) $($_.LinkSpeed)" }) -join ', ') | IP $(($ips | ForEach-Object { $_.IPv4 }) -join ',') | ping $([int]$ping.Average) ms ($($ping.Count)/3) | DNS ok=$([bool]$dns)"

Passo 'Impressoras'
$stMap = @{1='Outro';2='Desconhecido';3='Pronta';4='Imprimindo';5='Aquecendo';6='Parada';7='Offline'}
$imp = @(Get-CimInstance Win32_Printer | Select-Object Name, DriverName, PortName, @{n='Padrao';e={$_.Default}}, @{n='Status';e={ $stMap[[int]$_.PrinterStatus] }}, WorkOffline, Shared, Network)
$portas = @(Get-PrinterPort | Select-Object Name, Description, PrinterHostAddress, PortNumber)
$drv = @(Get-PrinterDriver | Select-Object Name, Manufacturer, MajorVersion)
$jobs = @(Get-Printer | ForEach-Object { Get-PrintJob -PrinterName $_.Name } | Select-Object PrinterName, DocumentName, JobStatus, SubmittedTime)
$spool = Get-Service Spooler
$pnpPrint = @(Get-PnpDevice | Where-Object { $_.Class -in 'Printer','PrintQueue','USBPrint' -or $_.FriendlyName -match 'printer|impressora|POS|Epson|Elgin|Bematech|Daruma|Tanca|Sweda|Zebra|Argox|Brother|Canon' } | Select-Object Class, FriendlyName, Status, InstanceId)
Sec 'IMPRESSORAS INSTALADAS'; Tab $imp
Sec 'PORTAS DE IMPRESSORA'; Tab $portas
Sec 'DRIVERS DE IMPRESSORA'; Tab $drv
Sec 'FILA DE IMPRESSÃO (trabalhos pendentes)'; Tab $jobs
Sec 'DISPOSITIVOS DE IMPRESSÃO (Plug and Play, inclusive desconectados)'; Tab $pnpPrint
L "Serviço Spooler: $($spool.Status) ($($spool.StartType))"
Res "IMPRESSORAS ($($imp.Count)): $(($imp | ForEach-Object { "$($_.Name) [driver $($_.DriverName); porta $($_.PortName); $($_.Status)$(if($_.WorkOffline){' OFFLINE'})$(if($_.Padrao){' PADRÃO'})]" }) -join ' || ') | spooler=$($spool.Status) | trabalhos presos=$($jobs.Count)"

Passo 'Leitor de código de barras e USB'
$usb = @(Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -like 'USB\VID_*' -or $_.InstanceId -like 'HID\VID_*' } | Select-Object Class, FriendlyName, Status, Manufacturer, @{n='VidPid';e={ ($_.InstanceId -split '\\')[1] }})
$leitor = @($usb | Where-Object { $_.FriendlyName -match 'bar ?code|scanner|leitor|Honeywell|Zebra|Symbol|Datalogic|Elgin|Bematech|Tanca|Metrologic|Opticon|Netum|Eyoyo|Inateck|Sunmi|Xenon|Voyager|Gertec|Newland' -or $_.VidPid -match 'VID_0C2E|VID_05E0|VID_05F9|VID_1EAB|VID_2DD6|VID_0483|VID_04B4|VID_1A86' })
$com = @(Get-CimInstance Win32_SerialPort | Select-Object DeviceID, Name, Description)
$tecl = @(Get-PnpDevice -PresentOnly -Class Keyboard | Select-Object FriendlyName, Status, InstanceId)
Sec 'TECLADOS (leitor USB em modo teclado aparece aqui como "Dispositivo de Teclado HID")'; Tab $tecl
Sec 'PORTAS SERIAIS (COM)'; Tab $com
Sec 'DISPOSITIVOS USB/HID PRESENTES'; Tab $usb
Sec 'POSSÍVEL LEITOR DE CÓDIGO DE BARRAS'; Tab $leitor
Res "LEITOR: $(if($leitor){ ($leitor | ForEach-Object { "$($_.FriendlyName) ($($_.VidPid)) $($_.Status)" }) -join '; ' } else { 'nenhum identificado pelo nome/fabricante' }) | teclados HID: $($tecl.Count) | portas COM: $(if($com){ ($com | ForEach-Object { $_.DeviceID }) -join ',' } else { 'nenhuma' })"

Passo 'Erros recentes (7 dias)'
$desde = (Get-Date).AddDays(-7)
$evS = @(Get-WinEvent -FilterHashtable @{LogName='System'; Level=1,2; StartTime=$desde} -MaxEvents 300 | Group-Object ProviderName | Sort-Object Count -Descending | Select-Object Count, Name)
$evA = @(Get-WinEvent -FilterHashtable @{LogName='Application'; Level=1,2; StartTime=$desde} -MaxEvents 300 | Group-Object ProviderName | Sort-Object Count -Descending | Select-Object -First 15 Count, Name)
$discoEv = @(Get-WinEvent -FilterHashtable @{LogName='System'; StartTime=$desde; ProviderName='disk','Ntfs','stornvme','storahci','volmgr','Microsoft-Windows-Ntfs'} -MaxEvents 50 | Select-Object TimeCreated, Id, ProviderName, @{n='Msg';e={ $m = [string]$_.Message; $m.Substring(0,[math]::Min(140,$m.Length)) -replace "`r|`n",' ' }})
Sec 'ERROS NO LOG DO SISTEMA (7 dias) — por origem'; Tab $evS
Sec 'ERROS NO LOG DE APLICATIVOS (7 dias) — por origem'; Tab $evA
Sec 'EVENTOS DE DISCO (7 dias)'; Tab $discoEv
Res "ERROS 7d: sistema $(($evS | Measure-Object Count -Sum).Sum) ($(Corta ($evS | Select-Object -First 4 | ForEach-Object { "$($_.Name)=$($_.Count)" }) 4)) | aplicativos $(($evA | Measure-Object Count -Sum).Sum) | eventos de disco: $($discoEv.Count)"

Passo 'Arquivos temporários e requisitos do PDV'
function TamMB($p){ if(Test-Path $p){ [math]::Round((Get-ChildItem $p -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum/1MB) } else { 0 } }
$tTemp = TamMB $env:TEMP; $tWinTemp = TamMB 'C:\Windows\Temp'; $tDown = TamMB (Join-Path $env:USERPROFILE 'Downloads'); $tSU = TamMB 'C:\Windows\SoftwareDistribution\Download'
$winOld = Test-Path 'C:\Windows.old'
$lix = (New-Object -ComObject Shell.Application).NameSpace(0xA).Items() | Measure-Object Size -Sum
$lixMB = [math]::Round($lix.Sum/1MB)
Sec 'ESPAÇO RECUPERÁVEL'
L "TEMP do usuário: $tTemp MB | Windows\Temp: $tWinTemp MB | Downloads: $tDown MB | cache do Windows Update: $tSU MB | Lixeira: $lixMB MB | Windows.old: $winOld"
$pyCmd = Get-Command python -ErrorAction SilentlyContinue
$py = if($pyCmd -and $pyCmd.Source -notlike '*WindowsApps*'){ (& $pyCmd.Source --version 2>&1) -join '' } elseif($pyCmd){ 'só o atalho da Loja (não instalado)' } else { 'não instalado' }
$wv2 = Get-ItemProperty 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}' -ErrorAction SilentlyContinue
$git = Get-Command git -ErrorAction SilentlyContinue
Sec 'REQUISITOS DO MOLEKA PDV'
L "Python: $py | WebView2 Runtime: $(if($wv2){"v$($wv2.pv)"}else{'NÃO ENCONTRADO'}) | Git: $(if($git){$git.Source}else{'não instalado'}) | Resolução: $resol"
Res "ESPAÇO RECUPERÁVEL: TEMP $tTemp MB + WinTemp $tWinTemp MB + Downloads $tDown MB + cache WU $tSU MB + Lixeira $lixMB MB | Windows.old=$winOld"
Res "PDV: Python=$py | WebView2=$(if($wv2){$wv2.pv}else{'NÃO'}) | Git=$([bool]$git)"

Write-Progress -Activity 'Diagnóstico do PC (só leitura)' -Completed
$dur = [int]((Get-Date) - $inicio).TotalSeconds
$cab = @("MOLEKA PDV — DIAGNÓSTICO DO PC — $(Get-Date -Format 'dd/MM/yyyy HH:mm') — $dur s — só leitura, nada foi alterado")
($cab + $R) | Out-File $relatorio -Encoding UTF8
($cab + $S) | Out-File $resumoArq -Encoding UTF8
''
'===== RESUMO — COPIE DAQUI ATÉ "FIM" E COLE NO CHAT ====='
$cab; $S
"Relatório completo: $relatorio"
'===== FIM ====='
}

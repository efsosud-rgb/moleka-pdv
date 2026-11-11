# Testa o Moleka PDV empacotado, no Windows: sobe o servidor, confere as páginas, abre a janela
# e tira um print da tela. Roda no GitHub Actions depois do PyInstaller e depois do instalador.
#
# Uso:
#   .\packaging\teste_windows.ps1                               # testa dist\MolekaPDV\MolekaPDV.exe
#   .\packaging\teste_windows.ps1 -Instalador dist\Moleka...exe # instala em silêncio e testa o instalado
param(
  [string]$Exe = 'dist\MolekaPDV\MolekaPDV.exe',
  [string]$Instalador = '',
  [string]$Saida = 'dist\teste'
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
New-Item -ItemType Directory -Force $Saida | Out-Null
$rotulo = 'pasta'

if ($Instalador) {
  $rotulo = 'instalado'
  Write-Host "Instalando em silêncio: $Instalador"
  $inst = Start-Process -FilePath $Instalador -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', "/LOG=$Saida\instalador.log" -Wait -PassThru
  if ($inst.ExitCode -ne 0) { throw "o instalador terminou com código $($inst.ExitCode)" }
  $Exe = Join-Path $env:LOCALAPPDATA 'Programs\MolekaPDV\MolekaPDV.exe'
  if (-not (Test-Path $Exe)) { throw "o instalador não criou $Exe" }
  $atalho = Join-Path ([Environment]::GetFolderPath('Programs')) 'Moleka PDV.lnk'
  if (-not (Test-Path $atalho)) { throw "o instalador não criou o atalho do menu Iniciar ($atalho)" }
  Write-Host "OK: instalado em $Exe, com atalho no menu Iniciar"
}
if (-not (Test-Path $Exe)) { throw "não achei o executável $Exe" }

# Dados de teste numa pasta temporária, nunca na pasta real do usuário.
$env:MOLEKA_PDV_DADOS = Join-Path ([IO.Path]::GetTempPath()) "moleka-teste-$rotulo"
if (Test-Path $env:MOLEKA_PDV_DADOS) { Remove-Item -Recurse -Force $env:MOLEKA_PDV_DADOS }

function Esperar-Servidor([int]$Porta, [int]$Segundos = 60) {
  $limite = (Get-Date).AddSeconds($Segundos)
  while ((Get-Date) -lt $limite) {
    try { return Invoke-RestMethod "http://127.0.0.1:$Porta/api/status" -TimeoutSec 3 } catch { Start-Sleep -Milliseconds 500 }
  }
  throw "o servidor local não respondeu na porta $Porta em $Segundos s"
}

function Copiar-Log([string]$Nome) {
  $log = Join-Path $env:MOLEKA_PDV_DADOS 'logs\moleka.log'
  if (Test-Path $log) { Copy-Item $log (Join-Path $Saida $Nome) -Force }
}

# 1) Só o servidor: API e páginas respondem?
$porta = 8766
$srv = Start-Process -FilePath $Exe -ArgumentList '--sem-janela', '--porta', $porta -PassThru
try {
  $status = Esperar-Servidor $porta
  if ($status.app -ne 'Moleka PDV') { throw "resposta inesperada de /api/status: $($status | ConvertTo-Json -Compress)" }
  if (-not $status.banco.ok) { throw "o banco local não abriu: $($status.banco.motivo)" }
  Write-Host "OK: servidor no ar, versão $($status.versao), banco $($status.banco.texto)"
  foreach ($caminho in '/', '/inicio', '/caixa', '/produtos', '/financeiro', '/static/css/moleka.css', '/static/js/moleka.js', '/assets/brand/mascote.png') {
    $r = Invoke-WebRequest "http://127.0.0.1:$porta$caminho" -UseBasicParsing -TimeoutSec 10
    if ($r.StatusCode -ne 200) { throw "$caminho respondeu $($r.StatusCode)" }
    Write-Host "OK: $caminho ($($r.RawContentLength) bytes)"
  }
}
finally {
  Copiar-Log "servidor-$rotulo.log"
  if (-not $srv.HasExited) { Stop-Process -Id $srv.Id -Force }
}
Start-Sleep -Seconds 2

# 2) Com a janela: abre, desenha e continua de pé?
try { Set-DisplayResolution -Width 1366 -Height 768 -Force | Out-Null } catch { Write-Host "Aviso: não mudei a resolução da tela ($($_.Exception.Message))" }
$app = Start-Process -FilePath $Exe -PassThru
try {
  $null = Esperar-Servidor 8765
  Start-Sleep -Seconds 15   # tempo para o WebView2 desenhar a capa
  $app.Refresh()
  if ($app.HasExited) { throw "o programa fechou sozinho (código $($app.ExitCode))" }
  $titulo = (Get-Process -Id $app.Id).MainWindowTitle
  Write-Host "Janela principal: '$titulo'"

  Add-Type -AssemblyName System.Windows.Forms, System.Drawing
  $tela = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
  $bmp = New-Object System.Drawing.Bitmap $tela.Width, $tela.Height
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.CopyFromScreen($tela.Location, [System.Drawing.Point]::Empty, $tela.Size)
  $print = Join-Path $Saida "janela-$rotulo.png"
  $bmp.Save($print, [System.Drawing.Imaging.ImageFormat]::Png)
  $g.Dispose(); $bmp.Dispose()
  Write-Host "OK: print da tela em $print ($($tela.Width)x$($tela.Height))"

  if ($titulo -ne 'Moleka PDV') { throw "a janela do sistema não apareceu (título encontrado: '$titulo')" }
  Write-Host "OK: a janela 'Moleka PDV' está aberta"
}
finally {
  Copiar-Log "janela-$rotulo.log"
  if (-not $app.HasExited) { Stop-Process -Id $app.Id -Force }
}
Write-Host "TESTE CONCLUÍDO ($rotulo)"

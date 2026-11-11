# Testa o Moleka PDV empacotado, no Windows: sobe o servidor, confere as páginas e o login, abre a
# janela e tira um print da tela. Roda no GitHub Actions depois do PyInstaller e depois do instalador.
#
# Uso:
#   .\packaging\teste_windows.ps1                               # testa dist\MolekaPDV\MolekaPDV.exe
#   .\packaging\teste_windows.ps1 -Instalador dist\Moleka...exe # instala em silêncio e testa o instalado
#   .\packaging\teste_windows.ps1 -SoServidor                   # só a parte sem janela (API, páginas e login)
param(
  [string]$Exe = 'dist\MolekaPDV\MolekaPDV.exe',
  [string]$Instalador = '',
  [string]$Saida = 'dist\teste',
  [switch]$SoServidor
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
  $log = Join-Path (Join-Path $env:MOLEKA_PDV_DADOS 'logs') 'moleka.log'
  if (Test-Path $log) { Copy-Item $log (Join-Path $Saida $Nome) -Force }
}

# Faz um pedido que deve ser recusado e devolve o código HTTP (401, 403...). 200 = foi aceito.
function Codigo-Recusado([scriptblock]$Pedido) {
  try { & $Pedido | Out-Null; return 200 } catch { return [int]$_.Exception.Response.StatusCode }
}

# 1) Só o servidor: API, páginas e login respondem?
$porta = 8766
$base = "http://127.0.0.1:$porta"
$srv = Start-Process -FilePath $Exe -ArgumentList '--sem-janela', '--porta', $porta -PassThru
try {
  $status = Esperar-Servidor $porta
  if ($status.app -ne 'Moleka PDV') { throw "resposta inesperada de /api/status: $($status | ConvertTo-Json -Compress)" }
  if (-not $status.banco.ok) { throw "o banco local não abriu: $($status.banco.motivo)" }
  Write-Host "OK: servidor no ar, versão $($status.versao), banco $($status.banco.texto)"

  # O que abre sem login: a capa e os arquivos da interface.
  foreach ($caminho in '/', '/static/css/moleka.css', '/static/js/moleka.js', '/static/js/entrada.js', '/static/js/operadores.js', '/assets/brand/mascote.png') {
    $r = Invoke-WebRequest "$base$caminho" -UseBasicParsing -TimeoutSec 10
    if ($r.StatusCode -ne 200) { throw "$caminho respondeu $($r.StatusCode)" }
    Write-Host "OK: $caminho ($($r.RawContentLength) bytes)"
  }

  # Banco novo: a capa pede o primeiro acesso, e as telas internas voltam para a capa.
  $sessao = Invoke-RestMethod "$base/api/sessao" -TimeoutSec 10
  if ($sessao.configurado -or $sessao.operador) { throw "banco novo deveria estar sem operador: $($sessao | ConvertTo-Json -Compress)" }
  $r = Invoke-WebRequest "$base/inicio" -UseBasicParsing -TimeoutSec 10
  if ($r.Content -notmatch 'data-tela="capa"' -or $r.Content -notmatch 'Primeiro acesso') { throw 'sem login, /inicio deveria voltar para a capa com o primeiro acesso' }
  $recusa = Codigo-Recusado { Invoke-WebRequest "$base/api/produtos" -UseBasicParsing -TimeoutSec 10 }
  if ($recusa -ne 401) { throw "sem login, /api/produtos deveria responder 401 (respondeu $recusa)" }
  Write-Host 'OK: sem login, só a capa abre (telas internas voltam para a capa; a API responde 401)'

  # Primeiro acesso: cria o gerente de teste. A senha é sorteada aqui e só existe neste teste.
  $senha = [guid]::NewGuid().ToString('N').Substring(0, 12)
  $gerente = @{ nome = 'Gerente de Teste'; login = 'gerente'; senha = $senha } | ConvertTo-Json -Compress
  $r = Invoke-WebRequest "$base/api/configuracao-inicial" -Method Post -Body $gerente -ContentType 'application/json' -SessionVariable janela -UseBasicParsing -TimeoutSec 20
  if ($r.StatusCode -ne 201) { throw "a configuração inicial respondeu $($r.StatusCode)" }
  foreach ($tela in 'inicio', 'caixa', 'produtos', 'financeiro', 'operadores') {
    $r = Invoke-WebRequest "$base/$tela" -WebSession $janela -UseBasicParsing -TimeoutSec 10
    if ($r.Content -notmatch "data-tela=`"$tela`"") { throw "a tela /$tela não abriu para o gerente logado" }
    if ($r.Content -notmatch 'Operador: Gerente de Teste') { throw "a tela /$tela não mostra o operador logado" }
    Write-Host "OK: /$tela com o gerente logado ($($r.RawContentLength) bytes)"
  }

  # Sair e entrar de novo: confere a senha gravada (hash) dentro do programa empacotado.
  Invoke-WebRequest "$base/api/sair" -Method Post -WebSession $janela -UseBasicParsing -TimeoutSec 10 | Out-Null
  $r = Invoke-WebRequest "$base/inicio" -WebSession $janela -UseBasicParsing -TimeoutSec 10
  if ($r.Content -notmatch 'id="form-login"') { throw 'depois de sair, a capa deveria pedir o login' }
  $errada = @{ login = 'gerente'; senha = 'senha-errada' } | ConvertTo-Json -Compress
  $recusa = Codigo-Recusado { Invoke-WebRequest "$base/api/login" -Method Post -Body $errada -ContentType 'application/json' -UseBasicParsing -TimeoutSec 20 }
  if ($recusa -ne 401) { throw "senha errada deveria responder 401 (respondeu $recusa)" }
  $certa = @{ login = 'gerente'; senha = $senha } | ConvertTo-Json -Compress
  $r = Invoke-WebRequest "$base/api/login" -Method Post -Body $certa -ContentType 'application/json' -WebSession $janela -UseBasicParsing -TimeoutSec 20
  if ($r.StatusCode -ne 200) { throw "o login com a senha certa respondeu $($r.StatusCode)" }
  $operadores = @(Invoke-RestMethod "$base/api/operadores" -WebSession $janela -TimeoutSec 10)
  if ($operadores.Count -ne 1 -or $operadores[0].perfil -ne 'gerente') { throw "lista de operadores inesperada: $($operadores | ConvertTo-Json -Compress)" }
  Write-Host 'OK: sair, senha errada recusada (401), login com a senha certa e lista de operadores'

  # Recuperação de acesso (senha esquecida): o programa sorteia uma senha provisória e mostra numa
  # caixa de mensagem. Confere que a caixa aparece e que a senha antiga deixa de valer.
  if ($env:OS -eq 'Windows_NT') {
    $rec = Start-Process -FilePath $Exe -ArgumentList '--redefinir-senha' -PassThru
    $tituloRec = ''
    $limite = (Get-Date).AddSeconds(40)
    while ((Get-Date) -lt $limite -and -not $rec.HasExited -and -not $tituloRec) {
      Start-Sleep -Milliseconds 500
      $rec.Refresh()
      if (-not $rec.HasExited) { $tituloRec = [string](Get-Process -Id $rec.Id -ErrorAction SilentlyContinue).MainWindowTitle }
    }
    if ($rec.HasExited) { throw "a recuperação de acesso fechou sem mostrar a senha provisória (código $($rec.ExitCode))" }
    Stop-Process -Id $rec.Id -Force
    if ($tituloRec -notmatch 'recupera') { throw "a caixa da recuperação de acesso não apareceu (título encontrado: '$tituloRec')" }
    $recusa = Codigo-Recusado { Invoke-WebRequest "$base/api/login" -Method Post -Body $certa -ContentType 'application/json' -UseBasicParsing -TimeoutSec 20 }
    if ($recusa -ne 401) { throw "depois da recuperação, a senha antiga deveria parar de valer (respondeu $recusa)" }
    Write-Host "OK: recuperação de acesso mostrou a caixa '$tituloRec' e a senha antiga parou de valer"
  }
}
finally {
  Copiar-Log "servidor-$rotulo.log"
  if (-not $srv.HasExited) { Stop-Process -Id $srv.Id -Force }
}
if ($SoServidor) { Write-Host "TESTE CONCLUÍDO ($rotulo, só o servidor)"; return }
Start-Sleep -Seconds 2

# 2) Com a janela: abre, desenha e continua de pé?
# No teste da pasta o banco é apagado antes, para o print mostrar a tela de primeiro acesso;
# no teste do instalado fica o gerente criado acima, e o print mostra a tela de login.
if ($rotulo -eq 'pasta') {
  try { Remove-Item -Recurse -Force $env:MOLEKA_PDV_DADOS }
  catch { Start-Sleep -Seconds 3; Remove-Item -Recurse -Force $env:MOLEKA_PDV_DADOS }  # arquivo ainda preso pelo processo encerrado
}
try { Set-DisplayResolution -Width 1366 -Height 768 -Force | Out-Null } catch { Write-Host "Aviso: não mudei a resolução da tela ($($_.Exception.Message))" }
$app = Start-Process -FilePath $Exe -PassThru
try {
  $null = Esperar-Servidor 8765
  $sessao = Invoke-RestMethod 'http://127.0.0.1:8765/api/sessao' -TimeoutSec 10
  $esperado = ($rotulo -ne 'pasta')
  if ([bool]$sessao.configurado -ne $esperado) { throw "a janela abriu com configurado=$($sessao.configurado), esperado $esperado" }
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

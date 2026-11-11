# Moleka PDV - abre a versao de teste que foi baixada em .zip (sem instalador).
#
# Como usar: abra o Windows PowerShell, cole este texto inteiro e aperte Enter.
# O que faz, mostrando uma barra de andamento:
#   1. acha o arquivo MolekaPDV-codigo-<versao>.zip mais novo (Downloads, Area de Trabalho ou Documentos);
#   2. confere se ha Python 3.12 ou mais novo;
#   3. confere se o Moleka PDV antigo esta fechado;
#   4. extrai o codigo em  <sua pasta de usuario>\MolekaPDV-dev\MolekaPDV-codigo-<versao>;
#   5. abre o sistema (tools\abrir_pelo_codigo.py).
# Nao muda nenhuma configuracao do Windows. Os dados do sistema ficam em %APPDATA%\MolekaPDV e
# nao sao tocados. A unica pasta apagada e a do proprio codigo desta mesma versao, se ja
# existir de uma tentativa anterior (ela e recriada em seguida).
#
# Sem acentos de proposito: o texto e colado no PowerShell, e acento colado pode sair trocado.
# O teste automatico (.github/workflows/teste-comando-windows.yml) roda este mesmo texto no
# Windows PowerShell 5.1 com MOLEKA_SO_PREPARAR=1, que prepara tudo e nao abre a janela.
# O bloco abaixo nao tem linhas em branco de proposito: colado no PowerShell, uma linha em
# branco no meio poderia encerrar o comando antes da hora.
& {
  $titulo = 'Moleka PDV - abrir a versao baixada'
  function Passo([int]$n, [string]$texto) {
    Write-Progress -Activity $titulo -Status "Passo $n de 5: $texto" -PercentComplete ($n * 20 - 10)
    Write-Host "[$n/5] $texto"
  }
  function Parar([string]$texto) {
    Write-Progress -Activity $titulo -Completed
    Write-Host ''
    Write-Host "=== MOLEKA: PAREI === $texto"
  }
  Passo 1 'Procurando o arquivo baixado...'
  $pastas = @((Join-Path $env:USERPROFILE 'Downloads'), [Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('MyDocuments'))
  try { $pastas += (New-Object -ComObject Shell.Application).NameSpace('shell:Downloads').Self.Path } catch { }
  $pastas = @($pastas | Where-Object { $_ -and (Test-Path $_) } | Select-Object -Unique)
  $achados = @(foreach ($pasta in $pastas) {
      Get-ChildItem -Path $pasta -Filter 'MolekaPDV-codigo-*.zip' -File -ErrorAction SilentlyContinue | ForEach-Object {
        if ($_.Name -match '^MolekaPDV-codigo-(\d+\.\d+\.\d+)') {
          New-Object PSObject -Property @{ Arquivo = $_; Versao = [version]$Matches[1] }
        }
      }
    })
  if ($achados.Count -eq 0) {
    Parar "NAO ACHEI nenhum arquivo MolekaPDV-codigo-...zip. Procurei em: $($pastas -join ' ; '). Baixe o arquivo enviado na conversa e rode este comando de novo."
    return
  }
  $escolhido = $achados | Sort-Object @{ Expression = { $_.Versao }; Descending = $true }, @{ Expression = { $_.Arquivo.LastWriteTime }; Descending = $true } | Select-Object -First 1
  $zip = $escolhido.Arquivo
  $nome = "MolekaPDV-codigo-$($escolhido.Versao)"
  Write-Host "      Achei: $($zip.FullName) (versao $($escolhido.Versao), $([math]::Round($zip.Length / 1MB, 1)) MB)"
  Passo 2 'Conferindo o Python...'
  $py = $null
  $versaoPy = ''
  foreach ($comando in 'py', 'python') {
    if (-not (Get-Command $comando -ErrorAction SilentlyContinue)) { continue }
    $saida = ''
    try { $saida = [string](& $comando -c "import sys; print('%d.%d' % sys.version_info[:2])") } catch { $saida = '' }
    if ($saida -match '^\d+\.\d+$' -and ([version]$saida -ge [version]'3.12')) { $py = $comando; $versaoPy = $saida; break }
  }
  if (-not $py) {
    Parar 'NAO ACHEI o Python 3.12 ou mais novo neste computador (comandos py e python).'
    return
  }
  Write-Host "      Python $versaoPy (comando: $py)"
  Passo 3 'Conferindo se o Moleka PDV antigo esta fechado...'
  $aberto = $false
  try { $ligacao = New-Object Net.Sockets.TcpClient; $ligacao.Connect('127.0.0.1', 8765); $aberto = $ligacao.Connected; $ligacao.Close() } catch { $aberto = $false }
  if ($aberto) {
    Parar 'O Moleka PDV ainda esta ABERTO neste computador. Feche a janela do sistema (e a janela antiga do PowerShell) e rode este comando de novo.'
    return
  }
  Write-Host '      Nenhum Moleka PDV aberto.'
  Passo 4 'Extraindo o codigo novo...'
  $destino = Join-Path $env:USERPROFILE 'MolekaPDV-dev'
  $pastaDoCodigo = Join-Path $destino $nome
  try {
    New-Item -ItemType Directory -Force $destino | Out-Null
    if (Test-Path $pastaDoCodigo) { Remove-Item -Recurse -Force $pastaDoCodigo -ErrorAction Stop }
    Expand-Archive -Path $zip.FullName -DestinationPath $destino -Force -ErrorAction Stop
  } catch {
    Parar "NAO CONSEGUI extrair o arquivo: $($_.Exception.Message)"
    return
  }
  if (-not (Test-Path (Join-Path $pastaDoCodigo 'tools\abrir_pelo_codigo.py'))) {
    Parar "A extracao nao criou a pasta esperada ($pastaDoCodigo)."
    return
  }
  Write-Host "      Codigo em: $pastaDoCodigo"
  Passo 5 'Abrindo o sistema (esta janela do PowerShell precisa ficar aberta)...'
  Write-Progress -Activity $titulo -Completed
  $extras = @()
  if ($env:MOLEKA_SO_PREPARAR) { $extras += '--so-preparar' }  # so o teste automatico usa
  Set-Location $pastaDoCodigo
  & $py 'tools\abrir_pelo_codigo.py' @extras
}

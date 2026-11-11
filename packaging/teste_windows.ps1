# Testa o Moleka PDV empacotado, no Windows: sobe o servidor, confere as páginas e o login, faz
# uma venda de teste do começo ao fim (cadastro, caixa, duas formas de pagamento, fechamento),
# dá entrada numa nota fictícia por XML, confere estoque, custo, fluxo de caixa e DRE, abre a
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
  $scripts = 'moleka', 'entrada', 'operadores', 'produtos', 'clientes', 'tabelas', 'controle_caixa', 'caixa', 'estoque', 'entrada_nf', 'financeiro' | ForEach-Object { "/static/js/$_.js" }
  foreach ($caminho in @('/', '/static/css/moleka.css', '/assets/brand/mascote.png') + $scripts) {
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
  foreach ($tela in 'inicio', 'caixa', 'controle-caixa', 'produtos', 'clientes', 'tabelas-preco', 'estoque', 'entrada-nf', 'financeiro', 'operadores') {
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

  # Cadastros, caixa e venda dentro do programa empacotado. Os dados são de teste (fictícios) e
  # ficam na pasta temporária. Os valores esperados foram calculados à mão:
  #   10 picolés na faixa "a partir de 10" = 10 x 4,50 = 45,00
  #   Pix de 20,00 com 5% de desconto quita 20,00 / 0,95 = 21,05; falta 23,95
  #   dinheiro 30,00 para 23,95: troco 6,05; total pago = 45,00 - 1,05 = 43,95
  #   dinheiro esperado na gaveta = fundo 100,00 + 23,95 = 123,95
  # Antes da venda entram 20 picolés a 2,00 (custo médio 2,00): a venda de 10 custa 20,00.
  function Pedir([string]$Metodo, [string]$Caminho, $Corpo = $null) {
    $pedido = @{ Uri = "$base$Caminho"; Method = $Metodo; WebSession = $janela; TimeoutSec = 20 }
    if ($null -ne $Corpo) {
      $pedido.Body = [Text.Encoding]::UTF8.GetBytes(($Corpo | ConvertTo-Json -Compress -Depth 6))
      $pedido.ContentType = 'application/json; charset=utf-8'
    }
    return Invoke-RestMethod @pedido
  }
  function Lista($Resposta) { return , @($Resposta | ForEach-Object { $_ }) }
  function Conferir([string]$Nome, $Obtido, $Esperado) {
    if ("$Obtido" -ne "$Esperado") { throw "${Nome}: esperado '$Esperado', veio '$Obtido'" }
    Write-Host "OK: ${Nome} = $Obtido"
  }
  $tabelas = Lista (Pedir GET '/api/tabelas-preco')
  $varejo = $tabelas | Where-Object { $_.padrao }
  Conferir 'tabela padrão criada com o banco' $varejo.nome 'VAREJO'
  Conferir 'tabelas de preço criadas com o banco' (($tabelas | ForEach-Object { $_.nome }) -join ',') 'VAREJO,ATACADO'
  $null = Pedir PUT '/api/formas-pagamento/pix' @{ ajuste_bp = -500; ativo = $true }
  $faixas = @(@{ tabela_id = $varejo.id; qtd_min = '1'; preco_centavos = 500 }, @{ tabela_id = $varejo.id; qtd_min = '10'; preco_centavos = 450 })
  $produto = Pedir POST '/api/produtos' @{ descricao = 'Picolé de teste'; ean = '7890000000017'; precos = $faixas }
  Conferir 'código automático do produto' $produto.codigo '1'
  Conferir 'pesquisa sem acento ("picole" acha o produto)' (Lista (Pedir GET '/api/produtos?busca=picole')).Count 1
  $entrada = Pedir POST '/api/estoque/ajustes' @{ produto_id = $produto.id; tipo = 'entrada'; quantidade = '20'; motivo = 'entrada de teste'; custo_unitario_centavos = 200 }
  Conferir 'estoque depois da entrada (saldo; custo médio em centavos)' "$($entrada.saldo);$($entrada.custo_centavos)" '20.000;200'
  $null = Pedir POST '/api/caixa/abrir' @{ fundo_troco_centavos = 10000 }
  $venda = (Pedir POST '/api/venda/itens' @{ codigo = '7890000000017'; quantidade = 10 }).venda
  Conferir 'preço por quantidade (10 x 4,50), em centavos' $venda.subtotal_centavos 4500
  $venda = (Pedir POST '/api/venda/pagamentos' @{ forma = 'pix'; valor_centavos = 2000 }).venda
  Conferir 'falta depois do Pix de 20,00 com 5% de desconto, em centavos' $venda.restante_centavos 2395
  $venda = (Pedir POST '/api/venda/pagamentos' @{ forma = 'dinheiro'; valor_centavos = 3000 }).venda
  Conferir 'troco do dinheiro, em centavos' $venda.troco_centavos 605
  $recusa = Codigo-Recusado { Pedir POST '/api/venda/finalizar' @{ emitir_nfce = $true } }
  if ($recusa -ne 409) { throw "finalizar com NFC-e sem a parte fiscal configurada deveria responder 409 (respondeu $recusa)" }
  Write-Host 'OK: finalizar com NFC-e é recusado enquanto a parte fiscal não está configurada (409)'
  $venda = (Pedir POST '/api/venda/finalizar' @{ emitir_nfce = $false }).venda
  Conferir 'situação da venda' $venda.status 'finalizada'
  Conferir 'total da venda (45,00 - 1,05 do Pix), em centavos' $venda.total_centavos 4395
  $resumo = Pedir GET '/api/vendas/resumo-hoje'
  Conferir 'saldo de vendas do dia' "$($resumo.quantidade) venda, $($resumo.total_centavos) centavos" '1 venda, 4395 centavos'
  $fechado = Pedir POST '/api/caixa/fechar' @{ contado = @{ dinheiro = 12395; pix = 2000; debito = 0; credito = 0 } }
  Conferir 'diferenças no fechamento (dinheiro, Pix, débito, crédito)' (($fechado.formas | ForEach-Object { $_.diferenca_centavos }) -join ',') '0,0,0,0'

  # Entrada de NF por XML, com uma nota FICTÍCIA escrita aqui mesmo (nenhuma empresa ou nota real):
  #   2 caixas de picolé a 48,00 = 96,00 + frete 4,00 + ICMS-ST 9,60 = 109,60 de custo;
  #   a nota diz 24 por caixa e traz o código de barras do picolé: entram 48 a 109,60 / 48 = 2,28;
  #   estoque: 20 - 10 vendidos = 10 a 2,00; + 48 a 2,28 = 129,44 em 58 = 2,2317 -> 2,23.
  $xml = @'
<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
<NFe xmlns="http://www.portalfiscal.inf.br/nfe">
<infNFe Id="NFe35261111222333000181550010000001231000001340" versao="4.00">
<ide><cUF>35</cUF><natOp>VENDA DE MERCADORIA (FICTICIA)</natOp><mod>55</mod><serie>1</serie><nNF>123</nNF><dhEmi>2026-11-03T10:15:00-03:00</dhEmi><tpNF>1</tpNF></ide>
<emit><CNPJ>11222333000181</CNPJ><xNome>FORNECEDOR FICTICIO DE TESTE LTDA</xNome></emit>
<dest><CNPJ>11444777000161</CNPJ><xNome>LOJA FICTICIA DE TESTE</xNome></dest>
<det nItem="1">
<prod><cProd>PIC-24</cProd><cEAN>SEM GTIN</cEAN><xProd>PICOLE FICTICIO DE TESTE CX 24</xProd><NCM>21050010</NCM><CFOP>5102</CFOP><uCom>CX</uCom><qCom>2.0000</qCom><vUnCom>48.0000000000</vUnCom><vProd>96.00</vProd><cEANTrib>7890000000017</cEANTrib><uTrib>UN</uTrib><qTrib>48.0000</qTrib><vUnTrib>2.0000000000</vUnTrib><vFrete>4.00</vFrete><indTot>1</indTot></prod>
<imposto><ICMS><ICMS10><orig>0</orig><CST>10</CST><vBC>96.00</vBC><vICMS>11.52</vICMS><vBCST>96.00</vBCST><vICMSST>9.60</vICMSST></ICMS10></ICMS></imposto>
</det>
<total><ICMSTot><vProd>96.00</vProd><vNF>109.60</vNF></ICMSTot></total>
<cobr><fat><nFat>123</nFat></fat><dup><nDup>001</nDup><dVenc>2026-12-03</dVenc><vDup>109.60</vDup></dup></cobr>
</infNFe>
</NFe>
<protNFe versao="4.00"><infProt><chNFe>35261111222333000181550010000001231000001340</chNFe><cStat>100</cStat><xMotivo>Situacao ficticia de teste</xMotivo></infProt></protNFe>
</nfeProc>
'@
  $lida = Pedir POST '/api/compras/conferir' @{ xml = $xml }
  Conferir 'nota fictícia lida (número; total em centavos; avisos)' "$($lida.numero);$($lida.total_centavos);$(@($lida.avisos).Count)" '123;10960;0'
  Conferir 'nota: produto achado pelo código de barras, com o fator da nota' "$($lida.itens[0].sugestao_produto_id);$($lida.itens[0].sugestao_fator);$($lida.itens[0].sugestao_origem)" "$($produto.id);24.000;ean"
  $feito = Pedir POST '/api/compras/importar' @{ xml = $xml; itens = @(@{ numero = 1; acao = 'vincular'; produto_id = $produto.id; fator = 24 }) }
  Conferir 'nota importada (entrou; custo de cada, em centavos; contas a pagar)' "$($feito.nota.itens[0].entrou);$($feito.nota.itens[0].custo_unitario_centavos);$($feito.contas_a_pagar)" '48.000;228;1'
  $guardado = Join-Path $env:MOLEKA_PDV_DADOS "xml\entrada\$($lida.chave).xml"
  if (-not (Test-Path $guardado)) { throw "o XML da nota não foi guardado em $guardado" }
  Write-Host 'OK: o XML da nota ficou guardado na pasta de dados'
  $recusa = Codigo-Recusado { Pedir POST '/api/compras/importar' @{ xml = $xml; itens = @(@{ numero = 1; acao = 'ignorar' }) } }
  if ($recusa -ne 409) { throw "a mesma nota importada de novo deveria responder 409 (respondeu $recusa)" }
  Write-Host 'OK: a mesma nota não entra duas vezes (409)'
  $estoque = Pedir GET '/api/estoque'
  Conferir 'estoque depois da nota (saldo; custo médio; valor, em centavos)' "$($estoque.itens[0].saldo);$($estoque.itens[0].custo_centavos);$($estoque.resumo.valor_centavos)" '58.000;223;12934'

  # Financeiro. Receita líquida 45,00 - 1,05 do Pix = 43,95; custo da venda 10 x 2,00 = 20,00;
  # lucro bruto 23,95; despesa de teste 10,00 paga hoje: resultado 13,95 e saldo do dia 33,95.
  # A data de hoje na loja, lida como texto (o PowerShell pode converter datas do JSON sozinho).
  $bruto = (Invoke-WebRequest "$base/api/vendas/resumo-hoje" -WebSession $janela -UseBasicParsing -TimeoutSec 10).Content
  if ($bruto -notmatch '"dia":\s*"(\d{4}-\d{2}-\d{2})"') { throw "não achei a data de hoje em /api/vendas/resumo-hoje: $bruto" }
  $hoje = $Matches[1]
  $categorias = Lista (Pedir GET '/api/financeiro/categorias')
  Conferir 'categorias do plano de contas inicial' $categorias.Count 17
  $aluguel = $categorias | Where-Object { $_.nome -eq 'Aluguel' }
  $conta = Pedir POST '/api/financeiro/lancamentos' @{ tipo = 'despesa'; categoria_id = $aluguel.id; descricao = 'Aluguel de teste'; valor_centavos = 1000; vencimento = $hoje; pago_em = $hoje; forma = 'pix' }
  Conferir 'despesa de teste lançada já paga' $conta.situacao 'pago'
  $fluxo = Pedir GET "/api/financeiro/fluxo?inicio=$hoje&fim=$hoje"
  Conferir 'fluxo de caixa de hoje (entrou; saiu; saldo, em centavos)' "$($fluxo.entradas_centavos);$($fluxo.pagamentos_centavos);$($fluxo.saldo_centavos)" '4395;1000;3395'
  $dre = Pedir GET "/api/financeiro/dre?inicio=$hoje&fim=$hoje"
  $linhas = @{}
  foreach ($linha in $dre.linhas) { if ($linha.chave) { $linhas[$linha.chave] = $linha.valor_centavos } }
  Conferir 'DRE de hoje (receita líquida; CMV; lucro bruto; resultado, em centavos)' "$($linhas.receita_liquida);$($linhas.cmv);$($linhas.lucro_bruto);$($linhas.resultado)" '4395;-2000;2395;1395'
  $rent = Pedir GET "/api/financeiro/rentabilidade?inicio=$hoje&fim=$hoje"
  Conferir 'rentabilidade do picolé (receita; custo; margem; %)' "$($rent.linhas[0].receita_centavos);$($rent.linhas[0].custo_centavos);$($rent.linhas[0].margem_centavos);$($rent.linhas[0].margem_percentual)" '4395;2000;2395;54,5%'

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

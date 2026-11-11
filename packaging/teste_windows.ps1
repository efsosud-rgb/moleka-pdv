# Testa o Moleka PDV empacotado, no Windows: sobe o servidor, confere as páginas e o login, faz
# uma venda de teste do começo ao fim (cadastro, caixa, duas formas de pagamento, fechamento),
# dá entrada numa nota fictícia por XML, confere estoque, custo, fluxo de caixa e DRE, grava as
# configurações, faz a cópia de segurança, imprime o cupom numa impressora de teste (só no GitHub
# Actions), abre a janela e tira um print da tela. Roda no GitHub Actions depois do PyInstaller e
# depois do instalador.
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
  $scripts = 'moleka', 'entrada', 'operadores', 'produtos', 'clientes', 'tabelas', 'controle_caixa', 'caixa', 'estoque', 'entrada_nf', 'financeiro', 'configuracoes' | ForEach-Object { "/static/js/$_.js" }
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
  foreach ($tela in 'inicio', 'caixa', 'controle-caixa', 'produtos', 'clientes', 'tabelas-preco', 'estoque', 'entrada-nf', 'financeiro', 'operadores', 'configuracoes') {
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

  # Configurações (versão 0.5.0): começam em branco, e os dados da loja ficam gravados.
  $cfg = Pedir GET '/api/configuracoes'
  Conferir 'configurações novas (loja em branco; sem impressora; 48 colunas; oferecer o botão)' "$($cfg.loja.nome_fantasia);$($cfg.impressao.impressora);$($cfg.impressao.colunas);$($cfg.impressao.quando)" ';;48;perguntar'
  $loja = @{ nome_fantasia = 'Sorveteria de Teste'; razao_social = 'Sorveteria de Teste Ltda'; cnpj = '11.222.333/0001-81'; ie = ''; logradouro = 'Rua das Flores'; numero = '100'; bairro = 'Centro'; cidade = 'São Paulo'; uf = 'SP'; cep = '01001-000'; telefone = ''; rodape = 'Obrigado pela preferência!' }
  $gravada = Pedir PUT '/api/configuracoes/loja' $loja
  Conferir 'dados da loja gravados (CNPJ e CEP só com os números; cidade com acento)' "$($gravada.cnpj);$($gravada.cep);$($gravada.cidade)" '11222333000181;01001000;São Paulo'

  # Cópia de segurança: a do dia é feita quando o programa abre; "fazer agora" refaz a cópia e
  # manda também para a pasta extra.
  $copiaDoDia = Join-Path $env:MOLEKA_PDV_DADOS "backups\moleka-$hoje.db"
  if (-not (Test-Path $copiaDoDia)) { throw "a cópia de segurança do dia não foi feita ao abrir o programa ($copiaDoDia)" }
  Write-Host "OK: a cópia de segurança do dia foi feita ao abrir o programa ($((Get-Item $copiaDoDia).Length) bytes)"
  $pastaExtra = Join-Path (Resolve-Path $Saida).Path "pasta-extra-$rotulo"
  if (Test-Path $pastaExtra) { Remove-Item -Recurse -Force $pastaExtra }
  New-Item -ItemType Directory -Force $pastaExtra | Out-Null
  $null = Pedir PUT '/api/configuracoes/backup' @{ pasta_extra = "$pastaExtra"; manter = 30 }
  $copia = Pedir POST '/api/backup'
  Conferir 'cópia de segurança feita agora (arquivo; erro da pasta extra)' "$($copia.copia.arquivo);$($copia.extra_erro)" "moleka-$hoje.db;"
  $naExtra = Join-Path $pastaExtra "moleka-$hoje.db"
  if (-not (Test-Path $naExtra)) { throw "a cópia de segurança não chegou à pasta extra ($naExtra)" }
  Conferir 'a cópia da pasta extra é um banco SQLite' ([Text.Encoding]::ASCII.GetString([IO.File]::ReadAllBytes($naExtra), 0, 15)) 'SQLite format 3'
  Conferir 'indicador da cópia de segurança, com as duas cópias feitas' (Pedir GET '/api/status').backup.ok 'True'
  $null = Pedir PUT '/api/configuracoes/backup' @{ pasta_extra = ''; manter = 30 }
  Remove-Item -Recurse -Force $pastaExtra   # a cópia de teste não precisa ir junto com os prints

  # Impressoras: a lista do sistema tem de ser a do Windows, lida aqui por outro caminho (WMI).
  $naNuvem = $env:GITHUB_ACTIONS -eq 'true'
  if ($naNuvem) { try { Set-Service Spooler -StartupType Manual; Start-Service Spooler } catch { Write-Host "Aviso: não liguei o serviço de impressão do Windows ($($_.Exception.Message))" } }
  $lista = Pedir GET '/api/impressoras'
  if (-not $lista.disponivel) {
    Write-Host "::warning::NAO VERIFICADO ($rotulo): o Windows não entregou a lista de impressoras ($($lista.motivo))"
  } else {
    $doSistema = (@($lista.impressoras | ForEach-Object { $_.nome }) | Sort-Object) -join ' | '
    $doWindows = (@(Get-CimInstance Win32_Printer | ForEach-Object { $_.Name }) | Sort-Object) -join ' | '
    Conferir 'impressoras instaladas: a lista do sistema é a mesma do Windows' $doSistema $doWindows
  }

  # Impressão de verdade pela fila do Windows. Só na máquina de teste do GitHub, porque aqui se
  # cria uma impressora de teste (num computador de uso este script nunca instala nada). A
  # impressora "Generic / Text Only" grava num arquivo exatamente os bytes que recebe.
  $impressaoConferida = $false
  if ($naNuvem -and $lista.disponivel) {
    $nomeDaImpressora = "Moleka Teste $rotulo"
    $arquivoDaFila = Join-Path (Resolve-Path $Saida).Path "impressora-$rotulo.prn"
    $criada = $false
    try {
      if (Test-Path $arquivoDaFila) { Remove-Item -Force $arquivoDaFila }
      if (-not (Get-PrinterDriver -Name 'Generic / Text Only' -ErrorAction SilentlyContinue)) { Add-PrinterDriver -Name 'Generic / Text Only' }
      if (-not (Get-PrinterPort -Name $arquivoDaFila -ErrorAction SilentlyContinue)) { Add-PrinterPort -Name $arquivoDaFila }
      if (-not (Get-Printer -Name $nomeDaImpressora -ErrorAction SilentlyContinue)) { Add-Printer -Name $nomeDaImpressora -DriverName 'Generic / Text Only' -PortName $arquivoDaFila }
      $criada = $true
    } catch {
      Write-Host "::warning::NAO VERIFICADO ($rotulo): não consegui criar a impressora de teste no Windows ($($_.Exception.Message))"
    }
    if ($criada) {
      try {
        function Esperar-Impresso([int]$Minimo = 100, [int]$Segundos = 40) {
          $limite = (Get-Date).AddSeconds($Segundos)
          while ((Get-Date) -lt $limite) {
            if ((Test-Path $arquivoDaFila) -and ((Get-Item $arquivoDaFila).Length -ge $Minimo)) {
              Start-Sleep -Milliseconds 800   # a fila pode ainda estar escrevendo
              try { return , [IO.File]::ReadAllBytes($arquivoDaFila) } catch { Start-Sleep -Milliseconds 300 }
            }
            Start-Sleep -Milliseconds 300
          }
          throw "a impressora de teste não gravou o arquivo em $Segundos s ($arquivoDaFila)"
        }
        function Limpar-Fila {
          for ($i = 0; $i -lt 20; $i++) {
            try { if (Test-Path $arquivoDaFila) { Remove-Item -Force $arquivoDaFila }; return } catch { Start-Sleep -Milliseconds 500 }
          }
          throw "não consegui apagar $arquivoDaFila para a impressão seguinte"
        }
        function Hex([byte[]]$Bytes) { return (($Bytes | ForEach-Object { $_.ToString('x2') }) -join '') }
        $latin1 = [Text.Encoding]::GetEncoding(28591)

        $lista = Pedir GET '/api/impressoras'
        if (@($lista.impressoras | Where-Object { $_.nome -eq $nomeDaImpressora }).Count -ne 1) { throw "a impressora de teste criada no Windows não apareceu na lista do sistema" }
        $opcoes = @{ impressora = $nomeDaImpressora; colunas = 48; acentos = 'cp850'; vias = 1; quando = 'sempre'; cortar = $true; gaveta = $true }
        $gravadas = Pedir PUT '/api/configuracoes/impressao' $opcoes
        Conferir 'impressora de cupom escolhida, ainda sem confirmação' "$($gravadas.impressora);$($gravadas.confirmada)" "$nomeDaImpressora;False"

        # 1) Página de teste: ESC @ + ESC t 2 no começo, "IMPRESSÃO" com Ã = C7 (página 850),
        #    a régua de 48 números e o corte do papel no fim.
        $null = Pedir POST '/api/impressao/teste'
        $bytes = Esperar-Impresso
        $hex = Hex $bytes
        if (-not $hex.StartsWith('1b401b7402')) { throw "a página de teste não começa com ESC @ e ESC t 2: $($hex.Substring(0, 20))" }
        if (-not $hex.EndsWith('1b45001d21001d564200')) { throw "a página de teste não termina com o corte do papel: $($hex.Substring($hex.Length - 24))" }
        if (-not $hex.Contains('494d5052455353c74f')) { throw 'a página de teste não traz "IMPRESSÃO" na página de código 850 (Ã = C7)' }
        if (-not $latin1.GetString($bytes).Contains('123456789012345678901234567890123456789012345678')) { throw 'a página de teste não traz a régua de 48 colunas' }
        Write-Host "OK: a página de teste passou pela fila do Windows e saiu na impressora de teste ($($bytes.Length) bytes conferidos)"
        $null = Pedir POST '/api/impressao/teste/confirmar' @{ saiu = $true }
        Conferir 'indicador da impressora de cupom depois da confirmação' (Pedir GET '/api/status').impressora_cupom.ok 'True'

        # 2) Reimpressão do comprovante da venda feita acima (total 43,95; troco 6,05).
        Limpar-Fila
        $null = Pedir POST "/api/vendas/$($venda.id)/imprimir"
        $bytes = Esperar-Impresso
        $texto = $latin1.GetString($bytes)
        foreach ($trecho in 'Sorveteria de Teste', 'CNPJ 11.222.333/0001-81', 'COMPROVANTE DE VENDA', 'TOTAL', '43,95', 'Troco', '6,05') {
          if (-not $texto.Contains($trecho)) { throw "o comprovante impresso não traz '$trecho'" }
        }
        if ((Hex $bytes).StartsWith('1b70')) { throw 'a reimpressão não deveria abrir a gaveta' }
        Write-Host "OK: comprovante da venda impresso pela fila do Windows ($($bytes.Length) bytes conferidos)"

        # 3) Venda nova em dinheiro com "imprimir sozinho" e gaveta: o pulso vem antes do comprovante.
        $null = Pedir POST '/api/caixa/abrir' @{ fundo_troco_centavos = 0 }
        Limpar-Fila
        $null = Pedir POST '/api/venda/itens' @{ codigo = '1'; quantidade = 1 }
        $null = Pedir POST '/api/venda/pagamentos' @{ forma = 'dinheiro'; valor_centavos = 500 }
        $fim = Pedir POST '/api/venda/finalizar' @{ emitir_nfce = $false }
        Conferir 'venda com "imprimir sozinho" (situação; comprovante enviado; erro)' "$($fim.venda.status);$($fim.depois.enviado);$($fim.depois.erro)" 'finalizada;True;'
        $bytes = Esperar-Impresso
        $hex = Hex $bytes
        if (-not $hex.StartsWith('1b700019fa1b401b7402')) { throw "na venda em dinheiro o pulso da gaveta deveria vir antes do comprovante: $($hex.Substring(0, 24))" }
        Write-Host 'OK: venda em dinheiro imprime sozinha, com o pulso da gaveta antes do comprovante'
        $null = Pedir PUT '/api/configuracoes/impressao' @{ impressora = ''; colunas = 48; acentos = 'cp850'; vias = 1; quando = 'perguntar'; cortar = $true; gaveta = $false }
        $impressaoConferida = $true
      }
      finally {
        Remove-Printer -Name $nomeDaImpressora -ErrorAction SilentlyContinue
        Remove-PrinterPort -Name $arquivoDaFila -ErrorAction SilentlyContinue
      }
    }
  }
  if ($impressaoConferida) { Write-Host "OK: impressão do cupom pela fila do Windows (RAW) CONFERIDA nesta máquina de teste ($rotulo)" }
  else { Write-Host "NAO VERIFICADO ($rotulo): impressão do cupom pela fila do Windows (sem impressora de teste nesta máquina)" }

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

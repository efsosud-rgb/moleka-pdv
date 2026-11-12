// Roteiro do relatório "Vendas por período" e dos botões "Excel" (relatório, Financeiro e
// Estoque), feito no navegador como um usuário faria, com os valores esperados calculados à mão
// (os mesmos de tests/test_relatorio_vendas.py; ver as contas nos comentários de lá).
//
// As vendas de preparação são feitas pela API, de dentro da página (a tela do caixa já tem o
// roteiro dela, vendas_no_navegador.js). Todas ficam no dia e na hora em que o roteiro roda;
// não rode perto da meia-noite.
//
// A planilha é baixada pelo navegador (no programa, a janela "Salvar como" do Windows é que
// grava; isso o navegador de teste NÃO mostra) e lida com o openpyxl do Python do projeto.
//
// Para rodar (precisa do Node.js com o pacote "playwright" e do Python do projeto):
//   1. suba o servidor com um banco NOVO:
//        MOLEKA_PDV_DADOS=/pasta/vazia python main.py --sem-janela --porta 8794
//   2. em outro terminal:
//        node tools/roteiros/relatorio_vendas_no_navegador.js 8794 /pasta/dos/prints
//
// Todos os dados daqui são fictícios, de teste, e as senhas são sorteadas a cada execução. O
// roteiro termina com código 0 quando tudo passa; os prints e as planilhas ficam na pasta dada.
const { chromium } = require('playwright');
const { execFileSync } = require('child_process');
const path = require('path'); const fs = require('fs'); const crypto = require('crypto');
const LARGURA = 1366, ALTURA = Number(process.argv[4] || 697);
const SEMANA = ['segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado', 'domingo'];

(async () => {
  const porta = process.argv[2]; const saida = path.resolve(process.argv[3]);
  fs.mkdirSync(saida, { recursive: true });
  const base = 'http://127.0.0.1:' + porta;
  const senhaGerente = 'g' + crypto.randomBytes(5).toString('hex');
  const senhaCaixa = String(1000 + crypto.randomInt(9000));
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: LARGURA, height: ALTURA }, locale: 'pt-BR', acceptDownloads: true });
  // A impressão do Windows não existe no navegador de teste: o roteiro conta as chamadas.
  await ctx.addInitScript(() => { window.__impressoes = 0; window.print = () => { window.__impressoes += 1; }; });
  const page = await ctx.newPage();
  const erros = [];
  const falhas = [];
  let passo = 0; let conferencias = 0;
  function vigiar(p) {
    p.on('pageerror', e => erros.push('pageerror: ' + e.message));
    // O navegador escreve no console toda resposta 4xx; as esperadas são conferidas no roteiro.
    p.on('console', m => { if (m.type() === 'error' && !/status of (401|403|404|409|422)/.test(m.text())) erros.push('console: ' + m.text()); });
    p.on('requestfailed', r => { if (!/\/static\/fonts\//.test(r.url())) erros.push('requestfailed: ' + r.url()); });
    p.on('response', r => { if (r.status() >= 500) erros.push(r.status() + ': ' + r.url()); });
  }
  vigiar(page);

  function confere(nome, ok, detalhe) { conferencias += 1; console.log((ok ? 'OK   ' : 'FALHA') + ' ' + nome + (detalhe !== undefined ? ' — ' + detalhe : '')); if (!ok) falhas.push(nome); }
  const LER = `(el) => { const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT); const p = []; while (w.nextNode()) p.push(w.currentNode.nodeValue); return p.join(' ').replace(/\\s+/g, ' ').trim(); }`;
  async function texto(sel, p) { return (p || page).evaluate(([s, ler]) => { const el = document.querySelector(s); return el ? eval(ler)(el) : '(sem elemento)'; }, [sel, LER]); }
  async function linhas(sel) { return page.evaluate(([s, ler]) => Array.from(document.querySelectorAll(s)).map(el => eval(ler)(el)), [sel, LER]); }
  async function espera(sel, regex, nome) {
    try {
      await page.waitForFunction(([s, fonte, flags, ler]) => { const el = document.querySelector(s); return !!el && new RegExp(fonte, flags).test(eval(ler)(el)); }, [sel, regex.source, regex.flags, LER], { timeout: 6000 });
      confere(nome, true, await texto(sel));
    } catch (e) { confere(nome, false, 'esperava ' + regex + ' e veio: ' + (await texto(sel).catch(() => '(sem elemento)'))); }
  }
  async function iguais(sel, esperado, nome) {
    const veio = await linhas(sel);
    confere(nome, JSON.stringify(veio) === JSON.stringify(esperado), JSON.stringify(veio));
  }
  async function foto(nome) {
    passo += 1;
    await page.waitForTimeout(350);
    await page.screenshot({ path: path.join(saida, String(passo).padStart(2, '0') + '-' + nome + '.png') });
  }
  async function medir(nome) {
    await page.waitForTimeout(300);
    const m = await page.evaluate(() => {
      const miolo = document.querySelector('.conteudo');
      return { h: document.documentElement.scrollHeight, w: document.documentElement.scrollWidth, mh: miolo ? miolo.scrollHeight - miolo.clientHeight : 0, mw: miolo ? miolo.scrollWidth - miolo.clientWidth : 0 };
    });
    confere('cabe em ' + LARGURA + 'x' + ALTURA + ' sem rolar a página: ' + nome, m.h <= ALTURA && m.w <= LARGURA && m.mh <= 0 && m.mw <= 0, 'página ' + m.w + 'x' + m.h + ', sobra do miolo ' + m.mw + 'x' + m.mh);
    await foto(nome);
  }
  // Uma tabela da tela não pode passar da largura do cartão (senão aparece rolagem de lado).
  async function semRolagemDeLado(sel, nome) {
    const m = await page.$eval(sel, el => { const r = el.closest('.rolagem') || el.parentElement; return [el.scrollWidth, r.clientWidth]; });
    confere(nome + ': a tabela cabe na largura do cartão', m[0] <= m[1], 'tabela ' + m[0] + ' px, espaço ' + m[1] + ' px');
  }
  const api = (metodo, caminho, corpo, p) => (p || page).evaluate(async ([m, c, d]) => {
    const r = await fetch(c, { method: m, headers: d ? { 'Content-Type': 'application/json' } : {}, body: d ? JSON.stringify(d) : undefined });
    let j = null; try { j = await r.json(); } catch (e) { j = null; }
    return { status: r.status, dados: j };
  }, [metodo, caminho, corpo || null]);
  async function pedir(metodo, caminho, corpo, p, esperado) {
    const r = await api(metodo, caminho, corpo, p);
    if (r.status !== (esperado || (metodo === 'POST' ? 201 : 200)) && !(metodo === 'POST' && r.status === 200)) throw new Error(metodo + ' ' + caminho + ': ' + r.status + ' ' + JSON.stringify(r.dados));
    return r.dados;
  }
  // Uma venda pela API: itens, pagamentos e finalização (como o caixa faria).
  async function vender(p, itens, pagamentos, desconto) {
    let venda = null;
    for (const [produto, quantidade] of itens) venda = (await pedir('POST', '/api/venda/itens', { produto_id: produto, quantidade: quantidade }, p)).venda;
    if (desconto) await pedir('PUT', '/api/venda/desconto', { centavos: desconto }, p);
    for (const pg of pagamentos) await pedir('POST', '/api/venda/pagamentos', pg, p);
    const fim = await pedir('POST', '/api/venda/finalizar', {}, p, 200);
    return fim.venda || venda;
  }
  // Baixa a planilha do botão Excel e devolve o caminho do arquivo.
  async function baixar(nome) {
    try {
      const [d] = await Promise.all([page.waitForEvent('download', { timeout: 15000 }), page.click('#btn-excel')]);
      const arquivo = path.join(saida, d.suggestedFilename());
      await d.saveAs(arquivo);
      confere(nome + ': a planilha foi baixada', fs.statSync(arquivo).size > 1000, d.suggestedFilename());
      return arquivo;
    } catch (e) { confere(nome + ': a planilha foi baixada', false, e.message); return null; }
  }
  // Lê uma célula da planilha: a coluna `coluna` (1 = A) da linha cuja coluna A é `rotulo`.
  function lerPlanilha(arquivo, aba, rotulo, coluna) {
    const codigo = 'import sys, openpyxl\nl = openpyxl.load_workbook(sys.argv[1])\nprint(l.sheetnames)\nfor linha in l[sys.argv[2]].iter_rows(values_only=True):\n    if linha and linha[0] == sys.argv[3]:\n        print(linha[int(sys.argv[4]) - 1]); break\nelse:\n    print("(sem a linha)")';
    const saidaPy = execFileSync(process.env.PYTHON || 'python3', ['-c', codigo, arquivo, aba, rotulo, String(coluna)]).toString('utf8').trim().split('\n');
    return { abas: saidaPy[0], valor: saidaPy[1] };
  }

  // ------------------------------------------------------------------ 1) preparação
  await page.goto(base + '/');
  await page.fill('#ci-nome', 'Gerente de Teste');
  await page.fill('#ci-senha', senhaGerente); await page.fill('#ci-senha2', senhaGerente);
  await page.keyboard.press('Enter');
  await page.waitForURL(base + '/inicio');
  const agora = (await api('GET', '/api/status')).dados.agora; // "2026-11-12T10:45:00-03:00"
  const hoje = agora.slice(0, 10);
  const br = iso => iso.slice(8, 10) + '/' + iso.slice(5, 7) + '/' + iso.slice(0, 4);
  const traco = iso => iso.slice(8, 10) + '-' + iso.slice(5, 7) + '-' + iso.slice(0, 4);
  const varejo = (await api('GET', '/api/tabelas-preco')).dados.find(t => t.padrao).id;
  const picole = (await pedir('POST', '/api/produtos', { codigo: '1', descricao: 'Picolé de teste', precos: [{ tabela_id: varejo, qtd_min: '1', preco_centavos: 500 }, { tabela_id: varejo, qtd_min: '10', preco_centavos: 450 }] })).id;
  const sorvete = (await pedir('POST', '/api/produtos', { codigo: '2', descricao: 'Sorvete de teste por quilo', unidade: 'kg', precos: [{ tabela_id: varejo, qtd_min: '1', preco_centavos: 5990 }] })).id;
  const agua = (await pedir('POST', '/api/produtos', { codigo: '3', descricao: 'Água de teste', precos: [{ tabela_id: varejo, qtd_min: '1', preco_centavos: 300 }] })).id;
  await pedir('PUT', '/api/formas-pagamento/pix', { ajuste_bp: -500, ativo: true });
  await pedir('PUT', '/api/formas-pagamento/credito', { ajuste_bp: 300, ativo: true });
  await pedir('POST', '/api/operadores', { nome: 'Caixa de Teste', login: 'caixa', senha: senhaCaixa, perfil: 'operador' });
  await pedir('POST', '/api/caixa/abrir', { fundo_troco_centavos: 10000 });
  // Gerente: vendas 1, 2, 3 e a 4, que é cancelada depois de finalizada.
  await vender(page, [[picole, 4]], [{ forma: 'dinheiro' }]); //                              20,00
  await vender(page, [[picole, 10], [sorvete, '0.5']], [{ forma: 'pix' }], 495); //            66,50
  await vender(page, [[picole, 2]], [{ forma: 'credito' }]); //                               10,30
  const v4 = await vender(page, [[picole, 1]], [{ forma: 'dinheiro' }]); //                     5,00
  await pedir('POST', '/api/vendas/' + v4.id + '/cancelar', { motivo: 'lançada em dobro' }, page, 200);
  // Caixa (outra janela): a venda 5, paga em duas formas, e a 6, cancelada antes de finalizar.
  const ctxCaixa = await b.newContext({ viewport: { width: LARGURA, height: ALTURA }, locale: 'pt-BR' });
  const caixa = await ctxCaixa.newPage();
  vigiar(caixa);
  await caixa.goto(base + '/');
  await caixa.selectOption('#lg-operador', 'caixa');
  await caixa.fill('#lg-senha', senhaCaixa);
  await caixa.keyboard.press('Enter');
  await caixa.waitForURL(base + '/inicio');
  await vender(caixa, [[agua, 2], [picole, 1]], [{ forma: 'dinheiro', valor_centavos: 500 }, { forma: 'pix' }]); // 10,70
  await pedir('POST', '/api/venda/itens', { produto_id: sorvete, quantidade: '1' }, caixa);
  await pedir('POST', '/api/venda/cancelar', { motivo: 'cliente desistiu' }, caixa, 200);
  const horaDasVendas = Number((await api('GET', '/api/status')).dados.agora.slice(11, 13));
  const diaDaSemana = (new Date(Number(hoje.slice(0, 4)), Number(hoje.slice(5, 7)) - 1, Number(hoje.slice(8, 10))).getDay() + 6) % 7;

  // ------------------------------------------------------------------ 2) caminho até a tela
  await page.goto(base + '/inicio');
  confere('Início: o bloco Relatórios leva ao relatório de vendas', (await page.getAttribute('.grade a.tile[href="/relatorios/vendas"]', 'href')) === '/relatorios/vendas');
  await page.click('.menubar .menu-botao:has-text("Relatórios")');
  await page.click('.submenu a[href="/relatorios/vendas"]');
  await page.waitForURL(base + '/relatorios/vendas');
  confere('menu Relatórios → Vendas por período abre a tela', true, page.url());
  await espera('[data-faixa]', new RegExp('^01/' + hoje.slice(5, 7) + '/' + hoje.slice(0, 4) + '( a ' + br(hoje) + ')?$'), 'o período começa em "Este mês", do dia 1 até hoje');
  await page.selectOption('#periodo', 'hoje');
  await espera('[data-faixa]', new RegExp('^' + br(hoje) + '$'), 'Hoje: a faixa mostra a data de hoje');

  // ------------------------------------------------------------------ 3) resumo
  await espera('[data-k="faturamento"]', /^R\$ 107,50$/, 'faturamento: 20,00 + 66,50 + 10,30 + 10,70 = 107,50');
  await espera('[data-k="faturamento_m"]', /^4 vendas finalizadas$/, 'quatro vendas finalizadas (canceladas não contam)');
  await espera('[data-k="ticket"]', /^R\$ 26,88$/, 'ticket médio: 107,50 ÷ 4 = 26,875 → 26,88');
  await espera('[data-k="descontos"]', /^R\$ 8,75$/, 'descontos: 4,95 do gerente + 3,80 do Pix = 8,75');
  await espera('[data-k="descontos_m"]', /^gerente R\$ 4,95 · formas R\$ 3,80 · acréscimos R\$ 0,30$/, 'descontos separados, com o acréscimo do crédito');
  await espera('[data-k="canceladas"]', /^2$/, 'duas vendas canceladas');
  await espera('[data-k="canceladas_m"]', /^1 antes de finalizar \(R\$ 59,90\) · 1 depois \(R\$ 5,00\)$/, 'canceladas antes e depois de finalizar, com os valores');
  await espera('[data-k="sem_nfce"]', /^4$/, 'as 4 vendas estão sem NFC-e');
  await espera('[data-k="sem_nfce_m"]', /^R\$ 107,50 · o sistema ainda não emite NFC-e$/, 'o cartão da NFC-e diz o motivo');
  await iguais('#tabela-formas tbody tr', [
    'Dinheiro 2 vendas 25,00 23,3%', //                 20,00 + 5,00
    'Pix 2 vendas 72,20 desconto 3,80 67,2%', //        66,50 + 5,70; desconto 3,50 + 0,30
    'Débito nenhuma venda — —',
    'Crédito 1 venda 10,30 acréscimo 0,30 9,6%',
    'Total 107,50',
  ], 'formas de pagamento: valores, desconto e acréscimo de cada forma');
  await semRolagemDeLado('#tabela-formas', 'formas de pagamento');
  await espera('[data-graf-titulo]', /^Vendas por hora$/, 'um dia só: o gráfico mostra as horas');
  const barras = await page.$$eval('.area-graf .graf-barra', els => els.length);
  confere('o gráfico tem uma barra por hora com venda', barras >= 1 && barras <= 2, barras + ' barra(s)');
  await espera('.area-graf .graf-rotulo', /^R\$ \d/, 'o maior valor vem escrito em cima da barra');
  await page.focus('.area-graf');
  await espera('[data-dica-graf]', /venda/, 'pelo teclado: o gráfico mostra a dica da barra');
  await page.evaluate(() => document.activeElement.blur());
  confere('saindo do gráfico, a dica some', await page.$eval('[data-dica-graf]', el => el.hidden));
  await medir('resumo-hoje');
  await page.click('[data-ver="tabela"]');
  await espera('#tabela-graf tbody tr.forte', /^Total 4 107,50 26,88$/, 'a tabela do gráfico tem o total do dia');
  await foto('resumo-tabela');
  await page.click('[data-ver="grafico"]');

  // ------------------------------------------------------------------ 4) produtos (curva ABC)
  await page.click('[data-aba="produtos"]');
  await espera('[data-c="A"]', /^2 produtos$/, 'classe A: picolé e sorvete');
  await espera('[data-c="A_m"]', /^94,6% do faturamento · R\$ 101,66$/, 'classe A: 75,09 + 26,57 = 101,66 (94,6%)');
  await espera('[data-c="B"]', /^1 produto$/, 'classe B: a água');
  await espera('[data-c="C_m"]', /^nenhum produto nesta classe$/, 'classe C vazia diz o motivo');
  await iguais('#tabela-produtos tbody tr', [
    '1 1 Picolé de teste 17 UN 4 75,09 69,9% 69,9% A',
    '2 2 Sorvete de teste por quilo 0,500 KG 1 26,57 24,7% 94,6% A',
    '3 3 Água de teste 2 UN 1 5,84 5,4% 100,0% B',
    'Total 107,50',
  ], 'produtos: o valor de cada venda dividido entre os itens, e a classe ABC');
  await medir('produtos');
  await page.keyboard.press('Control+p');
  await page.waitForFunction(() => window.__impressoes === 1).catch(() => {});
  confere('Ctrl+P na aba Produtos chama a impressão do Windows uma vez', await page.evaluate(() => window.__impressoes) === 1);
  await espera('#impressao h1', /^Vendas por produto \(curva ABC\)$/, 'a folha impressa tem o título da aba');
  await espera('#impressao .imp-detalhe', /^Período: /, 'a folha impressa tem o período');
  confere('a folha impressa tem a tabela dos produtos', (await page.$$eval('#impressao table tbody tr', trs => trs.length)) === 4);

  // ------------------------------------------------------------------ 5) horários
  await page.click('[data-aba="horarios"]');
  await espera('[data-pico]', new RegExp('^Maior movimento: ' + SEMANA[diaDaSemana] + ', \\d{1,2}h — R\\$ [\\d.,]+ em \\d+ vendas?$'), 'horários: o maior movimento diz o dia, a hora e o valor');
  const quantos = (await linhas('.mapa .dia small')).join(' ');
  confere('horários: cada linha diz quantos dias daquela semana o período tem (só hoje: 1)', quantos === SEMANA.map((_, i) => i === diaDaSemana ? '(1)' : '(0)').join(' '), quantos);
  confere('horários: só os quadrados com venda têm cor', (await page.$$eval('.mapa .cel:not(.n0)', els => els.length)) >= 1 && (await page.$$eval('.mapa .cel:not(.n0)', els => els.length)) <= 2);
  await medir('horarios');
  await page.click('[data-medida="vendas"]');
  await espera('[data-legenda]', /o mais escuro chega a \d+\)$/, 'medida "Nº de vendas": a legenda passa a contar vendas');
  await page.click('[data-ver-mapa="tabela"]');
  await espera('#tabela-horarios tbody tr.forte', /^Total( \d+)+ 4$/, 'tabela dos horários (vendas): o total é 4');
  await page.click('[data-medida="faturamento"]');
  await espera('#tabela-horarios tbody tr.forte', /^Total .*R\$ 107,50$/, 'tabela dos horários (R$): o total é o faturamento');
  await page.click('[data-ver-mapa="grafico"]');

  // ------------------------------------------------------------------ 6) operadores
  await page.click('[data-aba="operadores"]');
  await iguais('#tabela-operadores tbody tr', [
    'Gerente de Teste 3 96,80 32,27 90,0% 4,95 0 1 5,00', //  96,80 ÷ 3 = 32,266…
    'Caixa de Teste 1 10,70 10,70 10,0% 0,00 1 0 59,90',
  ], 'operadores: vendas, faturamento, desconto e cancelamentos de cada um');
  await semRolagemDeLado('#tabela-operadores', 'operadores');
  await medir('operadores');

  // ------------------------------------------------------------------ 7) lista de vendas
  await page.click('[data-aba="vendas"]');
  await espera('[data-vd-contagem]', new RegExp('^4 finalizadas, R\\$ 107,50 · 2 canceladas · ' + br(hoje) + '$'), 'lista: quatro finalizadas e duas canceladas');
  confere('lista: seis linhas, da mais nova para a mais velha', (await linhas('#tabela-lista tbody tr td:first-child')).join(' ') === '6 5 4 3 2 1', (await linhas('#tabela-lista tbody tr td:first-child')).join(' '));
  await semRolagemDeLado('#tabela-lista', 'lista de vendas');
  await medir('lista-de-vendas');
  await page.selectOption('#vd-situacao', 'canceladas');
  await espera('[data-vd-contagem]', /^2 canceladas · /, 'filtro "Só as canceladas"');
  await iguais('#tabela-lista tbody tr td:nth-child(3)', [
    'Cancelada antes de finalizar · por Caixa de Teste · “cliente desistiu”',
    'Cancelada depois de finalizada, em ' + br(hoje) + ' ' + (await texto('#tabela-lista tbody tr:nth-child(2) td:nth-child(3) .sub')).replace(/^.*em \d\d\/\d\d\/\d{4} (\d\d:\d\d).*$/, '$1') + ' · por Gerente de Teste · “lançada em dobro”',
  ], 'canceladas: quando, quem e o motivo');
  await page.click('#tabela-lista tbody tr:nth-child(2) button');
  await page.waitForSelector('#dlg-cupom[open]');
  confere('o comprovante da venda estornada sai marcado como cancelado', /\*\*\* VENDA CANCELADA \*\*\*/.test(await texto('#dlg-cupom [data-cupom]')));
  await foto('comprovante-da-cancelada');
  await page.keyboard.press('Escape');
  await page.selectOption('#vd-situacao', '');

  // ------------------------------------------------------------------ 8) filtro de operador e Excel
  await page.selectOption('#operador', { label: 'Caixa de Teste' });
  await espera('[data-vd-contagem]', new RegExp('^1 finalizada, R\\$ 10,70 · 1 cancelada · '), 'operador Caixa: a lista fica só com as vendas dele');
  await page.click('[data-aba="resumo"]');
  await espera('[data-k="faturamento"]', /^R\$ 10,70$/, 'operador Caixa: faturamento só da venda 5');
  const doCaixa = await baixar('relatório do operador Caixa');
  if (doCaixa) {
    confere('o nome do arquivo diz o operador e o dia', path.basename(doCaixa) === 'Moleka - Vendas (Caixa de Teste) ' + traco(hoje) + '.xlsx', path.basename(doCaixa));
    const lido = lerPlanilha(doCaixa, 'Resumo', 'Faturamento', 2);
    confere('a planilha do Caixa tem o mesmo faturamento da tela (10,70)', Number(lido.valor) === 10.7, lido.valor);
  }
  await page.selectOption('#operador', '');
  await espera('[data-k="faturamento"]', /^R\$ 107,50$/, 'todos os operadores de novo');
  const geral = await baixar('relatório geral');
  if (geral) {
    confere('o nome do arquivo geral', path.basename(geral) === 'Moleka - Vendas ' + traco(hoje) + '.xlsx', path.basename(geral));
    const lido = lerPlanilha(geral, 'Resumo', 'Faturamento', 2);
    confere('a planilha geral tem o faturamento da tela (107,50)', Number(lido.valor) === 107.5, lido.valor);
    confere('a planilha tem as abas do relatório', lido.abas === "['Resumo', 'Por dia', 'Formas de pagamento', 'Operadores', 'Produtos', 'Horários (R$)', 'Horários (vendas)', 'Lista de vendas']", lido.abas);
    const classe = lerPlanilha(geral, 'Produtos', '3', 9);
    confere('na planilha, a água é classe B', classe.valor === 'B', classe.valor);
  }

  // ------------------------------------------------------------------ 9) Excel do Financeiro e do Estoque
  await page.goto(base + '/financeiro#dre');
  await page.waitForSelector('#tabela-dre tbody tr:not(:has(.sem-linhas))');
  const dre = await baixar('DRE');
  if (dre) {
    // Receita bruta 116,25 (itens 115,95 + acréscimo 0,30) - descontos 8,75 = 107,50.
    const lido = lerPlanilha(dre, 'DRE', '= Receita líquida', 2);
    confere('DRE: a receita líquida da planilha é o faturamento do relatório (107,50)', lido.abas === "['DRE']" && Number(lido.valor) === 107.5, lido.abas + ' ' + lido.valor);
  }
  await page.goto(base + '/financeiro#rentabilidade');
  await page.waitForTimeout(600);
  const rent = await baixar('rentabilidade');
  if (rent) confere('rentabilidade: o nome do arquivo', /^Moleka - Rentabilidade \d\d-\d\d-\d{4} a \d\d-\d\d-\d{4}\.xlsx$/.test(path.basename(rent)), path.basename(rent));
  await page.goto(base + '/financeiro#categorias');
  await page.waitForTimeout(400);
  confere('Categorias não tem botão Excel (não é relatório)', !(await page.isVisible('#btn-excel')));
  await page.goto(base + '/estoque');
  await page.waitForTimeout(600);
  await page.fill('#busca', 'picolé');
  await page.waitForTimeout(700);
  const estoque = await baixar('estoque com a pesquisa "picolé"');
  if (estoque) {
    confere('estoque: o nome do arquivo', path.basename(estoque) === 'Moleka - Estoque ' + traco(hoje) + '.xlsx', path.basename(estoque));
    const lido = lerPlanilha(estoque, 'Estoque', '1', 2);
    confere('estoque: a planilha traz o picolé da pesquisa', lido.valor === 'Picolé de teste', lido.valor);
  }
  await medir('estoque-com-excel');

  // ------------------------------------------------------------------ 10) operador comum
  await caixa.goto(base + '/relatorios/vendas');
  confere('operador comum não abre o relatório de vendas', new URL(caixa.url()).pathname === '/inicio', caixa.url());
  for (const caminho of ['/api/relatorios/vendas', '/api/relatorios/vendas/lista', '/api/planilhas/vendas', '/api/planilhas/estoque']) {
    const r = await api('GET', caminho, null, caixa);
    confere('operador comum não usa ' + caminho, r.status === 403, r.status);
  }

  await b.close();
  console.log('');
  console.log(conferencias + ' conferências.');
  console.log(erros.length ? 'ERROS DO NAVEGADOR:\n' + erros.join('\n') : 'Nenhum erro de JavaScript, de rede ou do servidor (5xx).');
  console.log(falhas.length ? 'FALHAS (' + falhas.length + '): ' + falhas.join(' | ') : 'Todas as conferências passaram.');
  process.exit(falhas.length || erros.length ? 1 : 0);
})().catch(e => { console.error('ROTEIRO INTERROMPIDO: ' + e.message); process.exit(2); });

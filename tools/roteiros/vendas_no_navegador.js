// Roteiro das telas de cadastros, controle de caixa e venda, feito no navegador como um usuário
// faria: 128 conferências, com os valores esperados calculados à mão (ver os comentários).
//
// Para rodar (precisa do Node.js com o pacote "playwright"; não é dependência do programa):
//   1. suba o servidor com um banco NOVO, numa pasta vazia:
//        MOLEKA_PDV_DADOS=/caminho/de/uma/pasta/vazia python main.py --sem-janela --porta 8792
//   2. em outro terminal:
//        node tools/roteiros/vendas_no_navegador.js 8792 /caminho/para/os/prints
//      (um terceiro número muda a altura da janela; o padrão é 697, a área útil de 1366x768)
//
// Todos os dados daqui são fictícios, de teste, e as senhas são sorteadas a cada execução.
// O roteiro termina com código 0 quando tudo passa; os prints de cada tela ficam na pasta dada.
const { chromium } = require('playwright');
const path = require('path'); const fs = require('fs'); const crypto = require('crypto');
const LARGURA = 1366, ALTURA = Number(process.argv[4] || 697); // área útil da janela maximizada em 1366x768

(async () => {
  const porta = process.argv[2]; const saida = path.resolve(process.argv[3]);
  fs.mkdirSync(saida, { recursive: true });
  const base = 'http://127.0.0.1:' + porta;
  const senhaGerente = 'g' + crypto.randomBytes(5).toString('hex');
  const senhaCaixa = String(1000 + crypto.randomInt(9000));
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: LARGURA, height: ALTURA } });
  let page = await ctx.newPage();
  const erros = [];
  const falhas = [];
  let passo = 0;
  function vigiar(p) {
    p.on('pageerror', e => erros.push('pageerror: ' + e.message));
    // O navegador escreve no console toda resposta 4xx; as esperadas são conferidas no roteiro.
    p.on('console', m => { if (m.type() === 'error' && !/status of (401|403|404|409|422)/.test(m.text())) erros.push('console: ' + m.text()); });
    p.on('requestfailed', r => erros.push('requestfailed: ' + r.url()));
    p.on('response', r => { if (r.status() >= 500) erros.push(r.status() + ': ' + r.url()); });
  }
  vigiar(page);
  function confere(nome, ok, detalhe) { console.log((ok ? 'OK   ' : 'FALHA') + ' ' + nome + (detalhe !== undefined ? ' — ' + detalhe : '')); if (!ok) falhas.push(nome); }
  const LER = `(el) => { const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT); const p = []; while (w.nextNode()) p.push(w.currentNode.nodeValue); return p.join(' ').replace(/\\s+/g, ' ').trim(); }`;
  async function texto(sel) { return page.evaluate(([s, ler]) => { const el = document.querySelector(s); return el ? eval(ler)(el) : '(sem elemento)'; }, [sel, LER]); }
  async function espera(sel, regex, nome) {
    try {
      await page.waitForFunction(([s, fonte, flags, ler]) => { const el = document.querySelector(s); return !!el && new RegExp(fonte, flags).test(eval(ler)(el)); }, [sel, regex.source, regex.flags, LER], { timeout: 5000 });
      confere(nome, true, await texto(sel));
    } catch (e) { confere(nome, false, 'esperava ' + regex + ' e veio: ' + (await texto(sel).catch(() => '(sem elemento)'))); }
  }
  async function torrada(regex, nome) { await espera('.torrada.visivel', regex, nome); }
  async function foto(nome) {
    passo += 1;
    await page.waitForTimeout(350);
    await page.screenshot({ path: path.join(saida, String(passo).padStart(2, '0') + '-' + nome + '.png') });
  }
  async function medir(nome) {
    await page.waitForTimeout(300);
    const m = await page.evaluate(() => {
      const miolo = document.querySelector('.conteudo, .pdv, .capa');
      const ficha = document.querySelector('.cad .ficha');
      return { h: document.documentElement.scrollHeight, w: document.documentElement.scrollWidth, mh: miolo ? miolo.scrollHeight - miolo.clientHeight : 0, mw: miolo ? miolo.scrollWidth - miolo.clientWidth : 0, fh: ficha ? ficha.scrollHeight - ficha.clientHeight : 0 };
    });
    confere('cabe em ' + LARGURA + 'x' + ALTURA + ' sem rolar: ' + nome, m.h <= ALTURA && m.w <= LARGURA && m.mh <= 0 && m.mw <= 0, 'página ' + m.w + 'x' + m.h + ', sobra do miolo ' + m.mw + 'x' + m.mh + (m.fh > 0 ? ' (a ficha rola ' + m.fh + ' px por dentro)' : ''));
    await foto(nome);
  }
  const api = (metodo, caminho, corpo) => page.evaluate(async ([m, c, d]) => {
    const r = await fetch(c, { method: m, headers: d ? { 'Content-Type': 'application/json' } : {}, body: d ? JSON.stringify(d) : undefined });
    let j = null; try { j = await r.json(); } catch (e) { j = null; }
    return { status: r.status, dados: j };
  }, [metodo, caminho, corpo || null]);

  // ------------------------------------------------------------------ 1) primeiro acesso (gerente)
  await page.goto(base + '/');
  await page.fill('#ci-nome', 'Gerente de Teste');
  await page.fill('#ci-senha', senhaGerente); await page.fill('#ci-senha2', senhaGerente);
  await page.keyboard.press('Enter');
  await page.waitForURL(base + '/inicio');
  await espera('[data-status="caixa"] .texto', /^Caixa: fechado$/, 'Início: indicador do caixa diz "fechado"');
  await espera('[data-resumo="total"]', /^—$/, 'Início: vendas de hoje sem número inventado');
  await espera('[data-resumo-motivo]', /sem vendas finalizadas hoje/, 'Início: diz o motivo de não haver número');
  await medir('inicio-sem-vendas');

  // ------------------------------------------------------------------ 2) PDV com o caixa fechado
  await page.keyboard.press('F2');
  await page.waitForURL(base + '/caixa');
  await page.waitForSelector('#aviso-fechado', { state: 'visible' });
  await espera('#aviso-fechado', /O caixa está fechado/, 'PDV: avisa que o caixa está fechado');
  confere('PDV fechado: campo de produto desligado', await page.isDisabled('#prod'));
  await medir('pdv-caixa-fechado');

  // ------------------------------------------------------------------ 3) tabelas de preço e formas de pagamento
  await page.goto(base + '/tabelas-preco');
  await page.waitForSelector('#tabela-tabelas tbody tr:not(:has(.sem-linhas))');
  const nomes = await page.$$eval('#tabela-tabelas tbody tr td:first-child', tds => tds.map(td => td.textContent));
  confere('tabelas VAREJO e ATACADO já vêm criadas', nomes.join(',') === 'VAREJO,ATACADO', nomes.join(','));
  await page.waitForSelector('#tabela-formas tbody tr:nth-child(4) input[type=text]');
  async function forma(linha, pct) {
    const tr = '#tabela-formas tbody tr:nth-child(' + linha + ')';
    await page.fill(tr + ' input[type=text]', pct);
    await page.click(tr + ' button');
  }
  await forma(2, '-5'); await torrada(/Pix: -5%/, 'Pix com 5% de desconto');
  await forma(4, '3'); await torrada(/Crédito: \+3%/, 'Crédito com 3% de acréscimo');
  await forma(3, '80'); await espera('#msg-formas', /-50% a \+50%/, 'percentual absurdo (80%) é recusado');
  await page.reload(); await page.waitForSelector('#tabela-formas tbody tr:nth-child(4) input[type=text]');
  const pcts = await page.$$eval('#tabela-formas tbody tr input[type=text]', is => is.map(i => i.value));
  confere('percentuais ficaram gravados', pcts.join(' | ') === '0 | -5 | 0 | 3', pcts.join(' | '));
  await medir('tabelas-e-formas');

  // ------------------------------------------------------------------ 4) produtos
  await page.keyboard.press('F5');
  await page.waitForURL(base + '/produtos');
  await page.waitForSelector('#tabela-precos tbody tr:nth-child(2)');
  async function preco(linha, tabela, qtd, valor) {
    const tr = '#tabela-precos tbody tr:nth-child(' + linha + ')';
    await page.selectOption(tr + ' select', { label: tabela });
    await page.fill(tr + ' td:nth-child(2) input', qtd);
    await page.fill(tr + ' td:nth-child(3) input', valor);
  }
  // Picolé: varejo 5,00 (a partir de 1) e 4,50 (a partir de 10); atacado 4,00.
  await page.fill('#p-descricao', 'Picolé de teste');
  await page.fill('#p-ean', '7890000000017');
  await page.fill('#p-categoria', 'Picolés de teste');
  await preco(1, 'VAREJO', '1', '5,00');
  await preco(2, 'ATACADO', '1', '4,00');
  await page.click('[data-nova-faixa]');
  await preco(3, 'VAREJO', '10', '4,50');
  await foto('produto-ficha-preenchida');
  await page.keyboard.press('F10');
  await torrada(/Picolé de teste cadastrado \(código 1\)/, 'produto 1 cadastrado, com código automático');
  // Sorvete por quilo: varejo 59,90.
  await page.fill('#p-descricao', 'Sorvete de teste por quilo');
  await page.selectOption('#p-unidade', 'KG');
  await preco(1, 'VAREJO', '1', '59,90');
  await page.click('#form-produto button[type=submit]');
  await torrada(/Sorvete de teste por quilo cadastrado \(código 2\)/, 'produto 2 (por quilo) cadastrado');
  // Água: varejo 3,00.
  await page.fill('#p-descricao', 'Água de teste');
  await preco(1, 'VAREJO', '1', '3,00');
  await page.click('#form-produto button[type=submit]');
  await torrada(/Água de teste cadastrado \(código 3\)/, 'produto 3 cadastrado');
  // Erro: faixa a partir de 10 sem a faixa a partir de 1.
  await page.fill('#p-descricao', 'Produto errado de teste');
  await preco(1, 'VAREJO', '10', '1,00');
  await page.click('#form-produto button[type=submit]');
  await espera('#form-produto .msg-form', /falta o preço a partir de 1/, 'faixa sem o preço a partir de 1 é recusada');
  await page.click('[data-limpar]');
  await page.waitForFunction(() => document.querySelectorAll('#tabela-produtos tbody tr').length === 3);
  const lista = await page.$$eval('#tabela-produtos tbody tr', trs => trs.map(tr => tr.children[1].childNodes[0].textContent + ' ' + tr.children[2].textContent));
  confere('lista em ordem alfabética, com o preço de varejo', lista.join(' | ') === 'Água de teste 3,00 | Picolé de teste 5,00 | Sorvete de teste por quilo 59,90', lista.join(' | '));
  await page.fill('#busca', 'agua'); await page.waitForTimeout(500);
  confere('pesquisa "agua" acha "Água"', (await page.$$eval('#tabela-produtos tbody tr', t => t.length)) === 1 && /Água de teste/.test(await texto('#tabela-produtos tbody')));
  await page.fill('#busca', '');
  await page.waitForTimeout(500);
  await page.click('#tabela-produtos tbody tr:nth-child(2) button');
  await espera('#t-ficha', /Alterar produto/, 'abrir um produto para alterar');
  confere('ficha traz as 3 faixas de preço do picolé', (await page.$$eval('#tabela-precos tbody tr', t => t.length)) === 3);
  await medir('produtos');
  await page.click('[data-limpar]');

  // ------------------------------------------------------------------ 5) clientes
  await page.goto(base + '/clientes');
  await page.waitForSelector('#c-tabela option:nth-child(2)', { state: 'attached' });
  confere('opção padrão mostra o nome da tabela', /VAREJO \(padrão da loja\)/.test(await texto('#c-tabela option:first-child')), await texto('#c-tabela option:first-child'));
  await page.fill('#c-nome', 'Maria de Teste');
  await page.fill('#c-doc', '111.111.111-11');
  await page.click('#form-cliente button[type=submit]');
  await espera('#form-cliente .msg-form', /CPF ou CNPJ inválido/, 'CPF com dígitos errados é recusado');
  await page.fill('#c-doc', '529.982.247-25'); // CPF de teste, gerado pela regra dos dígitos
  await page.click('#form-cliente button[type=submit]');
  await torrada(/Cliente Maria de Teste cadastrado/, 'cliente com CPF cadastrado');
  await page.fill('#c-nome', 'Mercado Atacado de Teste');
  await page.fill('#c-doc', '11.222.333/0001-81'); // CNPJ de teste
  await page.selectOption('#c-tabela', { label: 'ATACADO' });
  await page.keyboard.press('F10');
  await torrada(/Cliente Mercado Atacado de Teste cadastrado/, 'cliente com CNPJ e tabela ATACADO cadastrado');
  await page.waitForFunction(() => document.querySelectorAll('#tabela-clientes tbody tr').length === 2);
  const cls = await page.$$eval('#tabela-clientes tbody tr', trs => trs.map(tr => [tr.children[0].childNodes[0].textContent, tr.children[1].textContent, tr.children[2].textContent].join(' ; ')));
  confere('lista de clientes com documento e tabela', cls.join(' | ') === 'Maria de Teste ; 529.982.247-25 ; VAREJO | Mercado Atacado de Teste ; 11.222.333/0001-81 ; ATACADO', cls.join(' | '));
  await medir('clientes');

  // ------------------------------------------------------------------ 6) controle de caixa: abrir, suprimento, sangria
  await page.keyboard.press('F11');
  await page.waitForURL(base + '/controle-caixa');
  await page.waitForSelector('#form-abrir', { state: 'visible' });
  await medir('controle-caixa-fechado');
  await page.keyboard.press('F10');
  await espera('#form-abrir .msg-form', /Digite o fundo de troco/, 'abrir sem fundo de troco pede o valor');
  await page.fill('#cx-fundo', '100,00');
  await page.keyboard.press('Enter');
  await torrada(/Caixa aberto com fundo de troco de R\$ 100,00/, 'caixa aberto com fundo de R$ 100,00');
  await espera('[data-cx="dinheiro_esperado"]', /^R\$ 100,00$/, 'dinheiro esperado = fundo');
  await espera('[data-cx="vendas_total"]', /^—$/, 'total vendido sem número inventado');
  await espera('[data-status="caixa"] .texto', /^Caixa: Caixa 01 · aberto \d\d:\d\d$/, 'indicador do topo mudou para aberto');
  async function movimento(tipo, valor, motivo) {
    await page.selectOption('#mv-tipo', tipo);
    await page.fill('#mv-valor', valor);
    await page.fill('#mv-motivo', motivo);
    await page.click('#form-movimento button[type=submit]');
    await page.waitForSelector('#dlg-confirmar[open]');
  }
  await movimento('suprimento', '20,00', 'mais troco de teste');
  await foto('controle-caixa-confirmar-suprimento');
  await page.click('#dlg-confirmar button[type=submit]');
  await torrada(/Suprimento de R\$ 20,00 lançado\./, 'suprimento lançado');
  await movimento('sangria', '500,00', 'sangria grande demais de teste');
  await page.click('#dlg-confirmar button[type=submit]');
  await espera('#form-movimento .msg-form', /maior que o dinheiro/, 'sangria maior que a gaveta é recusada');
  await movimento('sangria', '30,00', 'pagamento do gelo de teste');
  await page.click('#dlg-confirmar button[type=submit]');
  await torrada(/Sangria de R\$ 30,00 lançada\./, 'sangria lançada');
  await espera('[data-cx="dinheiro_esperado"]', /^R\$ 90,00$/, 'dinheiro esperado = 100 + 20 - 30');
  await medir('controle-caixa-aberto');

  // ------------------------------------------------------------------ 7) venda 1: leitor, quantidade, nome, cliente, duas formas
  await page.keyboard.press('F2');
  await page.waitForURL(base + '/caixa');
  await page.waitForFunction(() => document.activeElement && document.activeElement.id === 'prod');
  confere('PDV aberto: o cursor já está no campo do produto', true);
  await espera('[data-forma="pix"] .l2', /^5% de desconto$/, 'botão do Pix mostra o desconto da forma');
  await espera('[data-forma="credito"] .l2', /^3% de acréscimo$/, 'botão do Crédito mostra o acréscimo');
  await page.keyboard.type('7890000000017'); await page.keyboard.press('Enter'); // como o leitor faz
  await espera('#v-total', /^R\$ 5,00$/, 'bipe do código de barras lança 1 picolé a 5,00');
  await espera('#v-numero', /^1$/, 'a venda recebeu o nº 1');
  await page.keyboard.type('3*1'); await page.keyboard.press('Enter');
  await espera('#v-total', /^R\$ 20,00$/, '"3*1" soma 3 no mesmo item (4 x 5,00)');
  confere('produto repetido não cria outra linha', (await page.$$eval('#tabela-itens tbody tr', t => t.length)) === 1);
  // Editar a quantidade na linha: 10 unidades entram na faixa de 4,50.
  await page.fill('#tabela-itens tbody tr:nth-child(1) input', '10');
  await page.keyboard.press('Enter');
  await espera('#v-total', /^R\$ 45,00$/, 'quantidade editada para 10: preço por quantidade 4,50');
  await espera('#tabela-itens tbody tr:nth-child(1) .tag', /a partir de 10/, 'linha mostra a faixa de quantidade');
  await page.waitForFunction(() => document.activeElement && document.activeElement.id === 'prod');
  // Por nome, com quantidade quebrada (quilo): 0,350 x 59,90 = 20,965 -> 20,97.
  await page.keyboard.press('F3'); await page.keyboard.type('0,350');
  await page.keyboard.press('F2'); await page.keyboard.type('sorv');
  await page.waitForSelector('#sugestoes-prod li.marcada');
  await foto('pdv-sugestoes-de-produto');
  await page.keyboard.press('Enter');
  await espera('#v-total', /^R\$ 65,97$/, 'sorvete por quilo pelo nome: 0,350 kg = 20,97');
  // Sem acento, com quantidade 2: 2 x 3,00.
  await page.keyboard.press('F3'); await page.keyboard.type('2');
  await page.keyboard.press('F2'); await page.keyboard.type('agua'); await page.keyboard.press('Enter');
  await espera('#v-total', /^R\$ 71,97$/, '"agua" acha "Água": subtotal 45,00 + 20,97 + 6,00');
  confere('campo Qtd volta para 1', (await page.inputValue('#qtd')) === '1');
  // Quantidade quebrada num produto por unidade é recusada.
  await page.fill('#tabela-itens tbody tr:nth-child(3) input', '1,5'); await page.keyboard.press('Enter');
  await torrada(/unidade inteira/, 'água (UN) não aceita 1,5');
  await espera('#v-total', /^R\$ 71,97$/, 'total não mudou depois do erro');
  // Cliente do cadastro: atacado muda o preço do picolé para 4,00 (os outros não têm preço de atacado).
  await page.keyboard.press('F4'); await page.keyboard.type('mercado');
  await page.waitForSelector('#sugestoes-cli li.marcada');
  await foto('pdv-sugestoes-de-cliente');
  await page.keyboard.press('Enter');
  await torrada(/recalculados pela tabela ATACADO/, 'escolher cliente de atacado recalcula os preços');
  await espera('#cli-nome', /^Mercado Atacado de Teste$/, 'cliente aparece na venda');
  await espera('#v-total', /^R\$ 66,97$/, 'atacado: 40,00 + 20,97 + 6,00');
  await medir('pdv-cliente-atacado');
  // Trocar o cliente: Maria (varejo).
  await page.keyboard.press('F4'); await page.keyboard.type('maria'); await page.waitForSelector('#sugestoes-cli li.marcada'); await page.keyboard.press('Enter');
  await espera('#cli-nome', /^Maria de Teste$/, 'cliente trocado na mesma venda');
  await espera('#v-total', /^R\$ 71,97$/, 'voltou ao preço de varejo');
  // Pix em parte: 20,00 pagos no Pix quitam 20 / 0,95 = 21,05 da venda; falta 71,97 - 21,05 = 50,92.
  await page.keyboard.press('F7');
  await page.waitForSelector('#dlg-valor[open]');
  confere('valor sugerido no Pix = tudo com 5% de desconto (68,37)', (await page.inputValue('#dv-valor')) === '68,37', await page.inputValue('#dv-valor'));
  await foto('pdv-receber-no-pix');
  await page.fill('#dv-valor', '20,00'); await page.keyboard.press('Enter');
  await espera('#v-situacao', /^Falta pagar R\$ 50,92$/, 'Pix de 20,00: falta 50,92');
  await espera('#v-total', /^R\$ 70,92$/, 'total com o desconto do Pix: 71,97 - 1,05');
  await espera('[data-forma="credito"] .l2', /^R\$ 52,45 \(\+3%\)$/, 'crédito mostra quanto fica o resto: 50,92 + 1,53');
  // O resto no crédito.
  await page.keyboard.press('F9');
  await page.waitForSelector('#dlg-valor[open]');
  await page.keyboard.press('Enter');
  await espera('#v-situacao', /^Pago sem troco$/, 'duas formas quitam a venda');
  await espera('#v-total', /^R\$ 72,45$/, 'total final: 71,97 - 1,05 + 1,53');
  await medir('pdv-duas-formas');
  // Trocar a forma de um pagamento já lançado: Pix -> Débito (sem percentual) e de volta.
  await page.selectOption('#lancados .pg:nth-child(2) select', 'debito');
  await espera('#v-total', /^R\$ 73,50$/, 'Pix trocado por Débito: some o desconto (71,97 + 1,53)');
  await page.selectOption('#lancados .pg:nth-child(2) select', 'pix');
  await espera('#v-total', /^R\$ 72,45$/, 'de volta ao Pix: 72,45');
  // Finalizar: escolha da NFC-e.
  await page.keyboard.press('F10');
  await page.waitForSelector('#dlg-finalizar[open]');
  confere('"Com NFC-e" existe, mas desligado (fiscal não configurado)', await page.isDisabled('#df-com'));
  await espera('#dlg-finalizar [data-fim="pagamento"]', /^Pix R\$ 20,00 \+ Crédito R\$ 52,45$/, 'resumo do pagamento ao finalizar');
  await foto('pdv-finalizar-nfce');
  await page.keyboard.press('Enter'); // o foco está em "Sem NFC-e"
  await torrada(/Venda nº 1 finalizada: R\$ 72,45/, 'venda 1 finalizada');
  await espera('#saldo-do-dia', /^Vendas hoje: R\$ 72,45 · 1 venda$/, 'saldo do dia na tela do caixa');

  // ------------------------------------------------------------------ 8) venda 2: dinheiro com troco
  await page.keyboard.type('3'); await page.keyboard.press('Enter');
  await espera('#v-total', /^R\$ 3,00$/, 'venda 2: água pelo código');
  await page.keyboard.press('F6');
  await page.waitForSelector('#dlg-valor[open]');
  await page.fill('#dv-valor', '10'); await page.keyboard.press('Enter');
  await espera('#v-situacao', /^Troco R\$ 7,00$/, 'dinheiro 10,00 para 3,00: troco 7,00');
  await medir('pdv-troco');
  await page.waitForFunction(() => document.activeElement && document.activeElement.id === 'btn-finalizar');
  await page.keyboard.press('Enter');
  await page.waitForSelector('#dlg-finalizar[open]');
  await page.keyboard.press('Enter');
  await page.waitForSelector('#dlg-fim[open]');
  await espera('#dlg-fim [data-troco-valor]', /^R\$ 7,00$/, 'depois de finalizar, o troco fica na tela');
  await foto('pdv-venda-finalizada-troco');
  await page.keyboard.press('Enter');
  await espera('#saldo-do-dia', /^Vendas hoje: R\$ 75,45 · 2 vendas$/, 'saldo do dia somou a venda 2');
  await espera('#tabela-itens tbody', /Última venda: nº 2 · R\$ 3,00 · Dinheiro R\$ 3,00 · troco R\$ 7,00/, 'tela vazia lembra a última venda');

  // ------------------------------------------------------------------ 9) venda 3: cancelada
  await page.keyboard.type('1'); await page.keyboard.press('Enter');
  await espera('#v-numero', /^3$/, 'venda 3 aberta');
  await page.keyboard.press('F12');
  await page.waitForSelector('#dlg-confirmar[open]');
  await foto('pdv-cancelar-venda');
  await page.fill('#dc-motivo', 'cliente desistiu (teste)'); await page.keyboard.press('Enter');
  await torrada(/Venda nº 3 cancelada/, 'venda 3 cancelada');
  await espera('#v-total', /^—$/, 'sem venda aberta, o total volta para "—"');

  // ------------------------------------------------------------------ 10) venda 4: desconto do gerente
  await page.keyboard.type('2*1'); await page.keyboard.press('Enter');
  await espera('#v-total', /^R\$ 10,00$/, 'venda 4: 2 picolés');
  await page.keyboard.press('F5');
  await page.waitForSelector('#dlg-valor[open]');
  await page.fill('#dv-valor', '10%'); await page.keyboard.press('Enter');
  await espera('#v-total', /^R\$ 9,00$/, 'desconto de 10% do gerente');
  await espera('#v-desconto', /^Desconto: -R\$ 1,00$/, 'desconto aparece no total');
  await page.keyboard.press('F8'); await page.waitForSelector('#dlg-valor[open]'); await page.keyboard.press('Enter');
  await espera('#v-situacao', /^Pago sem troco$/, 'débito quita a venda 4');
  await page.keyboard.press('F10'); await page.waitForSelector('#dlg-finalizar[open]'); await page.keyboard.press('Enter');
  await torrada(/Venda nº 4 finalizada: R\$ 9,00/, 'venda 4 finalizada');
  await espera('#saldo-do-dia', /^Vendas hoje: R\$ 84,45 · 3 vendas$/, 'saldo do dia: 72,45 + 3,00 + 9,00');
  await page.click('#saldo-do-dia');
  await page.waitForSelector('#dlg-saldo[open]');
  const saldo = await page.$$eval('#dlg-saldo dd', dds => dds.map(d => d.textContent).join(' | '));
  // ticket médio = 84,45 / 3 = 28,15
  confere('detalhe do saldo do dia', saldo === 'R$ 84,45 | 3 | R$ 28,15 | R$ 3,00 | R$ 20,00 | R$ 9,00 | R$ 52,45', saldo);
  await foto('pdv-saldo-do-dia');
  await page.keyboard.press('Escape');
  await medir('pdv-sem-venda');

  // ------------------------------------------------------------------ 11) controle de caixa: vendas, cancelamento e fechamento
  await page.keyboard.press('F11');
  await page.waitForURL(base + '/controle-caixa');
  await espera('[data-cx="vendas_total"]', /^R\$ 84,45$/, 'controle: total vendido');
  await espera('[data-cx="dinheiro_esperado"]', /^R\$ 93,00$/, 'controle: dinheiro esperado = 90 + 3 da venda em dinheiro');
  const formas = await page.$$eval('#tabela-formas tbody tr', trs => trs.map(tr => Array.from(tr.children).map(td => td.textContent).join(' ')).join(' | '));
  confere('controle: por forma (recebido e esperado)', formas === 'Dinheiro 3,00 93,00 | Pix 20,00 20,00 | Débito 9,00 9,00 | Crédito 52,45 52,45', formas);
  await medir('controle-caixa-com-vendas');
  await page.click('[data-aba="movimentos"]');
  await espera('#tabela-movimentos tbody', /Suprimento \+20,00 mais troco de teste \(Gerente de Teste\).*Sangria -30,00 pagamento do gelo de teste \(Gerente de Teste\)/, 'aba de sangrias e suprimentos');
  await foto('controle-caixa-movimentos');
  await page.click('[data-aba="vendas"]');
  await espera('#tabela-vendas tbody tr:nth-child(1)', /^4 .* Consumidor final Débito 9,00 9,00 Finalizada/, 'aba de vendas: a mais nova primeiro');
  await espera('#tabela-vendas tbody tr:nth-child(2)', /^3 .* Cancelada/, 'venda cancelada aparece como cancelada');
  await espera('#tabela-vendas tbody tr:nth-child(4)', /^1 .* Maria de Teste Pix 20,00 \+ Crédito 52,45 72,45 Finalizada/, 'venda 1 com cliente e duas formas');
  await foto('controle-caixa-vendas');
  // O gerente cancela a venda 2 (dinheiro): sai dos totais.
  await page.click('#tabela-vendas tbody tr:nth-child(3) button:has-text("Cancelar")'); // o primeiro botão da linha é o de imprimir
  await page.waitForSelector('#dlg-confirmar[open]');
  await page.keyboard.press('Enter');
  await espera('#dlg-confirmar .msg-form', /Escreva o motivo/, 'cancelar venda finalizada exige o motivo');
  await page.fill('#dc-motivo', 'troco errado (teste)'); await page.keyboard.press('Enter');
  await torrada(/Venda nº 2 cancelada/, 'gerente cancela a venda 2');
  await espera('[data-cx="vendas_total"]', /^R\$ 81,45$/, 'total vendido sem a venda cancelada');
  await espera('[data-cx="dinheiro_esperado"]', /^R\$ 90,00$/, 'dinheiro esperado sem a venda cancelada');
  // Fechamento: dinheiro contado com 1,00 a menos.
  await page.click('#btn-fechar');
  await page.waitForSelector('#dlg-fechar[open]');
  const campos = '#dlg-fechar tbody input';
  await page.locator(campos).nth(0).fill('89,00');
  await page.locator(campos).nth(1).fill('20,00');
  await page.locator(campos).nth(3).fill('52,45');
  await page.click('#form-fechar button[type=submit]');
  await espera('#form-fechar .msg-form', /Digite o valor contado em Débito/, 'fechamento exige o contado de todas as formas');
  await page.locator(campos).nth(2).fill('9,00');
  await page.click('#form-fechar button[type=submit]');
  await espera('#form-fechar .msg-form', /Há diferença: Dinheiro -1,00/, 'fechamento avisa a diferença antes de fechar');
  await foto('controle-caixa-fechamento');
  await page.click('#form-fechar button[type=submit]');
  await torrada(/Caixa fechado\./, 'caixa fechado');
  await espera('#tabela-formas tbody tr:nth-child(1)', /^Dinheiro 0,00 90,00 89,00 -1,00$/, 'resultado do fechamento: diferença de -1,00 no dinheiro');
  await espera('[data-status="caixa"] .texto', /^Caixa: fechado$/, 'indicador do topo voltou para fechado');
  await medir('controle-caixa-depois-de-fechar');
  await page.click('[data-aba="historico"]');
  await espera('#tabela-historico tbody tr:nth-child(1)', /Gerente de Teste 2 81,45 -1,00 0,00$/, 'fechamentos anteriores (gerente)');
  await foto('controle-caixa-historico');
  await page.goto(base + '/inicio');
  await espera('[data-resumo="total"]', /^R\$ 81,45$/, 'Início: resumo de hoje com as vendas');
  await espera('[data-resumo="ticket"]', /^R\$ 40,73$/, 'Início: ticket médio 81,45 / 2 = 40,725 -> 40,73');
  await medir('inicio-com-vendas');

  // ------------------------------------------------------------------ 12) operador comum
  const criado = await api('POST', '/api/operadores', { nome: 'Caixa de Teste', login: 'caixa', senha: senhaCaixa, perfil: 'operador' });
  confere('operador comum criado', criado.status === 201, criado.status);
  const ctx2 = await b.newContext({ viewport: { width: LARGURA, height: ALTURA } });
  page = await ctx2.newPage(); vigiar(page);
  await page.goto(base + '/');
  await page.selectOption('#lg-operador', 'caixa');
  await page.fill('#lg-senha', senhaCaixa); await page.keyboard.press('Enter');
  await page.waitForURL(base + '/inicio');
  await page.goto(base + '/produtos');
  confere('operador comum não abre Produtos', new URL(page.url()).pathname === '/inicio', page.url());
  await page.goto(base + '/tabelas-preco');
  confere('operador comum não abre Tabelas de preço', new URL(page.url()).pathname === '/inicio', page.url());
  await page.goto(base + '/clientes');
  await page.waitForSelector('#tabela-clientes tbody tr:not(:has(.sem-linhas))');
  confere('operador comum abre Clientes, mas não muda a tabela de preço', await page.isDisabled('#c-tabela'));
  await page.fill('#c-nome', 'Cliente do Balcão de Teste'); await page.keyboard.press('F10');
  await torrada(/Cliente Cliente do Balcão de Teste cadastrado/, 'operador comum cadastra cliente');
  await medir('clientes-operador-comum');
  await page.goto(base + '/controle-caixa');
  await page.waitForSelector('#form-abrir', { state: 'visible' });
  confere('operador comum não vê os fechamentos anteriores', (await page.$('[data-aba="historico"]')) === null);
  await page.fill('#cx-fundo', '50'); await page.keyboard.press('Enter');
  await torrada(/Caixa aberto com fundo de troco de R\$ 50,00/, 'operador comum abre o caixa');
  await page.keyboard.press('F2');
  await page.waitForURL(base + '/caixa');
  await page.waitForFunction(() => document.activeElement && document.activeElement.id === 'prod');
  await page.keyboard.type('1'); await page.keyboard.press('Enter');
  await espera('#v-total', /^R\$ 5,00$/, 'operador comum vende');
  await page.keyboard.press('F5');
  await torrada(/Só o gerente dá desconto/, 'operador comum não dá desconto (tela)');
  // Leitor bipado com o foco fora de um campo: o código vai para o produto, não aciona botão nenhum.
  await page.keyboard.press('F6'); await page.waitForSelector('#dlg-valor[open]');
  await page.fill('#dv-valor', '7890000000017'); await page.keyboard.press('Enter');
  await torrada(/muito maior que o que falta pagar/, 'código de barras lido como valor em dinheiro é recusado');
  await page.keyboard.press('F6'); await page.waitForSelector('#dlg-valor[open]'); await page.keyboard.press('Enter');
  await page.waitForFunction(() => document.activeElement && document.activeElement.id === 'btn-finalizar');
  await page.keyboard.type('3'); await page.keyboard.press('Enter');
  await espera('#v-total', /^R\$ 8,00$/, 'com o foco no botão Finalizar, o que o leitor digita vai para o produto');
  confere('o bipe não abriu a caixa de finalizar', (await page.$('#dlg-finalizar[open]')) === null);
  await torrada(/os pagamentos foram desfeitos/, 'item novo desfaz o pagamento, com aviso');
  const desc = await api('PUT', '/api/venda/desconto', { centavos: 100 });
  confere('operador comum não dá desconto (servidor)', desc.status === 403, desc.status);
  await medir('pdv-operador-comum');
  await page.keyboard.press('F12'); await page.waitForSelector('#dlg-confirmar[open]'); await page.keyboard.press('Enter');
  await torrada(/Venda nº 5 cancelada/, 'operador comum cancela a venda que abriu (sem motivo)');

  await b.close();
  console.log('');
  console.log(erros.length ? 'ERROS DO NAVEGADOR:\n' + erros.join('\n') : 'Nenhum erro de JavaScript, de rede ou do servidor (5xx).');
  console.log(falhas.length ? 'FALHAS (' + falhas.length + '): ' + falhas.join(' | ') : 'Todas as conferências passaram.');
  process.exit(falhas.length || erros.length ? 1 : 0);
})().catch(e => { console.error('ROTEIRO INTERROMPIDO: ' + e.message); process.exit(2); });

// Roteiro das telas de estoque, entrada de NF por XML e financeiro, feito no navegador como um
// usuário faria, com os valores esperados calculados à mão (ver os comentários).
//
// Para rodar (precisa do Node.js com o pacote "playwright" e do Python do projeto; nenhum dos
// dois roteiros é dependência do programa):
//   1. suba o servidor com um banco NOVO, numa pasta vazia:
//        MOLEKA_PDV_DADOS=/caminho/de/uma/pasta/vazia python main.py --sem-janela --porta 8792
//   2. em outro terminal:
//        node tools/roteiros/estoque_compras_financeiro_no_navegador.js 8792 /caminho/para/os/prints
//      (um terceiro número muda a altura da janela; o padrão é 697, a área útil de 1366x768)
//
// Todos os dados daqui são fictícios, de teste (as notas saem de tools/roteiros/notas_ficticias.py)
// e as senhas são sorteadas a cada execução. O roteiro termina com código 0 quando tudo passa;
// os prints de cada tela ficam na pasta dada.
const { chromium } = require('playwright');
const { execFileSync } = require('child_process');
const path = require('path'); const fs = require('fs'); const crypto = require('crypto');
const LARGURA = 1366, ALTURA = Number(process.argv[4] || 697);

(async () => {
  const porta = process.argv[2]; const saida = path.resolve(process.argv[3]);
  fs.mkdirSync(saida, { recursive: true });
  const notas = path.join(saida, 'notas-ficticias');
  execFileSync(process.env.PYTHON || 'python3', [path.join(__dirname, 'notas_ficticias.py'), notas]);
  const base = 'http://127.0.0.1:' + porta;
  const senhaGerente = 'g' + crypto.randomBytes(5).toString('hex');
  const senhaCaixa = String(1000 + crypto.randomInt(9000));
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: LARGURA, height: ALTURA }, locale: 'pt-BR' });
  const page = await ctx.newPage();
  const erros = [];
  const falhas = [];
  let passo = 0; let conferencias = 0;
  page.on('pageerror', e => erros.push('pageerror: ' + e.message));
  // O navegador escreve no console toda resposta 4xx; as esperadas são conferidas no roteiro.
  page.on('console', m => { if (m.type() === 'error' && !/status of (401|403|404|409|422)/.test(m.text())) erros.push('console: ' + m.text()); });
  page.on('requestfailed', r => erros.push('requestfailed: ' + r.url()));
  page.on('response', r => { if (r.status() >= 500) erros.push(r.status() + ': ' + r.url()); });

  function confere(nome, ok, detalhe) { conferencias += 1; console.log((ok ? 'OK   ' : 'FALHA') + ' ' + nome + (detalhe !== undefined ? ' — ' + detalhe : '')); if (!ok) falhas.push(nome); }
  const LER = `(el) => { const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT); const p = []; while (w.nextNode()) p.push(w.currentNode.nodeValue); return p.join(' ').replace(/\\s+/g, ' ').trim(); }`;
  async function texto(sel) { return page.evaluate(([s, ler]) => { const el = document.querySelector(s); return el ? eval(ler)(el) : '(sem elemento)'; }, [sel, LER]); }
  async function espera(sel, regex, nome) {
    try {
      await page.waitForFunction(([s, fonte, flags, ler]) => { const el = document.querySelector(s); return !!el && new RegExp(fonte, flags).test(eval(ler)(el)); }, [sel, regex.source, regex.flags, LER], { timeout: 5000 });
      confere(nome, true, await texto(sel));
    } catch (e) { confere(nome, false, 'esperava ' + regex + ' e veio: ' + (await texto(sel).catch(() => '(sem elemento)'))); }
  }
  async function torrada(regex, nome) { await espera('.torrada.visivel', regex, nome); }
  // A linha de uma tabela que contém um texto: devolve o texto inteiro dela (ou "" se não há).
  async function linha(tabela, contem) {
    return page.evaluate(([t, c, ler]) => { const tr = Array.from(document.querySelectorAll(t + ' tbody tr')).find(l => eval(ler)(l).includes(c)); return tr ? eval(ler)(tr) : ''; }, [tabela, contem, LER]);
  }
  async function esperaLinha(tabela, contem, regex, nome) {
    try {
      await page.waitForFunction(([t, c, fonte, ler]) => { const tr = Array.from(document.querySelectorAll(t + ' tbody tr')).find(l => eval(ler)(l).includes(c)); return !!tr && new RegExp(fonte).test(eval(ler)(tr)); }, [tabela, contem, regex.source, LER], { timeout: 5000 });
      confere(nome, true, await linha(tabela, contem));
    } catch (e) { confere(nome, false, 'esperava ' + regex + ' na linha de “' + contem + '” e veio: ' + ((await linha(tabela, contem)) || '(sem a linha)')); }
  }
  const naLinha = (tabela, contem) => page.locator(tabela + ' tbody tr', { hasText: contem });
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
  const api = (metodo, caminho, corpo) => page.evaluate(async ([m, c, d]) => {
    const r = await fetch(c, { method: m, headers: d ? { 'Content-Type': 'application/json' } : {}, body: d ? JSON.stringify(d) : undefined });
    let j = null; try { j = await r.json(); } catch (e) { j = null; }
    return { status: r.status, dados: j };
  }, [metodo, caminho, corpo || null]);
  async function criar(caminho, corpo) { const r = await api('POST', caminho, corpo); if (r.status !== 201) throw new Error(caminho + ': ' + r.status + ' ' + JSON.stringify(r.dados)); return r.dados; }
  async function confirmar(regex, nome, motivo) {
    await page.waitForSelector('#dlg-confirmar[open]');
    if (regex) await espera('#dlg-confirmar [data-texto]', regex, nome);
    if (motivo !== undefined) await page.fill('#dc-motivo', motivo);
    await page.click('#dlg-confirmar button[type="submit"]');
  }
  function maisDias(iso, n) { const p = iso.split('-').map(Number); const d = new Date(p[0], p[1] - 1, p[2] + n); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); }
  const diaMes = iso => iso.slice(8, 10) + '/' + iso.slice(5, 7);
  const br = iso => diaMes(iso) + '/' + iso.slice(0, 4); // como a pessoa digita: dia/mês/ano
  // Escolhe o arquivo como o usuário: F3 abre a janela de arquivos do sistema. A escuta fica
  // ligada desde o começo (ligá-la só na hora da tecla perde a janela de vez em quando).
  let aoAbrirAJanela = null;
  page.on('filechooser', janela => { if (aoAbrirAJanela) aoAbrirAJanela(janela); });
  async function escolherArquivo(nome) {
    const aberta = new Promise((resolver, recusar) => {
      aoAbrirAJanela = resolver;
      setTimeout(() => recusar(new Error('F3 não abriu a janela de escolher arquivo')), 5000);
    });
    await page.keyboard.press('F3');
    await (await aberta).setFiles(path.join(notas, nome));
    aoAbrirAJanela = null;
  }
  // Solta o arquivo em cima da janela, como quem arrasta da pasta.
  async function soltarArquivo(nome) {
    await page.evaluate(([texto, n]) => {
      const carga = new DataTransfer();
      carga.items.add(new File([texto], n, { type: 'text/xml' }));
      document.body.dispatchEvent(new DragEvent('drop', { dataTransfer: carga, bubbles: true, cancelable: true }));
    }, [fs.readFileSync(path.join(notas, nome), 'utf8'), nome]);
  }

  // ------------------------------------------------------------------ 1) preparação (pela API)
  await page.goto(base + '/');
  await page.fill('#ci-nome', 'Gerente de Teste');
  await page.fill('#ci-senha', senhaGerente); await page.fill('#ci-senha2', senhaGerente);
  await page.keyboard.press('Enter');
  await page.waitForURL(base + '/inicio');
  const hoje = (await api('GET', '/api/status')).dados.agora.slice(0, 10);
  const tabelas = (await api('GET', '/api/tabelas-preco')).dados;
  const varejo = tabelas.find(t => t.padrao).id;
  // Picolé 5,00 (4,50 a partir de 10), sorvete 59,90 o quilo e água 3,00. Pix -5%, crédito +3%.
  const picole = (await criar('/api/produtos', { descricao: 'Picolé de teste', ean: '7890000000017', precos: [{ tabela_id: varejo, qtd_min: '1', preco_centavos: 500 }, { tabela_id: varejo, qtd_min: '10', preco_centavos: 450 }] })).id;
  const sorvete = (await criar('/api/produtos', { descricao: 'Sorvete de teste por quilo', unidade: 'KG', precos: [{ tabela_id: varejo, qtd_min: '1', preco_centavos: 5990 }] })).id;
  const agua = (await criar('/api/produtos', { descricao: 'Água de teste', precos: [{ tabela_id: varejo, qtd_min: '1', preco_centavos: 300 }] })).id;
  await api('PUT', '/api/formas-pagamento/pix', { ajuste_bp: -500, ativo: true });
  await api('PUT', '/api/formas-pagamento/credito', { ajuste_bp: 300, ativo: true });
  await criar('/api/caixa/abrir', { fundo_troco_centavos: 10000 });
  await espera('.lateral a[href="/estoque"]', /Estoque/, 'menu lateral tem o Estoque');
  await espera('.aviso', /estoque, entrada de nota por XML e financeiro/, 'Início diz o que já funciona nesta versão');

  // ------------------------------------------------------------------ 2) Estoque
  await page.goto(base + '/estoque');
  await espera('[data-kpi="com_saldo_m"]', /^de 3 produtos ativos$/, 'Estoque: conta os produtos ativos');
  await espera('[data-kpi="com_saldo"]', /^0$/, 'Estoque: nenhum produto com saldo');
  await espera('[data-kpi="valor"]', /^—$/, 'Estoque: sem saldo, o valor não é inventado');
  await espera('[data-kpi="valor_m"]', /^Sem dados: nenhum produto com saldo\.$/, 'Estoque: diz o motivo de não haver valor');
  await esperaLinha('#tabela-estoque', 'Sorvete de teste', /0 KG.*—.*Zerado/, 'Estoque: produto sem movimento aparece zerado e sem custo');
  // Entrada de 2,350 kg de sorvete a 25,00 o quilo: valor 2,350 x 25,00 = 58,75.
  await naLinha('#tabela-estoque', 'Sorvete de teste').getByRole('button').click();
  await espera('[data-ficha="descricao"]', /^Sorvete de teste por quilo$/, 'Estoque: a ficha abre no produto escolhido');
  await page.fill('#mv-qtd', '2,350'); await page.fill('#mv-custo', '25,00'); await page.fill('#mv-motivo', 'produção do dia (teste)');
  await page.keyboard.press('F10');
  await confirmar(/o saldo passa de 0 KG para 2,350 KG\. Custo de R\$ 25,00 cada/, 'Estoque: a confirmação mostra o saldo antes e depois');
  await torrada(/Entrada lançada\. Saldo de Sorvete de teste por quilo: 2,350 KG\./, 'Estoque: entrada lançada');
  await espera('[data-kpi="valor"]', /^R\$ 58,75$/, 'Estoque: valor = 2,350 kg x 25,00');
  await espera('[data-ficha="custo"]', /^R\$ 25,00$/, 'Estoque: custo médio depois da primeira entrada');
  // Saída sem motivo e quantidade quebrada em produto por unidade: recusadas.
  await page.selectOption('#mv-tipo', 'saida'); await page.fill('#mv-qtd', '1');
  await page.keyboard.press('F10');
  await espera('#form-movimento .msg-form', /Escreva o motivo/, 'Estoque: saída exige o motivo');
  // "1.000" com ponto: mil ou um? A tela não adivinha.
  await page.fill('#mv-qtd', '1.000'); await page.fill('#mv-motivo', 'teste'); await page.keyboard.press('F10');
  await espera('#form-movimento .msg-form', /Com ponto fica a dúvida: 1\.000 é 1000 ou 1,000\? Digite sem o ponto, ou com vírgula\./, 'Estoque: quantidade ambígua (1.000) é recusada');
  confere('Estoque: a quantidade ambígua não abriu a confirmação', (await page.$('#dlg-confirmar[open]')) === null);
  await naLinha('#tabela-estoque', 'Picolé de teste').getByRole('button').click();
  await page.fill('#mv-qtd', '1,5'); await page.fill('#mv-motivo', 'teste');
  await page.keyboard.press('F10');
  await confirmar(null);
  await espera('#form-movimento .msg-form', /unidade inteira/, 'Estoque: picolé não aceita quantidade quebrada');
  // Contagem: o sistema tem 2,350 kg e foram contados 2 kg. Valor 2 x 25,00 = 50,00.
  await naLinha('#tabela-estoque', 'Sorvete de teste').getByRole('button').click();
  await page.selectOption('#mv-tipo', 'contagem'); await page.fill('#mv-qtd', '2');
  await espera('[data-rotulo-qtd]', /^Quantidade contada$/, 'Estoque: o rótulo muda na contagem');
  await page.keyboard.press('F10');
  await confirmar(/o sistema tem 2,350 KG e você contou 2 KG\. Será lançada a diferença de -0,350 KG/, 'Estoque: a contagem mostra a diferença antes de gravar');
  await torrada(/Contagem gravada\. Saldo de Sorvete de teste por quilo: 2 KG\./, 'Estoque: contagem gravada');
  await espera('[data-kpi="valor"]', /^R\$ 50,00$/, 'Estoque: valor depois da contagem = 2 kg x 25,00');
  await page.fill('#mv-qtd', '2'); await page.keyboard.press('F10');
  await torrada(/A contagem bateu com o sistema \(2 KG\): nada foi alterado\./, 'Estoque: contagem igual ao saldo não grava nada');
  await page.click('#btn-historico'); await page.waitForSelector('#dlg-historico[open]');
  await espera('#dlg-historico tbody tr:nth-child(1)', /Contagem -0,350 2 — Contagem: o sistema tinha 2,35 e foram contados 2 Gerente de Teste/, 'Histórico: a contagem, com o saldo depois e quem fez');
  await espera('#dlg-historico tbody tr:nth-child(2)', /Ajuste \+2,350 2,350 25,00 produção do dia \(teste\)/, 'Histórico: a entrada, com custo e motivo');
  confere('Histórico: só os dois movimentos feitos', (await page.locator('#dlg-historico tbody tr').count()) === 2);
  await foto('estoque-historico');
  await page.keyboard.press('Escape');
  await page.fill('#busca', 'agua');
  await page.waitForFunction(() => document.querySelectorAll('#tabela-estoque tbody tr').length === 1);
  await esperaLinha('#tabela-estoque', 'Água de teste', /Água de teste/, 'Estoque: pesquisa sem acento ("agua" acha "Água")');
  await page.fill('#busca', ''); await page.selectOption('#situacao', 'com_saldo');
  await page.waitForFunction(() => document.querySelectorAll('#tabela-estoque tbody tr').length === 1);
  await esperaLinha('#tabela-estoque', 'Sorvete de teste', /2 KG 25,00 Em dia/, 'Estoque: filtro "com saldo"');
  await page.selectOption('#situacao', '');
  await medir('estoque');

  // ------------------------------------------------------------------ 3) Entrada de NF: nota 123
  await page.goto(base + '/entrada-nf');
  await escolherArquivo('nao-e-nota.xml');
  await espera('[data-msg-arquivo]', /nao-e-nota\.xml.*não achei os dados da nota/, 'Entrada de NF: arquivo que não é nota é recusado, com o motivo');
  await soltarArquivo('nota-ficticia-123.xml'); // arrastado para a janela: é lido como o escolhido
  await espera('[data-nf="fornecedor"]', /^FORNECEDOR FICTICIO DE TESTE LTDA$/, 'Entrada de NF: fornecedor lido da nota (arquivo arrastado para a janela)');
  await espera('[data-nf="numero"]', /^NF 123 · série 1$/, 'Entrada de NF: número e série');
  await espera('[data-nf="total"]', /^R\$ 580,60$/, 'Entrada de NF: total da nota');
  await espera('[data-nf="itens"]', /^3 itens$/, 'Entrada de NF: quantidade de itens');
  confere('Entrada de NF: nota certa não traz avisos', await page.isHidden('[data-avisos]'));
  const itens = page.locator('#tabela-itens tbody tr');
  // Item 1: 2 caixas, 109,60 de custo (96,00 + frete 4,00 + ICMS-ST 9,60). A nota diz 24 por
  // caixa e o código de barras da unidade é o do picolé: 48 UN a 109,60 / 48 = 2,283 -> 2,28.
  confere('item 1: produto achado pelo código de barras', (await itens.nth(0).locator('select').inputValue()) === 'vincular' && (await itens.nth(0).locator('input').first().inputValue()) === 'Picolé de teste');
  await espera('#tabela-itens tbody tr:nth-child(1)', /custo R\$ 109,60.*achado pelo código de barras.*48 UN R\$ 2,28 cada/, 'item 1: custo com frete e ICMS-ST; entram 48 UN a 2,28');
  await espera('[data-lote-texto]', /^2 itens ainda sem decisão\.$/, 'Entrada de NF: avisa quantos itens faltam decidir');
  await page.keyboard.press('F10');
  await espera('#form-importar .msg-form', /Falta decidir o que fazer com o item 2/, 'Entrada de NF: não importa com item sem decisão');
  // Item 2: 3 baldes, 441,00 de custo (450,00 - 22,50 + IPI 13,50); 10 kg por balde: 30 KG a 14,70.
  await itens.nth(1).locator('select').selectOption('vincular');
  await espera('#tabela-itens tbody tr:nth-child(2) td:last-child', /^escolha o produto$/, 'item 2: pede o produto');
  await itens.nth(1).locator('input').first().fill('sorv');
  await espera('.sugestoes.flutua', /Sorvete de teste por quilo KG/, 'item 2: a pesquisa sugere o produto');
  await page.keyboard.press('Enter');
  await espera('#tabela-itens tbody tr:nth-child(2) td:last-child', /^30 KG R\$ 14,70 cada$/, 'item 2: entram 30 KG a 441,00 / 30 = 14,70');
  // Fator errado no item 1: 2 caixas x 0,3 = 0,6 picolé. A tela avisa antes de mandar.
  await itens.nth(0).locator('input').nth(1).fill('0,3');
  await espera('#tabela-itens tbody tr:nth-child(1) td:last-child', /^0,600 UN quantidade quebrada: confira o fator$/, 'item 1: fator que dá quantidade quebrada é avisado');
  await itens.nth(0).locator('input').nth(1).fill('24');
  // Item 3: 5 pacotes de copo, 30,00: produto novo, 5 PCT a 6,00.
  await page.click('[data-lote-acao="criar"]');
  await espera('#tabela-itens tbody tr:nth-child(3)', /produto novo, sem preço de venda.*5 PCT R\$ 6,00 cada/, 'item 3: produto novo, 5 PCT a 6,00');
  confere('Entrada de NF: sem pendência, a faixa de decisão some', await page.isHidden('[data-lote]'));
  await espera('[data-contas-texto]', /^Criar as contas a pagar das 2 parcelas: \d\d\/\d\d R\$ 290,30 · \d\d\/\d\d R\$ 290,30$/, 'Entrada de NF: as duas parcelas de 290,30');
  confere('Entrada de NF: contas a pagar marcadas quando a nota traz parcelas', await page.isChecked('#gerar-contas'));
  await medir('entrada-nf-conferir');
  await page.keyboard.press('F10');
  // Com a pergunta aberta, outro arquivo solto na janela não troca a nota: o que se importa é o
  // que estava na tela (as decisões foram tomadas para aquela nota).
  await page.waitForSelector('#dlg-confirmar[open]');
  await soltarArquivo('nota-ficticia-140.xml');
  await page.waitForTimeout(500);
  confere('Entrada de NF: arquivo solto com a confirmação aberta não troca a nota', (await texto('[data-nf="numero"]')) === 'NF 123 · série 1', await texto('[data-nf="numero"]'));
  await confirmar(/2 itens dão entrada em produtos que já existem; 1 produto novo é criado \(sem preço de venda\)\. 2 contas a pagar são criadas\./, 'Entrada de NF: a confirmação resume o que vai acontecer');
  await page.waitForSelector('[data-passo="feito"]:not([hidden])');
  await espera('[data-feito]', /Picolé de teste : entraram 48 UN a R\$ 2,28 cada\./, 'importada: picolé');
  await espera('[data-feito]', /Sorvete de teste por quilo : entraram 30 KG a R\$ 14,70 cada\./, 'importada: sorvete');
  await espera('[data-feito]', /Produto novo: COPO FICTICIO DE TESTE 200 ML C\/100 \(código 4\)\. Ele está SEM preço de venda/, 'importada: produto novo, com aviso de que está sem preço');
  await espera('[data-feito]', /2 contas a pagar criadas em Financeiro/, 'importada: contas a pagar');
  await medir('entrada-nf-importada');
  // Estoque depois da nota. Sorvete: 2 kg a 25,00 + 30 kg a 14,70 = 491,00 em 32 kg = 15,34.
  // Valor: 48 x 2,28 + 32 x 15,34 + 5 x 6,00 = 109,44 + 490,88 + 30,00 = 630,32.
  let estoque = (await api('GET', '/api/estoque')).dados;
  const doEstoque = id => estoque.itens.find(i => i.produto_id === id);
  confere('estoque: picolé 48 a 2,28', Number(doEstoque(picole).saldo) === 48 && doEstoque(picole).custo_centavos === 228, JSON.stringify(doEstoque(picole)));
  confere('estoque: sorvete 32 kg a 15,34 (custo médio)', Number(doEstoque(sorvete).saldo) === 32 && doEstoque(sorvete).custo_centavos === 1534, doEstoque(sorvete).custo_centavos);
  confere('estoque: valor total 630,32', estoque.resumo.valor_centavos === 63032, estoque.resumo.valor_centavos);
  // A mesma nota de novo: avisada e travada.
  await escolherArquivo('nota-ficticia-123.xml');
  await espera('[data-avisos]', /Esta nota já foi importada em \d\d\/\d\d\/\d{4}\. Ela não entra duas vezes/, 'Entrada de NF: a mesma nota não entra duas vezes');
  confere('Entrada de NF: botão de importar travado na nota repetida', await page.isDisabled('#btn-importar'));

  // ------------------------------------------------------------------ 4) nota 140 (sem parcelas) e estorno
  await escolherArquivo('nota-ficticia-140.xml');
  await espera('[data-nf="total"]', /^R\$ 268,20$/, 'nota 140: total');
  // O sistema lembra que "PIC-24" deste fornecedor é o picolé, com 24 por caixa: 62,40 / 24 = 2,60.
  await espera('#tabela-itens tbody tr:nth-child(1)', /lembrado da última nota.*24 UN R\$ 2,60 cada/, 'nota 140: ligação lembrada da nota anterior');
  await itens.nth(1).locator('select').selectOption('vincular');
  await itens.nth(1).locator('input').first().fill('agua');
  await espera('.sugestoes.flutua', /Água de teste/, 'nota 140: pesquisa sem acento acha a água');
  await page.keyboard.press('Enter');
  // 2 fardos de 12 = 24 UN; 36,00 / 24 = 1,50.
  await espera('#tabela-itens tbody tr:nth-child(2) td:last-child', /^24 UN R\$ 1,50 cada$/, 'nota 140: fardo de 12 vira 24 UN a 1,50');
  await page.click('[data-lote-acao="ignorar"]');
  await espera('#tabela-itens tbody tr:nth-child(4) td:last-child', /^não entra$/, 'nota 140: itens sem entrada');
  await espera('[data-contas-texto]', /^A nota não traz parcelas\. Criar uma conta a pagar de R\$ 268,20$/, 'nota 140: sem parcelas, a conta é opcional');
  confere('nota 140: conta a pagar desmarcada por padrão', !(await page.isChecked('#gerar-contas')));
  await page.check('#gerar-contas');
  confere('nota 140: vencimento sugerido é hoje, em dia/mês/ano', (await page.inputValue('#nf-vencimento')) === br(hoje), await page.inputValue('#nf-vencimento'));
  confere('nota 140: categoria padrão é a de compra para revenda', (await page.locator('#nf-categoria option:checked').textContent()) === 'Compra de mercadorias para revenda');
  await page.keyboard.press('F10');
  await confirmar(/2 itens dão entrada em produtos que já existem; 2 itens ficam sem entrada no estoque\. 1 conta a pagar é criada\./, 'nota 140: confirmação');
  await page.waitForSelector('[data-passo="feito"]:not([hidden])');
  await espera('[data-feito]', /Água de teste : entraram 24 UN a R\$ 1,50 cada\..*LEITE FICTICIO DE TESTE INTEGRAL 1 L: sem entrada no estoque\..*1 conta a pagar criada/, 'nota 140: importada');
  // Picolé: 48 a 2,28 + 24 a 2,60 = 171,84 em 72 = 2,3867 -> 2,39.
  estoque = (await api('GET', '/api/estoque')).dados;
  confere('estoque: picolé 72 a 2,39 depois da segunda nota', Number(doEstoque(picole).saldo) === 72 && doEstoque(picole).custo_centavos === 239, doEstoque(picole).custo_centavos);
  confere('estoque: água 24 a 1,50', Number(doEstoque(agua).saldo) === 24 && doEstoque(agua).custo_centavos === 150);
  await page.click('[data-aba="notas"]');
  await esperaLinha('#tabela-notas', '140', /FORNECEDOR FICTICIO DE TESTE LTDA 11\.222\.333\/0001-81 140 268,20 4 1 Importada/, 'Notas importadas: a nota 140');
  await esperaLinha('#tabela-notas', '580,60', /123 580,60 3 2 Importada/, 'Notas importadas: a nota 123, com as 2 contas');
  await naLinha('#tabela-notas', '580,60').getByRole('button', { name: 'Ver a nota 123' }).click();
  await page.waitForSelector('#dlg-nota[open]');
  await espera('#dlg-nota tbody tr:nth-child(1)', /PICOLE FICTICIO DE TESTE CX 24 cód\. PIC-24 2 CX 109,60 Picolé de teste 48 UN 2,28/, 'Ver nota: o que entrou e a que custo');
  await foto('entrada-nf-ver-nota');
  await page.keyboard.press('Escape');
  // Estorno da nota 140: exige motivo; desfaz estoque, custo e a conta a pagar.
  await naLinha('#tabela-notas', '268,20').getByRole('button', { name: 'Estornar a nota 140' }).click();
  await page.waitForSelector('#dlg-confirmar[open]');
  await page.click('#dlg-confirmar button[type="submit"]');
  await espera('#dlg-confirmar .msg-form', /Escreva o motivo/, 'Estorno: exige o motivo');
  await confirmar(/O que entrou no estoque por esta nota sai de novo/, 'Estorno: a confirmação explica o que acontece', 'nota lançada por engano (teste)');
  await torrada(/NF 140 estornada/, 'Estorno feito');
  await esperaLinha('#tabela-notas', '268,20', /140 268,20 4 — Estornada/, 'Notas importadas: a nota 140 aparece estornada, sem contas');
  confere('Estorno: nenhum custo ficou para conferir', await page.isHidden('[data-msg-notas]'));
  estoque = (await api('GET', '/api/estoque')).dados;
  confere('estorno: picolé volta a 48 a 2,28', Number(doEstoque(picole).saldo) === 48 && doEstoque(picole).custo_centavos === 228, doEstoque(picole).custo_centavos);
  confere('estorno: água volta a zero e sem custo', Number(doEstoque(agua).saldo) === 0 && doEstoque(agua).custo_centavos === null, JSON.stringify(doEstoque(agua)));
  await medir('entrada-nf-notas');

  // ------------------------------------------------------------------ 5) vendas (pela API)
  // 1) 4 picolés a 5,00 = 20,00 em dinheiro.                      custo 4 x 2,28          =  9,12
  // 2) 10 picolés a 4,50 + 0,5 kg de sorvete (29,95) = 74,95;
  //    - 4,95 do gerente = 70,00; no Pix (-5%) = 66,50.           custo 22,80 + 7,67      = 30,47
  // 3) 2 picolés = 10,00 no crédito (+3%) = 10,30.                custo 2 x 2,28          =  4,56
  // 4) 2 águas = 6,00 em dinheiro. A água está sem custo (a nota dela foi estornada).
  async function vender(itensDaVenda, forma, desconto) {
    for (const [produto, quantidade] of itensDaVenda) await criar('/api/venda/itens', { produto_id: produto, quantidade: quantidade });
    if (desconto) await api('PUT', '/api/venda/desconto', { centavos: desconto });
    await criar('/api/venda/pagamentos', { forma: forma });
    return (await api('POST', '/api/venda/finalizar', {})).dados.venda.total_centavos;
  }
  const totais = [await vender([[picole, 4]], 'dinheiro'), await vender([[picole, 10], [sorvete, '0.5']], 'pix', 495), await vender([[picole, 2]], 'credito'), await vender([[agua, 2]], 'dinheiro')];
  confere('vendas de teste: 20,00 + 66,50 + 10,30 + 6,00', totais.join(',') === '2000,6650,1030,600', totais.join(','));

  // ------------------------------------------------------------------ 6) Financeiro: contas a pagar e a receber
  await page.goto(base + '/financeiro');
  // Datas são sempre dia/mês/ano (não dependem do idioma do Windows): 03/12 é 3 de dezembro.
  const lidas = await page.evaluate(() => ['3/12/2026', '03/12/26', '03122026', '031226', '31/02/2026', '12/13/2026', '1/1/1999', '', 'abc'].map(window.Moleka.lerData));
  confere('Datas digitadas são lidas como dia/mês/ano', JSON.stringify(lidas) === JSON.stringify(['2026-12-03', '2026-12-03', '2026-12-03', '2026-12-03', null, null, null, null, null]), JSON.stringify(lidas));
  // Ao entrar, o período é "Este mês". As parcelas da nota vencem daqui a 25 e a 55 dias: as que
  // caem fora do mês não estão na lista, e a tela avisa. "Ver todas em aberto" mostra as duas.
  const foraDoMes = [maisDias(hoje, 25), maisDias(hoje, 55)].filter(v => v.slice(0, 7) !== hoje.slice(0, 7)).length;
  await espera('[data-lc-fora-texto]', new RegExp('^Há mais ' + foraDoMes + (foraDoMes === 1 ? ' conta' : ' contas') + ' em aberto com vencimento fora deste período\\.$'), 'Financeiro: avisa das contas em aberto que vencem fora do período');
  await page.click('[data-lc-ver-abertas]');
  await espera('[data-lc-contagem]', /^2 lançamentos, de qualquer data$/, 'Financeiro: "Ver todas em aberto" mostra as duas parcelas da nota');
  confere('Financeiro: o filtro vira "Em aberto (qualquer data)" e o aviso some', (await page.inputValue('#lc-situacao')) === 'todas_em_aberto' && await page.isHidden('[data-lc-fora]'));
  await esperaLinha('#tabela-lancamentos', 'parcela 002', /parcela 002 .*Despesa 290,30 Em aberto/, 'Financeiro: a parcela que vence daqui a 55 dias aparece');
  await espera('[data-lk="a_pagar"]', /^R\$ 580,60$/, 'Financeiro: com esse filtro, "A pagar" soma tudo o que está em aberto');
  await espera('[data-lk="a_pagar_m"]', /^em aberto, de qualquer data$/, 'Financeiro: e o cartão diz que é de qualquer data');
  // Mostrando só as receitas, a lista fica vazia, mas o cartão continua somando as despesas em aberto.
  await page.selectOption('#lc-tipo', 'receita');
  await espera('#tabela-lancamentos tbody', /^Nenhum lançamento com esse filtro\.$/, 'Financeiro: só receitas em aberto: nenhuma');
  await espera('[data-lk="a_pagar"]', /^R\$ 580,60$/, 'Financeiro: o cartão "A pagar" não muda com o filtro de tipo');
  await page.selectOption('#lc-tipo', '');
  await page.selectOption('#lc-situacao', '');
  // "Próximos 30 dias" (de hoje a daqui a 29 dias): pega a parcela de daqui a 25 e avisa da outra.
  await page.selectOption('#periodo', 'prox30');
  await espera('[data-lc-contagem]', new RegExp('^1 lançamento, vencimento de ' + br(hoje) + ' a ' + br(maisDias(hoje, 29)) + '$'), 'Período "Próximos 30 dias": de hoje a daqui a 29 dias');
  await espera('[data-lc-fora-texto]', /^Há mais 1 conta em aberto com vencimento fora deste período\.$/, 'Próximos 30 dias: avisa da parcela que vence depois');
  // "Mês que vem": do dia 1 ao último dia do mês seguinte.
  await page.selectOption('#periodo', 'mes-que-vem');
  const [anoDeHoje, mesDeHoje] = hoje.split('-').map(Number);
  const seguinte = mesDeHoje === 12 ? [anoDeHoje + 1, 1] : [anoDeHoje, mesDeHoje + 1];
  const doisDigitos = n => String(n).padStart(2, '0');
  const mesSeguinte = doisDigitos(seguinte[1]) + '/' + seguinte[0];
  await espera('[data-lc-contagem]', new RegExp('vencimento de 01/' + mesSeguinte + ' a ' + doisDigitos(new Date(seguinte[0], seguinte[1], 0).getDate()) + '/' + mesSeguinte + '$'), 'Período "Mês que vem": o mês seguinte inteiro');
  // Resposta atrasada não cobre a tela: o pedido de "Este mês" é segurado por 0,7 s e, nesse meio
  // tempo, o período muda para "Próximos 30 dias". Tem de ficar na tela o último período escolhido.
  await page.selectOption('#periodo', 'mes');
  await espera('[data-lc-contagem]', new RegExp('vencimento de 01/' + br(hoje).slice(3) + ' a '), 'Período de volta em "Este mês"');
  const fimDoMes = hoje.slice(0, 8) + doisDigitos(new Date(anoDeHoje, mesDeHoje, 0).getDate());
  const pedidoDoMes = u => u.pathname === '/api/financeiro/lancamentos' && u.searchParams.get('inicio') === hoje.slice(0, 8) + '01' && u.searchParams.get('fim') === fimDoMes;
  await page.route(pedidoDoMes, async rota => { await new Promise(pronto => setTimeout(pronto, 700)); await rota.continue(); });
  await page.selectOption('#lc-tipo', 'despesa'); // carga de "Este mês": vai chegar atrasada
  await page.selectOption('#periodo', 'prox30'); // carga mais nova, que chega antes
  await page.waitForTimeout(1300);
  await page.unroute(pedidoDoMes);
  confere('Resposta atrasada de outro período não cobre a tela', new RegExp('vencimento de ' + br(hoje) + ' a ' + br(maisDias(hoje, 29)) + '$').test(await texto('[data-lc-contagem]')), await texto('[data-lc-contagem]'));
  await page.selectOption('#lc-tipo', '');
  await page.selectOption('#periodo', 'datas');
  confere('Período: ao escolher datas, vem do dia 1 até hoje, em dia/mês/ano', (await page.inputValue('#pd-inicio')) === '01' + br(hoje).slice(2) && (await page.inputValue('#pd-fim')) === br(hoje), (await page.inputValue('#pd-inicio')) + ' a ' + (await page.inputValue('#pd-fim')));
  await page.fill('#pd-inicio', br(maisDias(hoje, -40))); await page.fill('#pd-fim', br(maisDias(hoje, 70)));
  await page.dispatchEvent('#pd-fim', 'change');
  await esperaLinha('#tabela-lancamentos', 'parcela 001', /NF 123 de FORNECEDOR FICTICIO DE TESTE LTDA, parcela 001 Compra de mercadorias para revenda · da nota de compra.*Despesa 290,30 Em aberto Dar baixa Alterar$/, 'Financeiro: conta da nota, sem botão de cancelar');
  await espera('[data-lk="a_pagar"]', /^R\$ 580,60$/, 'Financeiro: a pagar = as duas parcelas da nota');
  // Novo lançamento: campos obrigatórios e despesa em aberto.
  await page.keyboard.press('F3'); await page.waitForSelector('#dlg-lancamento[open]');
  await page.click('#form-lancamento button[type="submit"]');
  await espera('#form-lancamento .msg-form', /Escolha a categoria/, 'Lançamento: exige a categoria');
  async function lancar(tipo, categoria, descricao, valor, vencimento, opcoes) {
    const o = opcoes || {};
    if (!(await page.$('#dlg-lancamento[open]'))) { await page.keyboard.press('F3'); await page.waitForSelector('#dlg-lancamento[open]'); }
    await page.selectOption('#lc-tipo-novo', tipo);
    await page.selectOption('#lc-categoria', { label: categoria });
    await page.fill('#lc-descricao', descricao); await page.fill('#lc-valor', valor); await page.fill('#lc-vencimento', br(vencimento));
    await page.fill('#lc-competencia', o.competencia ? br(o.competencia) : '');
    if (o.forma) { await page.check('#form-lancamento [name="ja_pago"]'); await page.selectOption('#lc-forma', o.forma); }
    await page.click('#form-lancamento button[type="submit"]');
    await page.waitForFunction(() => !document.querySelector('#dlg-lancamento').open);
  }
  // Datas: digitando só os números, as barras entram sozinhas; data que não existe é recusada.
  await page.selectOption('#lc-categoria', { label: 'Aluguel' }); await page.fill('#lc-descricao', 'x'); await page.fill('#lc-valor', '1,00');
  await page.fill('#lc-vencimento', ''); await page.type('#lc-vencimento', '31022026');
  confere('Data: as barras entram sozinhas', (await page.inputValue('#lc-vencimento')) === '31/02/2026', await page.inputValue('#lc-vencimento'));
  await page.click('#form-lancamento button[type="submit"]');
  await espera('#form-lancamento .msg-form', /Digite o vencimento com dia, mês e ano/, 'Data: 31 de fevereiro é recusado');
  await lancar('despesa', 'Aluguel', 'Aluguel da loja (teste)', '1.500,00', maisDias(hoje, 3), { competencia: hoje });
  await torrada(/Despesa de R\$ 1\.500,00 lançada\./, 'Lançamento: despesa em aberto');
  await esperaLinha('#tabela-lancamentos', 'Aluguel da loja', /Aluguel · competência \d\d\/\d\d\/\d{4} Despesa 1\.500,00 Em aberto Dar baixa Alterar Cancelar/, 'Lançamento: aparece em aberto, com a competência');
  await lancar('despesa', 'Energia elétrica', 'Conta de luz (teste)', '300,00', hoje, { forma: 'pix' });
  await esperaLinha('#tabela-lancamentos', 'Conta de luz', new RegExp('Despesa 300,00 Pago ' + diaMes(hoje) + ' Desfazer baixa'), 'Lançamento: despesa já paga');
  await page.keyboard.press('F3'); await page.waitForSelector('#dlg-lancamento[open]');
  await page.selectOption('#lc-tipo-novo', 'receita');
  await espera('[data-rotulo-pago]', /^Já foi recebido$/, 'Lançamento: na receita o texto muda para "recebido"');
  const categoriasDeReceita = await page.locator('#lc-categoria option').allTextContents();
  confere('Lançamento: receita só oferece categorias de receita', categoriasDeReceita.join(' | ') === '— escolha — | Aporte dos sócios e empréstimos | Outras receitas | Outras vendas (fora do caixa)', categoriasDeReceita.join(' | '));
  await lancar('receita', 'Outras receitas', 'Venda de caixas vazias (teste)', '40,00', hoje, { forma: 'dinheiro' });
  await torrada(/Receita de R\$ 40,00 lançada\./, 'Lançamento: receita recebida');
  await esperaLinha('#tabela-lancamentos', 'Venda de caixas', new RegExp('Receita 40,00 Recebido ' + diaMes(hoje)), 'Lançamento: receita aparece como recebida');
  // Dar baixa pela lista.
  await lancar('despesa', 'Embalagens e descartáveis', 'Copos (teste)', '25,00', hoje);
  await naLinha('#tabela-lancamentos', 'Copos (teste)').getByRole('button', { name: /^Dar baixa/ }).click();
  await page.waitForSelector('#dlg-baixa[open]');
  await espera('#dlg-baixa h2', /^Marcar como pago$/, 'Baixa: título da despesa');
  confere('Baixa: o dia sugerido é hoje, em dia/mês/ano', (await page.inputValue('#bx-data')) === br(hoje), await page.inputValue('#bx-data'));
  await page.selectOption('#bx-forma', 'dinheiro'); await page.click('#form-baixa button[type="submit"]');
  await torrada(/Copos \(teste\): pago em \d\d\/\d\d\/\d{4}\./, 'Baixa: feita');
  await esperaLinha('#tabela-lancamentos', 'Copos (teste)', /Despesa 25,00 Pago \d\d\/\d\d Desfazer baixa/, 'Baixa: a conta aparece paga');
  // Vencida, alterada e cancelada.
  await lancar('despesa', 'Internet e telefone', 'Internet (teste)', '99,90', maisDias(hoje, -2));
  await esperaLinha('#tabela-lancamentos', 'Internet (teste)', /Despesa 99,90 Vencido/, 'Lançamento: conta atrasada aparece vencida');
  await espera('[data-lk="a_pagar_m"]', /^R\$ 99,90 já venceu$/, 'Financeiro: o cartão diz quanto já venceu');
  await naLinha('#tabela-lancamentos', 'Internet (teste)').getByRole('button', { name: /^Alterar/ }).click();
  await page.waitForSelector('#dlg-lancamento[open]');
  await espera('#dlg-lancamento h2', /^Alterar lançamento$/, 'Alterar: abre com os dados');
  confere('Alterar: o tipo não muda', await page.isDisabled('#lc-tipo-novo'));
  await page.fill('#lc-valor', '89,90'); await page.click('#form-lancamento button[type="submit"]');
  await torrada(/Despesa de R\$ 89,90 alterada\./, 'Alterar: salvo');
  await naLinha('#tabela-lancamentos', 'Internet (teste)').getByRole('button', { name: /^Cancelar/ }).click();
  await confirmar(/fica guardado como cancelado, com o seu nome/, 'Cancelar: avisa que não é apagado');
  await torrada(/Lançamento cancelado\./, 'Cancelar: feito');
  await page.waitForFunction(() => !Array.from(document.querySelectorAll('#tabela-lancamentos tbody tr')).some(l => l.textContent.includes('Internet (teste)')));
  await page.selectOption('#lc-situacao', 'cancelado');
  // Dois cancelados: a internet e a conta da nota 140 (cancelada pelo estorno).
  await page.waitForFunction(() => document.querySelectorAll('#tabela-lancamentos tbody tr').length === 2);
  await esperaLinha('#tabela-lancamentos', 'Internet (teste)', /89,90 Cancelado$/, 'Cancelados: a internet, sem botões');
  await esperaLinha('#tabela-lancamentos', 'NF 140', /268,20 Cancelado$/, 'Cancelados: a conta da nota estornada');
  await page.selectOption('#lc-situacao', '');
  // Desfazer a baixa e baixar de novo.
  await naLinha('#tabela-lancamentos', 'Conta de luz').getByRole('button', { name: /^Desfazer/ }).click();
  await confirmar(/volta a ficar em aberto/, 'Desfazer baixa: confirmação');
  await esperaLinha('#tabela-lancamentos', 'Conta de luz', /300,00 Em aberto Dar baixa Alterar Cancelar/, 'Desfazer baixa: voltou a ficar em aberto');
  await naLinha('#tabela-lancamentos', 'Conta de luz').getByRole('button', { name: /^Dar baixa/ }).click();
  await page.waitForSelector('#dlg-baixa[open]'); await page.selectOption('#bx-forma', 'pix'); await page.click('#form-baixa button[type="submit"]');
  await esperaLinha('#tabela-lancamentos', 'Conta de luz', /300,00 Pago/, 'Baixa refeita');
  // Totais do período: a pagar 1.500,00 + 580,60; pago 300,00 + 25,00; recebido 40,00.
  await espera('[data-lk="a_pagar"]', /^R\$ 2\.080,60$/, 'Financeiro: a pagar = aluguel + parcelas da nota');
  await espera('[data-lk="a_pagar_m"]', /^nada vencido no período$/, 'Financeiro: nada vencido depois do cancelamento');
  await espera('[data-lk="pago"]', /^R\$ 325,00$/, 'Financeiro: pago = luz + copos');
  await espera('[data-lk="recebido"]', /^R\$ 40,00$/, 'Financeiro: recebido');
  await espera('[data-lk="a_receber"]', /^R\$ 0,00$/, 'Financeiro: nada a receber');
  await espera('[data-lc-contagem]', /^6 lançamentos, vencimento de /, 'Financeiro: seis lançamentos no período');
  await page.selectOption('#lc-tipo', 'receita');
  await page.waitForFunction(() => document.querySelectorAll('#tabela-lancamentos tbody tr').length === 1);
  await espera('[data-lk="a_pagar"]', /^R\$ 2\.080,60$/, 'Financeiro: os cartões não mudam quando a lista é filtrada');
  await page.selectOption('#lc-tipo', '');
  await medir('financeiro-contas');

  // ------------------------------------------------------------------ 7) fluxo de caixa de hoje
  // Entrou: vendas 20,00 + 66,50 + 10,30 + 6,00 = 102,80; + 40,00 recebidos = 142,80.
  // Saiu: luz 300,00 + copos 25,00 = 325,00. Saldo: 142,80 - 325,00 = -182,20.
  await page.click('[data-aba="fluxo"]');
  await page.selectOption('#periodo', 'hoje');
  await espera('[data-fk="entradas"]', /^R\$ 142,80$/, 'Fluxo: entrou');
  await espera('[data-fk="entradas_m"]', /^vendas R\$ 102,80 \+ outros recebimentos R\$ 40,00$/, 'Fluxo: de onde veio o que entrou');
  await espera('[data-fk="saidas"]', /^R\$ 325,00$/, 'Fluxo: saiu');
  await espera('[data-fk="saldo"]', /^-R\$ 182,20$/, 'Fluxo: saldo do dia');
  confere('Fluxo: saldo negativo em vermelho', await page.evaluate(() => document.querySelector('[data-fk="saldo"]').classList.contains('negativo')));
  await espera('[data-fk="aberto_m"]', /^nada vencido$/, 'Fluxo: nada vencido');
  await esperaLinha('#tabela-fluxo', 'hoje', /102,80 40,00 325,00 -182,20 -182,20 0,00 0,00$/, 'Fluxo: a linha de hoje');
  await esperaLinha('#tabela-fluxo', 'Total', /Total 102,80 40,00 325,00 -182,20 0,00 0,00$/, 'Fluxo: a linha de total');
  await espera('[data-fluxo-nota]', /Crédito R\$ 10,30/, 'Fluxo: recebido no crédito');
  await espera('[data-fluxo-nota]', /Dinheiro R\$ 26,00/, 'Fluxo: recebido em dinheiro (20,00 + 6,00)');
  await espera('[data-fluxo-nota]', /Pix R\$ 66,50/, 'Fluxo: recebido no Pix');
  await medir('financeiro-fluxo');

  // ------------------------------------------------------------------ 8) DRE de hoje
  // Receita bruta: 20,00 + 74,95 + 10,00 + 6,00 = 110,95; + acréscimo do crédito 0,30 = 111,25.
  // Descontos: 4,95 + 3,50 do Pix = 8,45. Receita líquida: 102,80.
  // CMV: itens 9,12 + 30,47 + 4,56 = 44,15; + copos 25,00 = 69,15 (parcial: a água não tem custo).
  // Lucro bruto: 33,65. Despesas: aluguel 1.500,00 + luz 300,00. Outras receitas: 40,00.
  // Resultado: 33,65 - 1.800,00 + 40,00 = -1.726,35.
  await page.click('[data-aba="dre"]');
  const dre = [
    ['Receita bruta', /^Receita bruta 111,25$/],
    ['Vendas no caixa', /^Vendas no caixa 110,95$/],
    ['Acréscimos das formas', /^Acréscimos das formas de pagamento 0,30$/],
    ['Descontos concedidos', /^\(−\) Descontos concedidos -8,45$/],
    ['Descontos na venda', /^Descontos na venda -4,95$/],
    ['Descontos das formas', /^Descontos das formas de pagamento -3,50$/],
    ['= Receita líquida', /^= Receita líquida 102,80 100,0%$/],
    ['(CMV)', /^\(−\) Custo das mercadorias vendidas \(CMV\) parcial -69,15 67,3%$/],
    ['Custo dos itens vendidos', /^Custo dos itens vendidos -44,15$/],
    ['Embalagens e descartáveis', /^Embalagens e descartáveis -25,00$/],
    ['= Lucro bruto', /^= Lucro bruto parcial 33,65 32,7%$/],
    ['Despesas operacionais', /^\(−\) Despesas operacionais -1\.800,00 1751,0%$/],
    ['Aluguel', /^Aluguel -1\.500,00$/],
    ['Energia elétrica', /^Energia elétrica -300,00$/],
    ['(+) Outras receitas', /^\(\+\) Outras receitas 40,00 38,9%$/],
    ['= Resultado do período', /^= Resultado do período parcial -1\.726,35 -1679,3%$/],
  ];
  for (const [contem, regex] of dre) await esperaLinha('#tabela-dre', contem, regex, 'DRE: ' + contem);
  await espera('[data-dre-avisos]', /1 item\(ns\) vendido\(s\), somando R\$ 6,00, estão sem custo gravado \(Água de teste\)/, 'DRE: avisa o que foi vendido sem custo');
  await espera('[data-dk="receita_liquida"]', /^R\$ 102,80$/, 'DRE: cartão da receita líquida');
  await espera('[data-dk="lucro_bruto_m"]', /^32,7% da receita líquida \(parcial\)$/, 'DRE: cartão do lucro bruto diz que é parcial');
  await espera('[data-dk="resultado"]', /^-R\$ 1\.726,35$/, 'DRE: cartão do resultado');
  await espera('[data-dk="vendas"]', /^4$/, 'DRE: quatro vendas no período');
  await medir('financeiro-dre');

  // ------------------------------------------------------------------ 9) rentabilidade de hoje
  // Venda 2: os 66,50 divididos na proporção 45,00 : 29,95 = 39,93 e 26,57.
  // Picolé: 20,00 + 39,93 + 10,30 = 70,23; custo 16 x 2,28 = 36,48; margem 33,75 (48,1%).
  // Sorvete: 26,57; custo 0,5 x 15,34 = 7,67; margem 18,90 (71,1%). Água: 6,00, sem custo.
  // Com custo: receita 96,80; custo 44,15; margem 52,65 (54,4%).
  await page.click('[data-aba="rentabilidade"]');
  await esperaLinha('#tabela-rentabilidade', 'Picolé de teste', /^1 Picolé de teste 16 UN 70,23 36,48 33,75 48,1%$/, 'Rentabilidade: picolé');
  await esperaLinha('#tabela-rentabilidade', 'Sorvete de teste', /^2 Sorvete de teste por quilo 0,500 KG 26,57 7,67 18,90 71,1%$/, 'Rentabilidade: sorvete');
  await esperaLinha('#tabela-rentabilidade', 'Água de teste', /^3 Água de teste 2 UN 6,00 — — —$/, 'Rentabilidade: água sem custo não ganha margem inventada');
  await esperaLinha('#tabela-rentabilidade', 'Sem custo gravado na venda', /^Sem custo gravado na venda \(1 produto\): fora da margem 6,00 — — —$/, 'Rentabilidade: o que ficou fora da margem');
  await esperaLinha('#tabela-rentabilidade', 'Total dos produtos com custo', /^Total dos produtos com custo 96,80 44,15 52,65 54,4%$/, 'Rentabilidade: total só de quem tem custo');
  await espera('[data-rent-nota]', /^Total vendido no período: R\$ 102,80\./, 'Rentabilidade: o total vendido fecha com o fluxo de caixa');
  await medir('financeiro-rentabilidade');

  // ------------------------------------------------------------------ 10) período sem nada: "—" e o motivo
  await page.selectOption('#periodo', 'datas');
  await page.fill('#pd-inicio', br(maisDias(hoje, -400))); await page.fill('#pd-fim', br(maisDias(hoje, -390)));
  await page.dispatchEvent('#pd-fim', 'change');
  await espera('#tabela-rentabilidade tbody', /^Sem dados: sem vendas no período \(/, 'Período vazio: rentabilidade diz o motivo');
  await page.click('[data-aba="dre"]');
  await espera('[data-dk="receita_liquida"]', /^—$/, 'Período vazio: DRE sem número inventado');
  await espera('#tabela-dre tbody', /Sem dados: sem vendas nem lançamentos de resultado no período/, 'Período vazio: DRE diz o motivo');
  confere('Período vazio: nenhuma linha do DRE tem valor', await page.evaluate(() => Array.from(document.querySelectorAll('#tabela-dre tbody tr td:nth-child(2)')).every(td => td.textContent === '—')));
  await page.click('[data-aba="fluxo"]');
  await espera('[data-fk="entradas"]', /^—$/, 'Período vazio: fluxo sem número inventado');
  await espera('[data-fk="entradas_m"]', /^Sem dados: sem vendas nem pagamentos no período\.$/, 'Período vazio: fluxo diz o motivo');
  await page.fill('#pd-inicio', br(maisDias(hoje, 5))); await page.dispatchEvent('#pd-inicio', 'change');
  await espera('#tabela-fluxo tbody', /A data final é anterior à data inicial/, 'Período invertido: a tela mostra o erro do servidor');
  await page.selectOption('#periodo', 'mes');

  // ------------------------------------------------------------------ 11) categorias
  await page.click('[data-aba="categorias"]');
  confere('Categorias: o período some (não se aplica)', await page.isHidden('[data-periodo]'));
  await espera('[data-cat-contagem]', /^17 categorias$/, 'Categorias: o plano de contas inicial');
  await page.fill('#cat-nome', 'aluguel'); await page.keyboard.press('F10');
  await espera('#form-categoria .msg-form', /Já existe a categoria “Aluguel”/, 'Categorias: nome repetido é recusado');
  await page.fill('#cat-nome', 'Marketing (teste)'); await page.keyboard.press('F10');
  await torrada(/Categoria Marketing \(teste\) salva\./, 'Categorias: nova categoria');
  await espera('[data-cat-contagem]', /^18 categorias$/, 'Categorias: agora são 18');
  await naLinha('#tabela-categorias', 'Marketing (teste)').getByRole('button').click();
  await page.uncheck('#form-categoria [name="ativo"]'); await page.keyboard.press('F10');
  await espera('[data-cat-contagem]', /^17 categorias$/, 'Categorias: a inativa sai da lista');
  await page.check('#cat-inativas');
  await esperaLinha('#tabela-categorias', 'Marketing (teste)', /Despesas operacionais Inativa/, 'Categorias: "mostrar inativas" traz de volta');
  await medir('financeiro-categorias');
  // Os menus do topo levam direto à aba.
  await page.click('.menu-botao:text("Financeiro")'); await page.click('.submenu a[href="/financeiro#dre"]');
  await page.waitForFunction(() => document.querySelector('[data-aba="dre"]').classList.contains('ativa'));
  confere('Menu Financeiro › DRE abre a aba do DRE', await page.isVisible('#tabela-dre'));

  // ------------------------------------------------------------------ 12) operador comum
  const criado = await api('POST', '/api/operadores', { nome: 'Caixa de Teste', login: 'caixa', senha: senhaCaixa, perfil: 'operador' });
  confere('operador comum criado', criado.status === 201, criado.status);
  await api('POST', '/api/sair');
  await page.goto(base + '/');
  await page.selectOption('#lg-operador', 'caixa');
  await page.fill('#lg-senha', senhaCaixa); await page.keyboard.press('Enter');
  await page.waitForURL(base + '/inicio');
  for (const tela of ['/estoque', '/entrada-nf', '/financeiro']) {
    await page.goto(base + tela);
    confere('operador comum não abre ' + tela, new URL(page.url()).pathname === '/inicio', page.url());
  }
  await torrada(/Essa tela é só para o gerente\./, 'operador comum: aviso de tela do gerente');
  for (const caminho of ['/api/estoque', '/api/compras', '/api/financeiro/dre', '/api/financeiro/lancamentos']) {
    const r = await api('GET', caminho);
    confere('operador comum não lê ' + caminho, r.status === 403, r.status);
  }
  confere('operador comum vê Estoque, Entrada de NF e Financeiro trancados', (await page.locator('.lateral button.item.em-breve .cadeado').count()) >= 5);
  await medir('inicio-operador-comum');

  await b.close();
  console.log('');
  console.log(conferencias + ' conferências feitas.');
  console.log(erros.length ? 'ERROS DO NAVEGADOR:\n' + erros.join('\n') : 'Nenhum erro de JavaScript, de rede ou do servidor (5xx).');
  console.log(falhas.length ? 'FALHAS (' + falhas.length + '): ' + falhas.join(' | ') : 'Todas as conferências passaram.');
  process.exit(falhas.length || erros.length ? 1 : 0);
})().catch(e => { console.error('ROTEIRO INTERROMPIDO: ' + e.message); process.exit(2); });

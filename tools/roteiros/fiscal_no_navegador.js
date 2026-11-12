// Roteiro da aba Configurações → Fiscal (NFC-e), feito no navegador como o dono da loja faria:
// dados da loja e da empresa, certificado digital A1, CSC, numeração, dados fiscais dos produtos
// (um por um e por categoria), contador, a lista "o que falta para emitir" e a remoção do
// certificado. Esta versão NÃO emite NFC-e; o roteiro confere que os dados ficam prontos e que
// os segredos (senha do certificado e código do CSC) nunca voltam para a tela.
//
// Os certificados são FICTÍCIOS, gerados na hora por tools/roteiros/certificado_ficticio.py
// (autoassinados, não valem para nada). A senha e os códigos CSC são sorteados a cada execução.
//
// Para rodar (precisa do Node.js com o pacote "playwright" e do Python do projeto):
//   1. suba o servidor com um banco NOVO:
//        MOLEKA_PDV_DADOS=/pasta/vazia python main.py --sem-janela --porta 8795
//   2. em outro terminal:
//        node tools/roteiros/fiscal_no_navegador.js 8795 /pasta/dos/prints
//
// O roteiro termina com código 0 quando tudo passa; os prints ficam na pasta dada.
const { chromium } = require('playwright');
const { execFileSync } = require('child_process');
const path = require('path'); const fs = require('fs'); const crypto = require('crypto');
const LARGURA = 1366, ALTURA = Number(process.argv[4] || 697);
const PYTHON = process.env.PYTHON || 'python3';
const RAIZ = path.resolve(__dirname, '..', '..');
const CNPJ = '11222333000181'; // fictício, com os dígitos verificadores certos

(async () => {
  const porta = process.argv[2]; const saida = path.resolve(process.argv[3]);
  fs.mkdirSync(saida, { recursive: true });
  const base = 'http://127.0.0.1:' + porta;
  const senhaGerente = 'g' + crypto.randomBytes(5).toString('hex');
  const senhaCertificado = 'cert-' + crypto.randomBytes(6).toString('hex');
  const cscHomologacao = 'HOMOLOG' + crypto.randomBytes(9).toString('hex').toUpperCase();
  const cscProducao = 'PRODUC' + crypto.randomBytes(9).toString('hex').toUpperCase();
  const SEGREDOS = [senhaCertificado, cscHomologacao, cscProducao];

  // Os certificados fictícios: o da loja, o de outra empresa e um vencido.
  const pastaCert = path.join(saida, 'certificados-ficticios');
  fs.rmSync(pastaCert, { recursive: true, force: true });
  const gerar = (nome, cnpj, dias) => execFileSync(PYTHON, [path.join(RAIZ, 'tools/roteiros/certificado_ficticio.py'), path.join(pastaCert, nome), senhaCertificado, cnpj, String(dias)]).toString().trim();
  const certLoja = gerar('empresa-ficticia.pfx', CNPJ, 365);
  const certOutra = gerar('outra-empresa.pfx', '11444777000161', 365);
  const certVencido = gerar('vencido.pfx', CNPJ, -3);

  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: LARGURA, height: ALTURA }, locale: 'pt-BR' });
  const page = await ctx.newPage();
  const erros = []; const falhas = []; const respostas = [];
  let passo = 0; let conferencias = 0;
  page.on('pageerror', e => erros.push('pageerror: ' + e.message));
  // O navegador escreve no console toda resposta 4xx; as esperadas são conferidas no roteiro.
  page.on('console', m => { if (m.type() === 'error' && !/status of (401|403|404|409|422)/.test(m.text())) erros.push('console: ' + m.text()); });
  page.on('requestfailed', r => erros.push('requestfailed: ' + r.url()));
  page.on('response', r => {
    if (r.status() >= 500) erros.push(r.status() + ': ' + r.url());
    if (r.url().includes('/api/')) respostas.push(r.text().then(t => ({ url: r.url(), texto: t })).catch(() => ({ url: r.url(), texto: '' })));
  });

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
  async function foto(nome) {
    passo += 1;
    await page.waitForTimeout(350);
    await page.screenshot({ path: path.join(saida, String(passo).padStart(2, '0') + '-' + nome + '.png') });
  }
  async function medir(nome) {
    await page.waitForTimeout(300);
    const m = await page.evaluate(() => {
      const miolo = document.querySelector('.conteudo');
      const principal = document.querySelector('.cfg.fiscal:not([hidden]) > .principal');
      return {
        h: document.documentElement.scrollHeight, w: document.documentElement.scrollWidth,
        mh: miolo ? miolo.scrollHeight - miolo.clientHeight : 0, mw: miolo ? miolo.scrollWidth - miolo.clientWidth : 0,
        ph: principal ? principal.scrollHeight - principal.clientHeight : 0,
      };
    });
    confere('cabe em ' + LARGURA + 'x' + ALTURA + ' sem rolar a página: ' + nome, m.h <= ALTURA && m.w <= LARGURA && m.mh <= 0 && m.mw <= 0, 'página ' + m.w + 'x' + m.h + ', sobra do miolo ' + m.mw + 'x' + m.mh);
    confere('o formulário cabe no cartão, sem rolar: ' + nome, m.ph <= 0, 'sobra ' + m.ph + ' px');
    await foto(nome);
  }
  const api = (metodo, caminho, corpo) => page.evaluate(async ([m, c, d]) => {
    const r = await fetch(c, { method: m, headers: d ? { 'Content-Type': 'application/json' } : {}, body: d ? JSON.stringify(d) : undefined });
    let j = null; try { j = await r.json(); } catch (e) { j = null; }
    return { status: r.status, dados: j };
  }, [metodo, caminho, corpo || null]);
  async function criar(caminho, corpo) { const r = await api('POST', caminho, corpo); if (r.status !== 201) throw new Error(caminho + ': ' + r.status + ' ' + JSON.stringify(r.dados)); return r.dados; }
  const situacao = chave => page.getAttribute('[data-fs-pendencias] li[data-chave="' + chave + '"]', 'class');
  const bola = parte => page.getAttribute('[data-bola="' + parte + '"]', 'class');
  async function irPara(parte) { await page.click('[data-passo="' + parte + '"]'); await page.waitForSelector('[data-secao="' + parte + '"]:not([hidden])'); }
  async function confirmar(regexTitulo, nome, botao) {
    await page.waitForSelector('#dlg-confirmar[open]');
    confere(nome, regexTitulo.test(await texto('#dlg-confirmar h2')), await texto('#dlg-confirmar h2') + ' / ' + await texto('#dlg-confirmar [data-texto]'));
    await page.click(botao === 'nao' ? '#dlg-confirmar [data-fechar-dialogo]' : '#dlg-confirmar button[type="submit"]');
  }
  async function semSegredosNaTela(nome) {
    const html = await page.evaluate(() => document.documentElement.outerHTML + ' ' + Array.from(document.querySelectorAll('input')).map(i => i.value).join(' '));
    const achados = SEGREDOS.filter(s => html.includes(s));
    confere('nenhum segredo na tela (senha do certificado, CSC): ' + nome, achados.length === 0, achados.length ? 'achou ' + achados.length : 'nenhum');
  }

  // ------------------------------------------------------------------ 1) primeiro acesso
  await page.goto(base + '/');
  await page.fill('#ci-nome', 'Gerente de Teste');
  await page.fill('#ci-senha', senhaGerente); await page.fill('#ci-senha2', senhaGerente);
  await page.keyboard.press('Enter');
  await page.waitForURL(base + '/inicio');
  const bloco = page.locator('.grade a.tile', { hasText: 'Fiscal / NFC-e' });
  confere('Início: o bloco Fiscal / NFC-e abre os dados fiscais (não é mais "em breve")', (await bloco.count()) === 1 && (await bloco.getAttribute('href')) === '/configuracoes#fiscal', await bloco.count() ? await bloco.getAttribute('href') : 'sem o bloco');
  const itemMenu = await page.$$eval('.menu a', links => links.filter(a => /Dados fiscais e certificado A1/.test(a.textContent)).map(a => a.getAttribute('href')));
  confere('menu Fiscal: "Dados fiscais e certificado A1" leva à aba Fiscal', itemMenu.length === 1 && itemMenu[0] === '/configuracoes#fiscal', JSON.stringify(itemMenu));
  await bloco.click();
  await page.waitForSelector('[data-fs-pendencias] li');

  // ------------------------------------------------------------------ 2) aba em branco
  confere('a aba Fiscal (NFC-e) abre selecionada', (await page.getAttribute('[data-aba="fiscal"]', 'aria-selected')) === 'true');
  await espera('.passos .nao-emite', /Esta versão ainda não emite NFC-e/, 'aviso: esta versão ainda não emite NFC-e');
  confere('começa na parte Empresa, com o endereço #fiscal-empresa', page.url().endsWith('#fiscal-empresa') && !(await page.isHidden('[data-secao="empresa"]')), page.url());
  const preenchidos = await page.$$eval('#form-fs-empresa input, #form-fs-empresa select', campos => campos.filter(c => c.value !== '').length);
  confere('dados fiscais começam em branco (nada de exemplo preenchido)', preenchidos === 0, preenchidos + ' campo(s)');
  await espera('[data-fs-loja]', /^Razão social: — · CNPJ — · IE — Endereço: —$/, 'resumo da loja em branco, com "—"');
  await espera('[data-fs-resumo]', /^5 itens faltam \(em vermelho\); 5 pedem atenção \(em amarelo\)\.$/, 'o que falta: 5 itens em vermelho e 5 em amarelo');
  confere('a lista tem os 10 itens', (await page.$$('[data-fs-pendencias] li')).length === 10);
  confere('bolinhas das partes (empresa, certificado, CSC: falta; numeração, produtos, contador: atenção)',
    JSON.stringify(await Promise.all(['empresa', 'certificado', 'csc', 'numeracao', 'produtos', 'contador'].map(bola))) === JSON.stringify(['bola falta', 'bola falta', 'bola falta', 'bola atencao', 'bola atencao', 'bola atencao']),
    JSON.stringify(await Promise.all(['empresa', 'certificado', 'csc', 'numeracao', 'produtos', 'contador'].map(bola))));
  await medir('fiscal-em-branco');

  // ------------------------------------------------------------------ 3) dados da loja e da empresa
  await page.click('.resumo-loja a[href="#loja"]');
  await page.waitForSelector('#form-loja:visible');
  confere('"Mudar em Dados da loja" abre a aba Dados da loja', (await page.getAttribute('[data-aba="loja"]', 'aria-selected')) === 'true');
  await page.fill('#lj-razao', 'Empresa Ficticia de Teste Ltda');
  await page.fill('#lj-cnpj', CNPJ);
  await page.fill('#lj-ie', '111222333444');
  await page.fill('#lj-rua', 'Rua das Flores'); await page.fill('#lj-numero', '100'); await page.fill('#lj-bairro', 'Centro');
  await page.fill('#lj-cidade', 'São Paulo'); await page.selectOption('#lj-uf', 'SP'); await page.fill('#lj-cep', '01001000');
  await page.keyboard.press('F10');
  await torrada(/Dados da loja salvos/, 'dados da loja salvos');
  await page.click('[data-aba="fiscal"]');
  await espera('[data-fs-loja]', /^Empresa Ficticia de Teste Ltda · CNPJ 11\.222\.333\/0001-81 · IE 111222333444 Rua das Flores, 100, Centro, São Paulo\/SP · CEP 01001-000$/, 'voltando à aba Fiscal, o resumo da loja já mostra o que foi salvo');
  confere('item "Dados da empresa" fica pronto', (await situacao('loja')) === 'pend ok', await situacao('loja'));

  await page.selectOption('#fs-crt', '1');
  await page.fill('#fs-municipio', '3304557'); // Rio de Janeiro: não é de SP
  await page.keyboard.press('F10');
  await espera('#form-fs-empresa .msg-form', /é de uma cidade de RJ, mas o estado da loja \(aba Dados da loja\) é SP/, 'código de município de outro estado é recusado');
  await page.fill('#fs-municipio', '3550308');
  await page.fill('#fs-cnae', '4721104');
  await page.selectOption('#fs-credenciada', 'sim');
  confere('o campo "qual sistema" fica escondido enquanto a resposta não é Sim', await page.isHidden('[data-fs-detalhe]'));
  await page.selectOption('#fs-emite', 'sim');
  confere('respondendo que já emite por outro sistema, aparece o campo "qual sistema"', await page.isVisible('[data-fs-detalhe]'));
  await page.fill('#fs-emite-detalhe', 'sistema antigo fictício, série 1, última nota nº 4521');
  await page.keyboard.press('F10');
  await torrada(/Dados fiscais da empresa salvos/, 'dados fiscais da empresa salvos');
  confere('CNAE volta formatado (4721-1/04)', (await page.inputValue('#fs-cnae')) === '4721-1/04', await page.inputValue('#fs-cnae'));
  confere('regime, município e credenciamento ficam prontos', JSON.stringify(await Promise.all(['regime', 'municipio', 'credenciamento'].map(situacao))) === JSON.stringify(['pend ok', 'pend ok', 'pend ok']));
  confere('bolinha da Empresa fica verde', (await bola('empresa')) === 'bola ok', await bola('empresa'));
  await medir('fiscal-empresa-preenchida');

  // ------------------------------------------------------------------ 4) certificado digital
  await page.click('[data-fs-pendencias] li[data-chave="certificado"] button');
  await page.waitForSelector('[data-secao="certificado"]:not([hidden])');
  confere('clicar no item da lista abre a parte certa (certificado)', page.url().endsWith('#fiscal-certificado'), page.url());
  await espera('[data-fs-cert]', /^Nenhum certificado instalado neste computador\.$/, 'sem certificado: a tela diz que não há nenhum');
  await page.click('#form-fs-certificado button[type="submit"]');
  await espera('#form-fs-certificado .msg-form', /Escolha o arquivo do certificado/, 'instalar sem arquivo: pede o arquivo');
  async function instalar(arquivo, senha) {
    if (!(await page.$eval('[data-fs-trocar]', d => d.open))) await page.click('[data-fs-trocar] summary');
    await page.setInputFiles('#fs-arquivo', arquivo);
    await page.fill('#fs-senha', senha);
    await page.click('#form-fs-certificado button[type="submit"]');
  }
  await page.setInputFiles('#fs-arquivo', certOutra);
  await espera('[data-fs-nome-arquivo]', /^outra-empresa\.pfx$/, 'o nome do arquivo escolhido aparece ao lado do botão');
  await instalar(certOutra, senhaCertificado);
  await espera('#form-fs-certificado .msg-form', /Este certificado é do CNPJ 11\.444\.777\/0001-61, mas o CNPJ da loja .* é 11\.222\.333\/0001-81/, 'certificado de outra empresa é recusado');
  confere('a senha não fica no campo depois de tentar', (await page.inputValue('#fs-senha')) === '');
  await instalar(certVencido, senhaCertificado);
  await espera('#form-fs-certificado .msg-form', /Este certificado venceu em \d\d\/\d\d\/\d{4}/, 'certificado vencido é recusado');
  await instalar(certLoja, 'senha-errada-ficticia');
  await espera('#form-fs-certificado .msg-form', /Não deu para abrir o certificado com esta senha/, 'senha errada é recusada');
  await instalar(certLoja, senhaCertificado);
  await torrada(/Certificado instalado: EMPRESA FICTICIA DE TESTE LTDA, válido até \d\d\/\d\d\/\d{4}\./, 'certificado da loja instalado');
  await espera('[data-fs-cert] .dados-cert', /Titular EMPRESA FICTICIA DE TESTE LTDA CNPJ 11\.222\.333\/0001-81 é o da loja Emitido por AC FICTICIA DE TESTE Validade de \d\d\/\d\d\/\d{4} até \d\d\/\d\d\/\d{4} \(36[45] dias para vencer\) Instalado \d\d\/\d\d\/\d{4} às \d\d:\d\d, do arquivo empresa-ficticia\.pfx/, 'dados do certificado instalado na tela');
  confere('depois de instalar: senha e arquivo saem dos campos', (await page.inputValue('#fs-senha')) === '' && (await texto('[data-fs-nome-arquivo]')) === 'Nenhum arquivo escolhido');
  confere('item "Certificado digital A1" fica pronto', (await situacao('certificado')) === 'pend ok', await situacao('certificado'));
  const status = (await api('GET', '/api/status')).dados.certificado;
  confere('indicador do certificado (/api/status): A1, com o titular', status.ok === true && status.texto === 'A1' && /EMPRESA FICTICIA DE TESTE LTDA · válido até/.test(status.motivo), JSON.stringify(status));
  await page.click('[data-fs-testar]');
  await espera('[data-fs-cert-msg]', /O certificado abriu com a senha guardada: válido até \d\d\/\d\d\/\d{4}\./, '"Testar o certificado" abre a cópia guardada com a senha guardada');
  await espera('[data-fs-cert-titulo]', /^Trocar o certificado \(renovação\)$/, 'com certificado instalado, o formulário vira "Trocar o certificado"');
  confere('com certificado instalado, o formulário de troca fica recolhido', !(await page.$eval('[data-fs-trocar]', d => d.open)));
  await semSegredosNaTela('certificado instalado');
  await medir('fiscal-certificado-instalado');
  await instalar(certLoja, senhaCertificado);
  await confirmar(/^Trocar o certificado\?$/, 'trocar o certificado pergunta antes');
  await torrada(/Certificado instalado/, 'certificado trocado');

  // ------------------------------------------------------------------ 5) CSC
  await irPara('csc');
  await espera('[data-csc-situacao="homologacao"]', /^Nenhum código guardado\.$/, 'CSC de homologação: nenhum guardado');
  await page.fill('#fs-csc-h-id', '000001');
  await page.fill('#fs-csc-h', 'CODIGO COM ESPACO');
  await page.keyboard.press('F10');
  await espera('#form-fs-csc .msg-form', /sem espaços no meio/, 'CSC com espaço é recusado');
  confere('o código do CSC fica escondido enquanto se digita', (await page.getAttribute('#fs-csc-h', 'type')) === 'password');
  await page.check('#form-fs-csc [name="mostrar"]');
  confere('"Mostrar o código" deixa ver o que foi digitado', (await page.getAttribute('#fs-csc-h', 'type')) === 'text');
  await page.uncheck('#form-fs-csc [name="mostrar"]');
  await page.fill('#fs-csc-h', cscHomologacao);
  await page.fill('#fs-csc-p-id', '2');
  await page.fill('#fs-csc-p', cscProducao);
  await page.keyboard.press('F10');
  await torrada(/CSC salvo/, 'CSC salvo');
  await espera('[data-csc-situacao="homologacao"]', new RegExp('^Código guardado \\(termina em ' + cscHomologacao.slice(-4) + '\\)\\. Para trocar, digite o novo\\.$'), 'CSC de homologação: só os 4 últimos caracteres voltam');
  await espera('[data-csc-situacao="producao"]', new RegExp('termina em ' + cscProducao.slice(-4)), 'CSC de produção guardado');
  confere('os campos do código ficam vazios depois de salvar', (await page.inputValue('#fs-csc-h')) === '' && (await page.inputValue('#fs-csc-p')) === '');
  confere('CSC de homologação e de produção ficam prontos', (await situacao('csc_homologacao')) === 'pend ok' && (await situacao('csc_producao')) === 'pend ok');
  await semSegredosNaTela('CSC salvo');
  await medir('fiscal-csc-salvo');

  // ------------------------------------------------------------------ 6) numeração
  await irPara('numeracao');
  await espera('[data-fs-outro-sistema]', /já emite NFC-e por outro sistema: sistema antigo fictício, série 1, última nota nº 4521\./, 'numeração lembra o que foi anotado sobre o outro sistema');
  await espera('#tabela-fs-numeracao tbody', /Caixa 01 — \(nenhuma NFC-e registrada por este sistema\)/, 'Caixa 01 sem nenhuma NFC-e registrada');
  confere('numeração pede atenção enquanto não é conferida', (await situacao('numeracao')) === 'pend atencao');
  await page.fill('#tabela-fs-numeracao [name="serie"]', '1a');
  await page.keyboard.press('F10');
  await espera('#form-fs-numeracao .msg-form', /Série e próximo número: só números/, 'série com letra é recusada');
  await page.fill('#tabela-fs-numeracao [name="serie"]', '1');
  await page.fill('#tabela-fs-numeracao [name="proximo"]', '4522');
  await page.keyboard.press('F10');
  await torrada(/Numeração da NFC-e salva/, 'numeração salva');
  await espera('[data-fs-pendencias] li[data-chave="numeracao"]', /Caixa 01: série 1, próxima nota nº 4522\./, 'item da numeração pronto, com a série e o próximo número');
  await medir('fiscal-numeracao');

  // ------------------------------------------------------------------ 7) dados fiscais dos produtos
  const varejo = (await api('GET', '/api/tabelas-preco')).dados.find(t => t.padrao).id;
  const preco = [{ tabela_id: varejo, qtd_min: '1', preco_centavos: 500 }];
  const morango = await criar('/api/produtos', { descricao: 'Picolé fictício de morango', categoria: 'Picolés', ncm: '21050010', precos: preco });
  const limao = await criar('/api/produtos', { descricao: 'Picolé fictício de limão', categoria: 'Picolés', precos: preco });
  await criar('/api/produtos', { descricao: 'Pote fictício de 2 litros', categoria: 'Sorvetes', precos: preco });
  await criar('/api/produtos', { descricao: 'Produto fictício sem categoria', precos: preco });
  await page.goto(base + '/configuracoes#fiscal-produtos');
  await page.waitForSelector('#tabela-fs-categorias tbody tr td button');
  confere('o endereço #fiscal-produtos abre direto a parte Produtos', !(await page.isHidden('[data-secao="produtos"]')));
  await espera('[data-fs-regime]', /^Regime: Simples Nacional\. Use CSOSN, de 3 números/, 'a parte Produtos lembra o que o regime usa (CSOSN)');
  await espera('#tabela-fs-categorias tbody', /^Picolés 2 1 2 2 falta Preencher… Sorvetes 1 1 1 1 falta Preencher… \(sem categoria\) 1 1 1 1 falta Preencher…$/, 'resumo por categoria (produtos, sem NCM, sem CFOP, sem CST/CSOSN)');
  await espera('[data-fs-pendencias] li[data-chave="produtos"]', /Dos 4 produtos ativos: 3 sem NCM, 4 sem CFOP e 4 sem CST\/CSOSN\./, 'item dos produtos diz quantos faltam');
  await medir('fiscal-produtos');
  const linha = nome => page.locator('#tabela-fs-categorias tbody tr', { hasText: nome });
  await linha('Picolés').locator('button').click();
  await page.waitForSelector('#dlg-fs-categoria[open]');
  await espera('#dlg-fs-categoria h2', /^Preencher: Picolés$/, 'diálogo da categoria Picolés');
  await espera('#dlg-fs-categoria [data-texto]', /^2 produtos ativos \(1 sem NCM, 2 sem CFOP, 2 sem CST\/CSOSN\)\.$/, 'o diálogo diz o que falta na categoria');
  await foto('fiscal-dialogo-categoria');
  await page.click('#dlg-fs-categoria button[type="submit"]');
  await espera('#dlg-fs-categoria .msg-form', /Preencha pelo menos um dos campos/, 'sem nenhum campo, pede um');
  await page.fill('#dfc-cfop', '6102');
  await page.click('#dlg-fs-categoria button[type="submit"]');
  await espera('#dlg-fs-categoria .msg-form', /na NFC-e ele começa com 5/, 'CFOP de fora do estado é recusado');
  await page.fill('#dfc-ncm', '2105.00.90'); await page.fill('#dfc-cfop', '5405'); await page.fill('#dfc-cst', '500');
  await page.click('#dlg-fs-categoria button[type="submit"]');
  await torrada(/^2 produtos atualizados\.$/, 'preencher só os vazios: 2 produtos mudaram');
  let lido = (await api('GET', '/api/produtos/' + morango.id)).dados;
  confere('o NCM que o picolé de morango já tinha ficou (só os vazios são preenchidos)', lido.ncm === '21050010' && lido.cfop === '5405' && lido.cst_csosn === '500', JSON.stringify([lido.ncm, lido.cfop, lido.cst_csosn]));
  confere('o picolé de limão ganhou o NCM da categoria', (await api('GET', '/api/produtos/' + limao.id)).dados.ncm === '21050090');
  await linha('Picolés').locator('button').click();
  await page.waitForSelector('#dlg-fs-categoria[open]');
  await page.fill('#dfc-ncm', '21050090');
  await page.check('#dlg-fs-categoria [name="sobrescrever"]');
  await page.click('#dlg-fs-categoria button[type="submit"]');
  await confirmar(/^Trocar os dados fiscais\?$/, 'trocar o que já está preenchido pede confirmação', 'nao');
  await page.waitForSelector('#dlg-fs-categoria[open]');
  confere('desistindo, o diálogo volta com o que foi digitado', (await page.inputValue('#dfc-ncm')) === '21050090' && await page.isChecked('#dlg-fs-categoria [name="sobrescrever"]'));
  await page.click('#dlg-fs-categoria button[type="submit"]');
  await confirmar(/^Trocar os dados fiscais\?$/, 'confirmando a troca');
  await torrada(/^1 produto atualizado\.$/, 'trocar: só o picolé de morango mudou de NCM');
  lido = (await api('GET', '/api/produtos/' + morango.id)).dados;
  confere('o picolé de morango ficou com o NCM novo', lido.ncm === '21050090', lido.ncm);
  for (const nome of ['Sorvetes', '(sem categoria)']) {
    await linha(nome).locator('button').click();
    await page.waitForSelector('#dlg-fs-categoria[open]');
    await page.fill('#dfc-ncm', '21050010'); await page.fill('#dfc-cfop', '5405'); await page.fill('#dfc-cst', '500');
    await page.click('#dlg-fs-categoria button[type="submit"]');
    await torrada(/^1 produto atualizado\.$/, 'categoria ' + nome + ' preenchida');
  }
  await espera('#tabela-fs-categorias tbody', /^Picolés 2 0 0 0 completa Preencher… Sorvetes 1 0 0 0 completa Preencher… \(sem categoria\) 1 0 0 0 completa Preencher…$/, 'todas as categorias completas');
  await espera('[data-fs-pendencias] li[data-chave="produtos"]', /Os 4 produtos ativos têm NCM, CFOP e CST\/CSOSN\./, 'item dos produtos pronto');

  // ------------------------------------------------------------------ 8) contador
  await irPara('contador');
  await page.fill('#fs-ct-nome', 'Contador Fictício de Teste');
  await page.fill('#fs-ct-email', 'contador-sem-arroba');
  await page.keyboard.press('F10');
  await espera('#form-fs-contador .msg-form', /E-mail do contador inválido/, 'e-mail sem @ é recusado');
  await page.fill('#fs-ct-email', 'contador@ficticio.com.br');
  await page.fill('#fs-ct-telefone', '(11) 5555-0199');
  await page.fill('#fs-ct-obs', 'Picolés e potes: CSOSN 500, CFOP 5405.');
  // A tecla Salvar do rodapé salva a parte que está aberta.
  await page.click('.rodape [data-salvar]');
  await torrada(/Contato do contador salvo/, 'a tecla Salvar do rodapé salva o contador');
  await medir('fiscal-contador');

  // ------------------------------------------------------------------ 9) tudo pronto
  await espera('[data-fs-resumo]', /^Os dados estão prontos\. A emissão da NFC-e entra numa próxima versão\.$/, 'com tudo preenchido: dados prontos, e a emissão vem numa próxima versão');
  const bolas = await Promise.all(PASSOS().map(bola));
  confere('todas as bolinhas verdes', bolas.every(c => c === 'bola ok'), JSON.stringify(bolas));
  confere('todos os itens da lista prontos', (await page.$$eval('[data-fs-pendencias] li', l => l.filter(x => !x.classList.contains('ok')).length)) === 0);
  await espera('[data-fs-ambiente]', /^Homologação \(testes, a nota não vale\)$/, 'ambiente: homologação');
  await irPara('empresa');
  await medir('fiscal-tudo-pronto');

  // ------------------------------------------------------------------ 10) cadastro do produto
  await page.goto(base + '/produtos');
  await page.waitForSelector('#form-produto');
  await page.locator('#tabela-produtos tbody tr', { hasText: 'Picolé fictício de limão' }).locator('button', { hasText: 'Alterar' }).click();
  await page.waitForFunction(() => document.querySelector('#form-produto [name="descricao"]').value !== '');
  await page.click('.grupo-fiscal summary');
  await page.waitForTimeout(200);
  await foto('produto-dados-fiscais');
  confere('cadastro do produto: CFOP e origem vêm preenchidos', (await page.inputValue('#p-cfop')) === '5405' && (await page.inputValue('#p-origem')) === '0', (await page.inputValue('#p-cfop')) + ' / ' + (await page.inputValue('#p-origem')));
  const origens = await page.$$eval('#p-origem option', o => o.map(x => x.value).join(''));
  confere('origem é uma lista de 0 a 8', origens === '012345678', origens);
  await page.fill('#p-cfop', '6102');
  await page.keyboard.press('F10');
  await espera('#form-produto .msg-form', /na NFC-e ele começa com 5/, 'cadastro do produto recusa CFOP de fora do estado');
  await page.fill('#p-cfop', '5102');
  await page.selectOption('#p-origem', '2');
  await page.keyboard.press('F10');
  await torrada(/salvo/, 'produto salvo com o CFOP 5102 e a origem 2');
  lido = (await api('GET', '/api/produtos/' + limao.id)).dados;
  confere('o produto ficou com o CFOP e a origem escolhidos', lido.cfop === '5102' && lido.origem === '2', lido.cfop + ' / ' + lido.origem);

  // ------------------------------------------------------------------ 11) remover o certificado
  await page.goto(base + '/configuracoes#fiscal-certificado');
  await page.waitForSelector('[data-fs-remover]');
  await page.click('[data-fs-remover]');
  await confirmar(/^Remover o certificado\?$/, 'remover o certificado pede confirmação');
  await torrada(/Certificado removido deste computador/, 'certificado removido');
  await espera('[data-fs-cert]', /^Nenhum certificado instalado neste computador\.$/, 'depois de remover, não há certificado');
  confere('item do certificado volta a faltar', (await situacao('certificado')) === 'pend falta');
  confere('indicador do certificado volta a "—"', (await api('GET', '/api/status')).dados.certificado.ok === false);

  // ------------------------------------------------------------------ 12) nenhum segredo nas respostas
  const todas = await Promise.all(respostas);
  const comSegredo = todas.filter(r => SEGREDOS.some(s => r.texto.includes(s)));
  confere('nenhuma resposta do sistema trouxe a senha do certificado ou um código CSC (' + todas.length + ' respostas)', comSegredo.length === 0, comSegredo.map(r => r.url).join(', ') || 'nenhuma');

  confere('nenhum erro no navegador', erros.length === 0, erros.join(' | ') || 'nenhum');
  await b.close();
  fs.rmSync(pastaCert, { recursive: true, force: true }); // os certificados fictícios não ficam junto com os prints
  console.log('\n' + conferencias + ' conferências, ' + falhas.length + ' falha(s)');
  process.exit(falhas.length ? 1 : 0);

  function PASSOS() { return ['empresa', 'certificado', 'csc', 'numeracao', 'produtos', 'contador']; }
})().catch(e => { console.error(e); process.exit(2); });

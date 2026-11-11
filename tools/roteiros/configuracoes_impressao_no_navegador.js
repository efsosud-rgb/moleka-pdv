// Roteiro das Configurações, da impressão do cupom, da cópia de segurança e dos relatórios em
// folha comum, feito no navegador como um usuário faria, com os valores esperados calculados à
// mão (ver os comentários).
//
// A impressora é a "impressora de teste" do sistema, que grava cada impressão num arquivo: o
// roteiro abre esses arquivos e confere os bytes que iriam para a térmica. Ele NÃO prova que
// sai papel numa impressora de verdade; isso só o teste na loja mostra.
//
// Para rodar (precisa do Node.js com o pacote "playwright" e do Python do projeto):
//   1. suba o servidor com um banco NOVO e a impressora de teste apontando para uma pasta vazia:
//        MOLEKA_PDV_DADOS=/pasta/vazia MOLEKA_PDV_IMPRESSORA_EM_ARQUIVO=/pasta/da/impressora \
//          python main.py --sem-janela --porta 8793
//   2. em outro terminal:
//        node tools/roteiros/configuracoes_impressao_no_navegador.js 8793 /pasta/dos/prints /pasta/da/impressora
//
// Todos os dados daqui são fictícios, de teste, e as senhas são sorteadas a cada execução. O
// roteiro termina com código 0 quando tudo passa; os prints e os PDFs ficam na pasta dada.
const { chromium } = require('playwright');
const { execFileSync } = require('child_process');
const path = require('path'); const fs = require('fs'); const crypto = require('crypto');
const LARGURA = 1366, ALTURA = Number(process.argv[5] || 697);
const IMPRESSORA = 'Impressora de teste (grava em arquivo)';

(async () => {
  const porta = process.argv[2]; const saida = path.resolve(process.argv[3]); const fila = path.resolve(process.argv[4]);
  fs.mkdirSync(saida, { recursive: true });
  const pastaExtra = path.join(saida, 'pasta-extra'); fs.rmSync(pastaExtra, { recursive: true, force: true }); fs.mkdirSync(pastaExtra);
  const base = 'http://127.0.0.1:' + porta;
  const senhaGerente = 'g' + crypto.randomBytes(5).toString('hex');
  const senhaCaixa = String(1000 + crypto.randomInt(9000));
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: LARGURA, height: ALTURA }, locale: 'pt-BR' });
  // A impressão do Windows não existe no navegador de teste: o roteiro conta as chamadas.
  await ctx.addInitScript(() => { window.__impressoes = 0; window.print = () => { window.__impressoes += 1; }; });
  let page = await ctx.newPage();
  const erros = [];
  const falhas = [];
  let passo = 0; let conferencias = 0;
  function vigiar(p) {
    p.on('pageerror', e => erros.push('pageerror: ' + e.message));
    // O navegador escreve no console toda resposta 4xx; as esperadas são conferidas no roteiro.
    p.on('console', m => { if (m.type() === 'error' && !/status of (401|403|404|409|422)/.test(m.text())) erros.push('console: ' + m.text()); });
    p.on('requestfailed', r => erros.push('requestfailed: ' + r.url()));
    p.on('response', r => { if (r.status() >= 500) erros.push(r.status() + ': ' + r.url()); });
  }
  vigiar(page);

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

  // ---- a "impressora": cada impressão é um arquivo impressao-NNN.bin na pasta da fila
  const impressos = () => (fs.existsSync(fila) && fs.statSync(fila).isDirectory() ? fs.readdirSync(fila).filter(n => /^impressao-\d+\.bin$/.test(n)).sort() : []);
  let esperados = 0; // quantas impressões já deveriam ter saído
  // Espera a impressão seguinte e devolve { bytes, texto } dela (texto lido como CP850).
  async function impresso(nome) {
    esperados += 1;
    for (let i = 0; i < 50 && impressos().length < esperados; i++) await page.waitForTimeout(100);
    const lista = impressos();
    confere(nome + ': saiu 1 impressão (a ' + esperados + 'ª)', lista.length === esperados, lista.length + ' arquivo(s) na fila');
    if (lista.length < esperados) { esperados = lista.length; return { bytes: Buffer.alloc(0), texto: '' }; }
    const arquivo = path.join(fila, lista[esperados - 1]);
    const bytes = fs.readFileSync(arquivo);
    const lido = execFileSync(process.env.PYTHON || 'python3', ['-c', 'import sys; sys.stdout.buffer.write(open(sys.argv[1], "rb").read().decode("cp850").encode("utf-8"))', arquivo]).toString('utf8');
    return { bytes, texto: lido };
  }
  async function nadaImpresso(nome) {
    await page.waitForTimeout(400);
    confere(nome + ': nada foi para a impressora', impressos().length === esperados, impressos().length + ' arquivo(s), esperados ' + esperados);
  }
  const comeca = (bytes, hex) => bytes.subarray(0, hex.length / 2).toString('hex') === hex;
  const termina = (bytes, hex) => bytes.subarray(bytes.length - hex.length / 2).toString('hex') === hex;
  const INICIO = '1b401b7402'; // ESC @ (iniciar) + ESC t 2 (página de código 850)
  const CORTE = '1b45001d21001d564200'; // negrito e tamanho normais + GS V 66 0 (cortar)
  const GAVETA = '1b700019fa'; // ESC p 0 25 250 (pulso da gaveta)
  // A linha do cupom que contém um texto, sem os espaços repetidos.
  // O texto sem os comandos da impressora: gaveta (o byte 0xFA é lido como "·"), iniciar, página
  // de código, negrito, tamanho e corte.
  const semComandos = lido => lido.replace(/\x1bp\x00\x19\u00b7/g, '').replace(/\x1b@/g, '').replace(/\x1b[tE][\x00-\x1f]/g, '').replace(/\x1d![\x00-\x1f]/g, '').replace(/\x1dVB\x00/g, '');
  // A linha do cupom que contém um texto, sem os espaços repetidos.
  const linhaDe = (lido, contem) => { const l = semComandos(lido).split('\n').find(x => x.includes(contem)); return l === undefined ? '(sem a linha)' : l.replace(/\s+/g, ' ').trim(); };

  // ------------------------------------------------------------------ 1) preparação
  await page.goto(base + '/');
  await page.fill('#ci-nome', 'Gerente de Teste');
  await page.fill('#ci-senha', senhaGerente); await page.fill('#ci-senha2', senhaGerente);
  await page.keyboard.press('Enter');
  await page.waitForURL(base + '/inicio');
  const hoje = (await api('GET', '/api/status')).dados.agora.slice(0, 10);
  const br = iso => iso.slice(8, 10) + '/' + iso.slice(5, 7) + '/' + iso.slice(0, 4);
  const varejo = (await api('GET', '/api/tabelas-preco')).dados.find(t => t.padrao).id;
  // Um produto só: picolé a 4,50 (código 1).
  await criar('/api/produtos', { descricao: 'Picolé de teste', precos: [{ tabela_id: varejo, qtd_min: '1', preco_centavos: 450 }] });
  await espera('[data-status="backup"] .texto', /^Backup: hoje \d\d:\d\d$/, 'Início: a cópia de segurança de hoje foi feita ao abrir o programa');
  await espera('.rodape [data-status="backup"]', /^Backup: hoje \d\d:\d\d$/, 'rodapé: mostra a cópia de segurança de hoje');

  // ------------------------------------------------------------------ 2) Configurações: dados da loja
  await page.click('.lateral a[href="/configuracoes"]');
  await page.waitForSelector('#form-loja');
  await espera('[data-status="impressora_cupom"] .texto', /^Cupom: —$/, 'sem impressora escolhida, o indicador do cupom fica "—"');
  confere('o indicador do cupom diz o motivo', (await page.getAttribute('[data-status="impressora_cupom"]', 'title')) === 'nenhuma impressora de cupom escolhida', await page.getAttribute('[data-status="impressora_cupom"]', 'title'));
  const vazios = await page.$$eval('#form-loja input', campos => campos.filter(c => c.value !== '').length);
  confere('dados da loja começam em branco (nada de exemplo preenchido)', vazios === 0, vazios + ' campo(s) preenchido(s)');
  await medir('configuracoes-loja-em-branco');
  await page.fill('#lj-nome', 'Sorveteria de Teste');
  await page.fill('#lj-cnpj', '11.111.111/1111-11');
  await page.keyboard.press('F10');
  await espera('#form-loja .msg-form', /^CNPJ inválido/, 'CNPJ com dígito errado é recusado');
  await page.fill('#lj-razao', 'Sorveteria de Teste Ltda');
  await page.fill('#lj-cnpj', '11222333000181');
  await page.fill('#lj-ie', '123456789');
  await page.fill('#lj-telefone', '(11) 5555-0100');
  await page.fill('#lj-rua', 'Rua das Flores');
  await page.fill('#lj-numero', '100');
  await page.fill('#lj-bairro', 'Centro');
  await page.fill('#lj-cidade', 'São Paulo');
  await page.selectOption('#lj-uf', 'SP');
  await page.fill('#lj-cep', '01001000');
  await page.fill('#lj-rodape', 'Obrigado pela preferência!');
  await page.keyboard.press('F10');
  await torrada(/^Dados da loja salvos\.$/, 'dados da loja gravados com F10');
  await page.reload(); await page.waitForSelector('#form-loja');
  await page.waitForFunction(() => document.getElementById('lj-nome').value !== '');
  const gravados = await page.$$eval('#form-loja input, #form-loja select', campos => campos.map(c => c.value).join(' | '));
  confere('dados da loja continuam gravados depois de recarregar (CNPJ e CEP com pontuação)',
    gravados === 'Sorveteria de Teste | Sorveteria de Teste Ltda | 11.222.333/0001-81 | 123456789 | (11) 5555-0100 | Rua das Flores | 100 | Centro | São Paulo | SP | 01001-000 | Obrigado pela preferência!', gravados);
  await medir('configuracoes-loja');

  // ------------------------------------------------------------------ 3) Configurações: impressora de cupom
  await page.click('[data-aba="impressao"]');
  const opcoes = await page.$$eval('#im-impressora option', os => os.map(o => o.textContent).join(' | '));
  confere('a lista traz as impressoras do computador, com a padrão marcada', opcoes === '— nenhuma — | ' + IMPRESSORA + ' (padrão do Windows)', opcoes);
  await espera('[data-im-situacao]', /^Nenhuma impressora de cupom escolhida: o sistema não imprime comprovante\.$/, 'situação: nenhuma impressora escolhida');
  await page.click('#btn-teste');
  await espera('#form-impressao .msg-form', /^Escolha a impressora antes de testar\.$/, 'teste sem impressora escolhida é recusado');
  await nadaImpresso('teste sem impressora');
  await page.selectOption('#im-impressora', IMPRESSORA);
  await page.click('#btn-teste');
  await torrada(/^Teste enviado para “Impressora de teste \(grava em arquivo\)”\. Confira o papel\.$/, 'teste de impressão enviado');
  let papel = await impresso('teste de impressão');
  confere('teste: começa iniciando a impressora na página de código 850', comeca(papel.bytes, INICIO), papel.bytes.subarray(0, 5).toString('hex'));
  confere('teste: termina cortando o papel', termina(papel.bytes, CORTE), papel.bytes.subarray(papel.bytes.length - 10).toString('hex'));
  confere('teste: a régua tem 48 números (48 colunas)', papel.texto.split('\n').includes('123456789012345678901234567890123456789012345678'));
  // Na página 850: ê = 0x88, ã = 0xC6, ç = 0x87 (tabela da própria página de código).
  confere('teste: "ç" vai como 0x87 e "ã" como 0xC6', papel.bytes.includes(Buffer.from([0x87])) && papel.bytes.includes(Buffer.from([0xC6])));
  confere('teste: a página de teste não traz valor em dinheiro de exemplo', !/R\$/.test(papel.texto));
  await espera('[data-im-enviado]', /TESTE DE IMPRESSÃO/, 'a tela mostra o que foi mandado para a impressora');
  await espera('[data-status="impressora_cupom"] .texto', /^Cupom: não testada$/, 'impressora escolhida mas não confirmada: indicador "não testada"');
  await medir('configuracoes-impressao-teste-enviado');
  await page.click('[data-saiu="nao"]');
  await espera('#form-impressao .msg-form', /^O teste não saiu certo\./, '"não saiu": a tela orienta o que conferir');
  await espera('[data-status="impressora_cupom"] .texto', /^Cupom: não testada$/, '"não saiu": a impressora continua não testada');
  await page.click('#btn-teste');
  await impresso('segundo teste');
  await page.click('[data-saiu="sim"]');
  await torrada(/^Impressora de cupom confirmada\.$/, '"sim, saiu certo" confirma a impressora');
  await espera('[data-status="impressora_cupom"] .texto', /^Cupom: Impressora de teste \(grava em arquivo\)$/, 'só depois da confirmação o indicador fica verde, com o nome');
  await espera('[data-im-situacao]', /^Impressora testada: o teste em “Impressora de teste \(grava em arquivo\)” foi confirmado\.$/, 'situação: impressora testada');
  // Mudar a largura do papel desfaz a confirmação: o teste foi feito com outra largura.
  await page.selectOption('#im-colunas', '42');
  await page.keyboard.press('F10');
  await torrada(/^Opções de impressão salvas\.$/, 'opções gravadas com 42 colunas');
  await espera('[data-status="impressora_cupom"] .texto', /^Cupom: não testada$/, 'mudar a largura volta a impressora para "não testada"');
  await page.click('#btn-teste');
  papel = await impresso('teste com 42 colunas');
  confere('teste com 42 colunas: a régua tem 42 números', papel.texto.split('\n').includes('123456789012345678901234567890123456789012') && !papel.texto.includes('1234567890123456789012345678901234567890123'));
  // Volta para 48, liga a gaveta e manda imprimir sozinho em toda venda; testa e confirma.
  await page.selectOption('#im-colunas', '48');
  await page.selectOption('#im-quando', 'sempre');
  await page.check('#form-impressao [name="gaveta"]');
  await page.click('#btn-teste');
  await impresso('teste de volta a 48 colunas');
  await page.click('[data-saiu="sim"]');
  await espera('[data-status="impressora_cupom"] .texto', /^Cupom: Impressora de teste \(grava em arquivo\)$/, 'impressora confirmada de novo com 48 colunas');
  await medir('configuracoes-impressao-confirmada');

  // ------------------------------------------------------------------ 4) Configurações: cópia de segurança
  await page.click('[data-aba="backup"]');
  await espera('#tabela-copias tbody', new RegExp('^' + br(hoje) + ' \\d\\d:\\d\\d \\d+ KB$'), 'lista de cópias: a de hoje, com hora e tamanho');
  await espera('[data-bk-situacao]', /^As cópias estão só neste computador\. Escolha uma pasta extra\.$/, 'sem pasta extra, a tela avisa que a cópia está só neste computador');
  await page.fill('#bk-pasta', path.join(saida, 'pasta-que-nao-existe'));
  await page.keyboard.press('F10');
  await espera('#form-backup .msg-form', /não existe neste computador/, 'pasta extra que não existe é recusada');
  await page.fill('#bk-pasta', pastaExtra);
  await page.fill('#bk-manter', '5');
  await page.keyboard.press('F10');
  await espera('#form-backup .msg-form', /7 a 365/, 'guardar menos de 7 cópias é recusado');
  await page.fill('#bk-manter', '30');
  await page.keyboard.press('F10');
  await torrada(/^Opções da cópia de segurança salvas\.$/, 'pasta extra gravada');
  await espera('[data-bk-situacao]', /^A pasta extra ainda não recebeu nenhuma cópia: clique em “Fazer a cópia agora”\.$/, 'pasta extra escolhida, mas ainda sem cópia: a tela diz');
  await espera('[data-status="backup"] .texto', /^Backup: hoje \d\d:\d\d, sem a pasta extra$/, 'indicador avisa que a pasta extra ainda não recebeu a cópia');
  await page.click('#btn-copiar');
  await torrada(/^Cópia feita neste computador e na pasta extra\.$/, '"Fazer a cópia agora" copia nos dois lugares');
  const copia = path.join(pastaExtra, 'moleka-' + hoje + '.db');
  confere('a cópia está na pasta extra, com o nome do dia', fs.existsSync(copia), copia);
  const cabeca = fs.existsSync(copia) ? fs.readFileSync(copia).subarray(0, 15).toString('latin1') : '';
  confere('a cópia é um banco SQLite de verdade (não um arquivo vazio)', cabeca === 'SQLite format 3', cabeca);
  const contagem = fs.existsSync(copia) ? execFileSync(process.env.PYTHON || 'python3', ['-c', 'import sqlite3, sys; c = sqlite3.connect(sys.argv[1]); print(c.execute("select count(*) from produto").fetchone()[0], c.execute("pragma integrity_check").fetchone()[0])', copia]).toString().trim() : '';
  confere('a cópia abre, passa na conferência do SQLite e tem o produto cadastrado', contagem === '1 ok', contagem);
  // A hora mostrada é a da loja (a mesma do rodapé), e não a hora UTC em que o banco grava.
  const naLoja = (await api('GET', '/api/status')).dados.agora; // AAAA-MM-DDTHH:MM...
  await espera('[data-bk-situacao]', new RegExp('^A pasta extra recebeu a cópia em ' + naLoja.slice(8, 10) + '/' + naLoja.slice(5, 7) + ' ' + naLoja.slice(11, 13) + ':\\d\\d\\.$'), 'a tela diz quando a pasta extra recebeu a cópia, na hora da loja');
  await espera('[data-status="backup"] .texto', /^Backup: hoje \d\d:\d\d$/, 'indicador da cópia fica verde com as duas cópias feitas');
  await medir('configuracoes-backup');

  // ------------------------------------------------------------------ 5) PDV: comprovante sozinho, gaveta e Ctrl+P
  await criar('/api/caixa/abrir', { fundo_troco_centavos: 5000 });
  await page.goto(base + '/caixa');
  await page.waitForFunction(() => document.activeElement && document.activeElement.id === 'prod');
  await page.keyboard.press('Control+p');
  await torrada(/^Nenhuma venda encerrada nesta tela ainda\./, 'Ctrl+P sem venda encerrada: avisa, não imprime');
  await nadaImpresso('Ctrl+P sem venda');
  // Venda 1: 2 picolés a 4,50 = 9,00; paga com 10,00 em dinheiro; troco 1,00.
  await page.keyboard.type('2*1'); await page.keyboard.press('Enter');
  await espera('#v-total', /^R\$ 9,00$/, 'venda 1: 2 x 4,50 = 9,00');
  await page.keyboard.press('F6'); await page.waitForSelector('#dlg-valor[open]');
  await page.fill('#dv-valor', '10'); await page.keyboard.press('Enter');
  await page.waitForFunction(() => document.activeElement && document.activeElement.id === 'btn-finalizar');
  await page.keyboard.press('Enter'); await page.waitForSelector('#dlg-finalizar[open]');
  await page.keyboard.press('Enter'); await page.waitForSelector('#dlg-fim[open]');
  await espera('#dlg-fim [data-troco-valor]', /^R\$ 1,00$/, 'venda 1: troco de 1,00 na tela');
  await espera('#dlg-fim [data-fim-impressao]', /^Comprovante enviado para a impressora\.$/, 'venda 1: a tela diz que o comprovante foi para a impressora');
  papel = await impresso('comprovante da venda 1 (sozinho)');
  confere('venda em dinheiro: o pulso da gaveta vai antes do comprovante', comeca(papel.bytes, GAVETA + INICIO), papel.bytes.subarray(0, 10).toString('hex'));
  confere('comprovante: termina cortando o papel', termina(papel.bytes, CORTE));
  confere('comprovante: cabeçalho com o nome da loja', linhaDe(papel.texto, 'Sorveteria de Teste') === 'Sorveteria de Teste', linhaDe(papel.texto, 'Sorveteria de Teste'));
  confere('comprovante: CNPJ da loja', /CNPJ:? 11\.222\.333\/0001-81/.test(papel.texto), linhaDe(papel.texto, 'CNPJ'));
  confere('comprovante: diz que não é documento fiscal', papel.texto.includes('NÃO É DOCUMENTO FISCAL'));
  confere('comprovante: item 2 x 4,50 = 9,00', /^2 UN x 4,50 9,00$/.test(linhaDe(papel.texto, ' x 4,50')), linhaDe(papel.texto, ' x 4,50'));
  confere('comprovante: TOTAL R$ 9,00', linhaDe(papel.texto, 'TOTAL') === 'TOTAL R$ 9,00', linhaDe(papel.texto, 'TOTAL'));
  confere('comprovante: dinheiro 10,00 e troco 1,00', /Dinheiro.* 10,00$/.test(linhaDe(papel.texto, 'Dinheiro')) && /^Troco.* 1,00$/.test(linhaDe(papel.texto, 'Troco')), linhaDe(papel.texto, 'Dinheiro') + ' / ' + linhaDe(papel.texto, 'Troco'));
  confere('comprovante: mensagem do fim com acento ("ê" = 0x88)', papel.bytes.includes(Buffer.concat([Buffer.from('Obrigado pela prefer'), Buffer.from([0x88]), Buffer.from('ncia!')])));
  confere('comprovante: "São Paulo" com "ã" = 0xC6', papel.bytes.includes(Buffer.concat([Buffer.from('S'), Buffer.from([0xC6]), Buffer.from('o Paulo')])));
  await foto('pdv-venda-finalizada-comprovante-enviado');
  // Ctrl+P com o troco na tela: reimprime, sem abrir a gaveta de novo.
  await page.keyboard.press('Control+p');
  await torrada(/^Comprovante da venda nº 1 enviado para “Impressora de teste \(grava em arquivo\)”\.$/, 'Ctrl+P na tela do troco reimprime o comprovante');
  papel = await impresso('reimpressão da venda 1');
  confere('reimpressão: não abre a gaveta', comeca(papel.bytes, INICIO), papel.bytes.subarray(0, 5).toString('hex'));
  confere('reimpressão: mesma venda, mesmo total', linhaDe(papel.texto, 'TOTAL') === 'TOTAL R$ 9,00', linhaDe(papel.texto, 'TOTAL'));
  await page.keyboard.press('Enter'); // "Nova venda (Enter)" continua sendo o Enter
  await page.waitForFunction(() => !document.querySelector('#dlg-fim[open]') && document.activeElement && document.activeElement.id === 'prod');
  confere('Enter na tela do troco continua sendo "Nova venda"', true);

  // "Oferecer o botão": não imprime sozinho. Venda 2: 1 picolé no Pix = 4,50 (sem dinheiro, sem gaveta).
  const impressao = (await api('GET', '/api/configuracoes')).dados.impressao;
  const mudar = async quando => api('PUT', '/api/configuracoes/impressao', { impressora: impressao.impressora, colunas: 48, acentos: 'cp850', vias: 1, quando: quando, cortar: true, gaveta: true });
  confere('opção "oferecer o botão" gravada sem perder a confirmação', (await mudar('perguntar')).dados.confirmada === true);
  await page.keyboard.type('1'); await page.keyboard.press('Enter');
  await espera('#v-numero', /^2$/, 'venda 2 aberta');
  await page.keyboard.press('F7'); await page.waitForSelector('#dlg-valor[open]'); await page.keyboard.press('Enter');
  await espera('#v-situacao', /^Pago sem troco$/, 'venda 2: Pix quita os 4,50');
  await page.keyboard.press('F10'); await page.waitForSelector('#dlg-finalizar[open]'); await page.keyboard.press('Enter');
  await torrada(/^Venda nº 2 finalizada: R\$ 4,50\. Ctrl\+P imprime o comprovante\.$/, 'venda 2 (Pix): não imprime sozinho e lembra do Ctrl+P');
  await nadaImpresso('venda 2 no Pix, com "oferecer o botão"');
  await page.click('#btn-comprovante');
  await torrada(/^Comprovante da venda nº 2 enviado/, 'botão Comprovante imprime a última venda');
  papel = await impresso('comprovante da venda 2 (pelo botão)');
  confere('comprovante da venda 2: Pix 4,50, sem linha de troco', /^Pix.* 4,50$/.test(linhaDe(papel.texto, 'Pix')) && !papel.texto.includes('Troco'), linhaDe(papel.texto, 'Pix'));
  // "Não imprimir": venda 3 em dinheiro certo (4,50). Só o pulso da gaveta vai para a impressora.
  await mudar('nunca');
  await page.keyboard.type('1'); await page.keyboard.press('Enter');
  await espera('#v-numero', /^3$/, 'venda 3 aberta');
  await page.keyboard.press('F6'); await page.waitForSelector('#dlg-valor[open]'); await page.keyboard.press('Enter');
  await espera('#v-situacao', /^Pago sem troco$/, 'venda 3: dinheiro certo, sem troco');
  await page.keyboard.press('F10'); await page.waitForSelector('#dlg-finalizar[open]'); await page.keyboard.press('Enter');
  await torrada(/^Venda nº 3 finalizada: R\$ 4,50\.$/, 'venda 3: com "não imprimir", o aviso não fala em comprovante');
  papel = await impresso('gaveta da venda 3');
  confere('venda em dinheiro sem comprovante: vai só o pulso da gaveta (5 bytes)', papel.bytes.toString('hex') === GAVETA, papel.bytes.toString('hex'));
  // Impressora com defeito: a venda 4 (débito, 4,50) é finalizada do mesmo jeito, com aviso.
  await mudar('sempre');
  fs.renameSync(fila, fila + '-guardada'); fs.writeFileSync(fila, 'não é pasta'); // gravar na "impressora" passa a dar erro
  await page.keyboard.type('1'); await page.keyboard.press('Enter');
  await espera('#v-numero', /^4$/, 'venda 4 aberta');
  await page.keyboard.press('F8'); await page.waitForSelector('#dlg-valor[open]'); await page.keyboard.press('Enter');
  await espera('#v-situacao', /^Pago sem troco$/, 'venda 4: débito quita os 4,50');
  await page.keyboard.press('F10'); await page.waitForSelector('#dlg-finalizar[open]'); await page.keyboard.press('Enter');
  await torrada(/^Venda nº 4 finalizada: R\$ 4,50\. ATENÇÃO: Não consegui imprimir em “Impressora de teste \(grava em arquivo\)”/, 'impressora com defeito: a venda é finalizada e o caixa é avisado');
  await espera('#saldo-do-dia', /^Vendas hoje: R\$ 22,50 · 4 vendas$/, 'as 4 vendas valem: 9,00 + 4,50 + 4,50 + 4,50 = 22,50');
  await page.keyboard.press('Control+p');
  await page.waitForSelector('#dlg-cupom[open]');
  await espera('#dlg-cupom .msg-form', /^Não consegui imprimir em “Impressora de teste \(grava em arquivo\)”/, 'Ctrl+P com a impressora com defeito: o comprovante aparece na tela, com o erro');
  await espera('#dlg-cupom [data-cupom]', /COMPROVANTE DE VENDA.*TOTAL R\$ 4,50/, 'o comprovante da venda 4 está na tela');
  await foto('pdv-comprovante-na-tela-com-erro');
  fs.rmSync(fila); fs.renameSync(fila + '-guardada', fila); // a "impressora" volta a funcionar
  await page.keyboard.press('Control+p'); // com a caixa aberta, Ctrl+P é o botão Imprimir dela
  await torrada(/^Enviado para a impressora “Impressora de teste \(grava em arquivo\)”\.$/, 'impressora de volta: Ctrl+P na caixa do comprovante imprime');
  papel = await impresso('comprovante da venda 4');
  confere('comprovante da venda 4: Débito 4,50', /^Débito.* 4,50$/.test(linhaDe(papel.texto, 'bito')), linhaDe(papel.texto, 'bito'));
  await page.waitForFunction(() => !document.querySelector('#dlg-cupom[open]'));
  await medir('pdv-depois-das-vendas');

  // ------------------------------------------------------------------ 6) Controle de caixa: comprovante, resumo e fechamento
  await page.keyboard.press('F11');
  await page.waitForURL(base + '/controle-caixa');
  await page.click('[data-aba="vendas"]');
  await espera('#tabela-vendas tbody tr:last-child', /^1 \d\d:\d\d Consumidor final Dinheiro 9,00 9,00 Finalizada Cancelar$/, 'lista de vendas: a venda 1, de 9,00 em dinheiro');
  confere('lista de vendas: cada linha tem o botão de imprimir, com o que ele faz escrito', (await page.$$eval('#tabela-vendas tbody tr button.so-icone', bs => bs.map(x => x.title).join(' | '))) === [4, 3, 2, 1].map(n => 'Ver e imprimir o comprovante da venda nº ' + n).join(' | '));
  const cabem = sel => page.$$eval(sel, bs => bs.every(x => { const r = x.getBoundingClientRect(); const c = x.closest('.rolagem').getBoundingClientRect(); return r.left >= c.left && r.right <= c.right; }));
  confere('lista de vendas: os botões cabem na tabela, sem rolar para o lado', await cabem('#tabela-vendas tbody button'));
  await medir('controle-caixa-vendas-com-comprovante');
  await page.click('#tabela-vendas tbody tr:last-child button.so-icone');
  await page.waitForSelector('#dlg-cupom[open]');
  await espera('#dlg-cupom h2', /^Comprovante da venda nº 1$/, 'caixa do comprovante com o número da venda');
  await espera('#dlg-cupom [data-cupom]', /Sorveteria de Teste.*COMPROVANTE DE VENDA.*TOTAL R\$ 9,00.*Troco.*1,00.*Obrigado pela preferência!/, 'o papel na tela é o mesmo da impressora');
  await foto('controle-caixa-comprovante-na-tela');
  await page.click('#dlg-cupom [data-cupom-imprimir]');
  papel = await impresso('comprovante pelo Controle de caixa');
  confere('comprovante pelo Controle de caixa: venda 1, sem abrir a gaveta', comeca(papel.bytes, INICIO) && linhaDe(papel.texto, 'TOTAL') === 'TOTAL R$ 9,00', linhaDe(papel.texto, 'TOTAL'));
  await page.waitForFunction(() => !document.querySelector('#dlg-cupom[open]'));
  await page.click('[data-aba="formas"]');
  await page.click('[data-resumo-cx] button');
  await page.waitForSelector('#dlg-cupom[open]');
  await espera('#dlg-cupom h2', /^Resumo do caixa \(ainda aberto\)$/, 'resumo do caixa aberto: título diz que ainda está aberto');
  // Dinheiro na gaveta: fundo 50,00 + vendas em dinheiro 9,00 + 4,50 = 63,50.
  await espera('#dlg-cupom [data-cupom]', /RESUMO DO CAIXA \(AINDA ABERTO\).*63,50/, 'resumo: dinheiro esperado na gaveta 50,00 + 13,50 = 63,50');
  await foto('controle-caixa-resumo-na-tela');
  await page.keyboard.press('Escape');
  await nadaImpresso('ver o resumo na tela');
  // Fechamento com tudo batendo: dinheiro 63,50, Pix 4,50, débito 4,50, crédito 0.
  await page.click('#btn-fechar');
  await page.waitForSelector('#dlg-fechar[open]');
  const campos = '#dlg-fechar tbody input';
  await page.locator(campos).nth(0).fill('63,50');
  await page.locator(campos).nth(1).fill('4,50');
  await page.locator(campos).nth(2).fill('4,50');
  await page.locator(campos).nth(3).fill('0');
  await page.click('#form-fechar button[type=submit]');
  await torrada(/^Caixa fechado\.$/, 'caixa fechado sem diferença');
  await page.waitForSelector('#dlg-cupom[open]');
  await espera('#dlg-cupom h2', /^Fechamento de caixa$/, 'com impressora, o papel do fechamento aparece sozinho depois de fechar');
  await foto('controle-caixa-fechamento-na-tela');
  await page.keyboard.press('Control+p');
  papel = await impresso('fechamento de caixa');
  confere('fechamento: título e total vendido 22,50', papel.texto.includes('FECHAMENTO DE CAIXA') && /22,50/.test(papel.texto), linhaDe(papel.texto, '22,50'));
  confere('fechamento: tem a linha para assinar', papel.texto.includes('Conferido por:'));
  confere('fechamento: sai 1 via e não abre a gaveta', comeca(papel.bytes, INICIO) && papel.bytes.indexOf(Buffer.from(INICIO, 'hex'), 1) === -1);
  await page.waitForFunction(() => !document.querySelector('#dlg-cupom[open]'));
  await espera('[data-status="backup"] .texto', /^Backup: hoje \d\d:\d\d$/, 'depois do fechamento do caixa, a cópia de segurança continua em dia');
  await page.click('[data-aba="historico"]');
  await espera('#tabela-historico tbody tr:nth-child(1)', /Gerente de Teste 4 22,50 0,00 0,00$/, 'fechamentos: 4 vendas, 22,50, sem diferença');
  confere('fechamentos: a linha tem o botão de imprimir e ele cabe na tabela', (await page.$$eval('#tabela-historico tbody tr button.so-icone', bs => bs.length)) === 1 && await cabem('#tabela-historico tbody button'));
  await medir('controle-caixa-fechamentos');
  await page.click('#tabela-historico tbody tr:nth-child(1) button');
  await page.waitForSelector('#dlg-cupom[open]');
  await espera('#dlg-cupom [data-cupom]', /FECHAMENTO DE CAIXA/, 'fechamento anterior abre na tela');
  await page.keyboard.press('Escape');

  // ------------------------------------------------------------------ 7) relatórios em folha comum (A4)
  const cat = (await api('GET', '/api/financeiro/categorias')).dados.find(c => c.serve_para.includes('despesa'));
  await criar('/api/financeiro/lancamentos', { tipo: 'despesa', categoria_id: cat.id, descricao: 'Conta de luz de teste', valor_centavos: 12345, vencimento: hoje });
  const folha = () => page.evaluate(() => {
    const f = document.getElementById('impressao');
    if (!f) return null;
    const t = el => { if (!el) return ''; const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT); const p = []; while (w.nextNode()) p.push(w.currentNode.nodeValue); return p.join(' ').replace(/\s+/g, ' ').trim(); };
    return {
      loja: t(f.querySelector('.imp-loja')), titulo: t(f.querySelector('h1')), detalhes: Array.from(f.querySelectorAll('.imp-detalhe')).map(t),
      resumo: Array.from(f.querySelectorAll('.imp-resumo > div')).map(t), avisos: Array.from(f.querySelectorAll('.imp-aviso')).map(t),
      colunas: Array.from(f.querySelectorAll('table thead th')).map(t), linhas: Array.from(f.querySelectorAll('table tbody tr')).map(t),
      botoes: f.querySelectorAll('button, input, select').length, pe: t(f.querySelector('footer')), chamadas: window.__impressoes,
    };
  });
  const fimDoMes = new Date(Number(hoje.slice(0, 4)), Number(hoje.slice(5, 7)), 0).getDate();
  const periodo = 'Período: 01/' + hoje.slice(5, 7) + '/' + hoje.slice(0, 4) + ' a ' + fimDoMes + '/' + hoje.slice(5, 7) + '/' + hoje.slice(0, 4);
  await page.goto(base + '/financeiro');
  await page.waitForSelector('#tabela-lancamentos tbody tr:not(:has(.sem-linhas))');
  await medir('financeiro-com-o-botao-imprimir');
  await page.keyboard.press('Control+p');
  await page.waitForFunction(() => window.__impressoes === 1);
  let f = await folha();
  confere('contas (folha): cabeçalho com a loja e o CNPJ', f.loja === 'Sorveteria de Teste · CNPJ 11.222.333/0001-81', f.loja);
  confere('contas (folha): título e período escritos', f.titulo === 'Contas a pagar e a receber' && f.detalhes[0] === periodo, f.titulo + ' / ' + f.detalhes[0]);
  confere('contas (folha): o filtro e a contagem da lista estão escritos', /^Lista: Despesas e receitas · Em aberto e pagas · 1 lançamento, vencimento de /.test(f.detalhes[1]), f.detalhes[1]);
  confere('contas (folha): a coluna de botões não vai para o papel', f.colunas.join(' | ') === 'Vencimento | Descrição | Tipo | Valor (R$) | Situação' && f.botoes === 0, f.colunas.join(' | ') + ' / ' + f.botoes + ' botão(ões)');
  confere('contas (folha): a linha é a da tela', f.linhas.length === 1 && /^\d\d\/\d\d\/\d{4} Conta de luz de teste .* Despesa 123,45 Em aberto$/.test(f.linhas[0]), f.linhas.join(' || '));
  confere('contas (folha): resumo com os 4 números da tela (a pagar 123,45)', f.resumo.length === 4 && /^A pagar R\$ 123,45/.test(f.resumo[0]), f.resumo.join(' || '));
  confere('contas (folha): pé com data, operador e versão', /^Impresso em \d\d\/\d\d\/\d{4} às \d\d:\d\d por Gerente de Teste · Moleka PDV \d+\.\d+\.\d+$/.test(f.pe), f.pe);
  await page.emulateMedia({ media: 'print' });
  const noPapel = await page.evaluate(() => ({ tela: getComputedStyle(document.querySelector('.tela')).display, folha: getComputedStyle(document.getElementById('impressao')).display }));
  confere('no papel só a folha aparece (a tela, com menus e botões, fica de fora)', noPapel.tela === 'none' && noPapel.folha === 'block', JSON.stringify(noPapel));
  await page.pdf({ path: path.join(saida, 'relatorio-contas.pdf'), format: 'A4' });
  await page.emulateMedia({ media: 'screen' });
  const naTela = await page.evaluate(() => getComputedStyle(document.getElementById('impressao')).display);
  confere('na tela a folha não aparece', naTela === 'none', naTela);
  // DRE: receita das 4 vendas = 22,50.
  await page.click('[data-aba="dre"]');
  await page.waitForSelector('#tabela-dre tbody tr:not(:has(.sem-linhas))');
  const linhasDaTela = await page.$$eval('#tabela-dre tbody tr', trs => trs.length);
  await page.click('#btn-imprimir');
  await page.waitForFunction(() => window.__impressoes === 2);
  f = await folha();
  confere('DRE (folha): título, período e as mesmas linhas da tela', f.titulo === 'Demonstração do resultado (DRE)' && f.detalhes[0] === periodo && f.linhas.length === linhasDaTela, f.titulo + ' / ' + f.linhas.length + ' de ' + linhasDaTela + ' linhas');
  confere('DRE (folha): a receita das vendas (22,50) está na folha', f.linhas.some(l => /22,50/.test(l)), f.linhas[0]);
  await page.emulateMedia({ media: 'print' }); await page.pdf({ path: path.join(saida, 'relatorio-dre.pdf'), format: 'A4' }); await page.emulateMedia({ media: 'screen' });
  await page.click('[data-aba="fluxo"]');
  await page.waitForSelector('#tabela-fluxo tbody tr:not(:has(.sem-linhas))');
  await page.click('#btn-imprimir');
  await page.waitForFunction(() => window.__impressoes === 3);
  f = await folha();
  confere('fluxo de caixa (folha): título, 8 colunas e a nota de rodapé da tela', f.titulo === 'Fluxo de caixa' && f.colunas.length === 8, f.titulo + ' / ' + f.colunas.length + ' colunas');
  await page.emulateMedia({ media: 'print' }); await page.pdf({ path: path.join(saida, 'relatorio-fluxo.pdf'), format: 'A4' }); await page.emulateMedia({ media: 'screen' });
  await page.click('[data-aba="rentabilidade"]');
  await page.waitForSelector('#tabela-rentabilidade tbody tr');
  await page.click('#btn-imprimir');
  await page.waitForFunction(() => window.__impressoes === 4);
  f = await folha();
  confere('rentabilidade (folha): título e o picolé vendido', f.titulo === 'Rentabilidade por produto' && f.linhas.some(l => /Picolé de teste/.test(l)), f.titulo + ' / ' + f.linhas.join(' || '));
  await page.click('[data-aba="categorias"]');
  await page.keyboard.press('Control+p');
  await torrada(/^Esta tela não tem impressão\.$/, 'aba Categorias: sem impressão, o Ctrl+P avisa');
  confere('aba Categorias: nada foi mandado imprimir', (await page.evaluate(() => window.__impressoes)) === 4);
  // Estoque: o picolé vendido sem entrada fica com saldo negativo (-5).
  await page.goto(base + '/estoque');
  await page.waitForSelector('#tabela-estoque tbody tr:not(:has(.sem-linhas))');
  await medir('estoque-com-o-botao-imprimir');
  await page.click('#btn-imprimir');
  await page.waitForFunction(() => window.__impressoes === 1);
  f = await folha();
  confere('estoque (folha): título, filtro e contagem', f.titulo === 'Posição do estoque' && f.detalhes[0] === 'Lista: Todos os produtos · 1 produto', f.titulo + ' / ' + f.detalhes[0]);
  confere('estoque (folha): 4 colunas, sem a de botões', f.colunas.join(' | ') === 'Produto | Saldo | Custo (R$) | Situação' && f.botoes === 0, f.colunas.join(' | '));
  confere('estoque (folha): o saldo é o da tela (5 picolés vendidos sem entrada: -5)', /^Picolé de teste .* -5 UN — Negativo$/.test(f.linhas[0]), f.linhas[0]);
  await page.emulateMedia({ media: 'print' }); await page.pdf({ path: path.join(saida, 'relatorio-estoque.pdf'), format: 'A4' }); await page.emulateMedia({ media: 'screen' });
  await page.goto(base + '/produtos');
  await page.waitForSelector('#tabela-produtos tbody tr');
  await page.keyboard.press('Control+p');
  await torrada(/^Esta tela não tem impressão\.$/, 'tela sem impressão (Produtos): o Ctrl+P avisa em vez de imprimir a tela');

  // ------------------------------------------------------------------ 8) sem impressora escolhida
  await page.goto(base + '/configuracoes#impressao');
  await page.waitForSelector('#form-impressao');
  await page.waitForFunction(nome => document.getElementById('im-impressora').value === nome, IMPRESSORA);
  await page.selectOption('#im-impressora', '');
  await page.keyboard.press('F10');
  await torrada(/^Opções de impressão salvas\.$/, 'impressora tirada das Configurações');
  await espera('[data-status="impressora_cupom"] .texto', /^Cupom: —$/, 'sem impressora, o indicador volta para "—"');
  await page.goto(base + '/controle-caixa');
  await page.waitForSelector('#tabela-historico tbody tr button');
  await page.click('#tabela-historico tbody tr:nth-child(1) button');
  await page.waitForSelector('#dlg-cupom[open]');
  await espera('#dlg-cupom .msg-form', /^Nenhuma impressora de cupom escolhida\. O gerente escolhe em Configurações\.$/, 'sem impressora: o papel aparece na tela com o motivo de não imprimir');
  confere('sem impressora: o botão Imprimir fica desligado', await page.isDisabled('#dlg-cupom [data-cupom-imprimir]'));
  await foto('fechamento-na-tela-sem-impressora');
  await page.keyboard.press('Escape');
  await nadaImpresso('sem impressora escolhida');

  // ------------------------------------------------------------------ 9) operador comum
  const criado = await api('POST', '/api/operadores', { nome: 'Caixa de Teste', login: 'caixa', senha: senhaCaixa, perfil: 'operador' });
  confere('operador comum criado', criado.status === 201, criado.status);
  const ctx2 = await b.newContext({ viewport: { width: LARGURA, height: ALTURA }, locale: 'pt-BR' });
  page = await ctx2.newPage(); vigiar(page);
  await page.goto(base + '/');
  await page.selectOption('#lg-operador', 'caixa');
  await page.fill('#lg-senha', senhaCaixa); await page.keyboard.press('Enter');
  await page.waitForURL(base + '/inicio');
  confere('operador comum: Configurações aparece trancado no menu lateral', (await page.$('.lateral a[href="/configuracoes"]')) === null && (await page.$('.lateral button[data-aviso^="Configurações"]')) !== null);
  await page.goto(base + '/configuracoes');
  confere('operador comum não abre Configurações', new URL(page.url()).pathname === '/inicio', page.url());
  for (const [metodo, caminho] of [['GET', '/api/configuracoes'], ['GET', '/api/impressoras'], ['POST', '/api/impressao/teste'], ['POST', '/api/backup']]) {
    const r = await api(metodo, caminho);
    confere('operador comum não usa ' + metodo + ' ' + caminho, r.status === 403, r.status);
  }
  const ver = await api('GET', '/api/vendas/1/comprovante');
  confere('operador comum vê o comprovante de uma venda', ver.status === 200 && ver.dados.pode_imprimir === false, ver.status);
  const anterior = await api('GET', '/api/caixa/resumo-impresso?sessao_id=1');
  confere('operador comum não vê o fechamento feito pelo gerente', anterior.status === 403, anterior.status);

  await b.close();
  console.log('');
  console.log(conferencias + ' conferências, ' + esperados + ' impressões lidas da impressora de teste.');
  console.log(erros.length ? 'ERROS DO NAVEGADOR:\n' + erros.join('\n') : 'Nenhum erro de JavaScript, de rede ou do servidor (5xx).');
  console.log(falhas.length ? 'FALHAS (' + falhas.length + '): ' + falhas.join(' | ') : 'Todas as conferências passaram.');
  process.exit(falhas.length || erros.length ? 1 : 0);
})().catch(e => { console.error('ROTEIRO INTERROMPIDO: ' + e.message); process.exit(2); });

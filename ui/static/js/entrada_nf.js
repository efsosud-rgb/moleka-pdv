/* Moleka PDV — tela Entrada de NF (só o gerente): escolher o XML, conferir, importar e estornar.
   O XML é lido pelo servidor (/api/compras/conferir) e nada é gravado antes do "Importar".
   A coluna "Entra no estoque" é uma prévia da conta que o servidor faz na importação
   (quantidade × fator, e custo do item ÷ quantidade que entra); o que vale é o que ele devolve. */

(function () {
  "use strict";

  const M = window.Moleka;
  const raiz = document.getElementById("entrada-nf");
  if (!raiz) return;

  const arquivo = document.getElementById("arquivo");
  const corpoItens = raiz.querySelector("#tabela-itens tbody");
  const corpoNotas = raiz.querySelector("#tabela-notas tbody");
  const form = document.getElementById("form-importar");
  const msgArquivo = raiz.querySelector("[data-msg-arquivo]");
  const msgNotas = raiz.querySelector("[data-msg-notas]");
  const lote = raiz.querySelector("[data-lote]");
  const dlgNota = document.getElementById("dlg-nota");
  const teclaEsc = document.querySelector('.rodape [data-atalho="Escape"]');

  const TAMANHO_MAXIMO = 2000000; // o mesmo limite do servidor
  const UNIDADES_FRACIONADAS = ["KG", "G", "L", "ML", "M"];
  const ACOES = [["", "— escolha —"], ["vincular", "Dar entrada em…"], ["criar", "Criar produto novo"], ["ignorar", "Não dar entrada"]];
  const ORIGENS = { memoria: "lembrado da última nota", ean: "achado pelo código de barras" };

  let xml = ""; // o texto do arquivo escolhido
  let nota = null; // a nota lida, de /api/compras/conferir
  let linhas = []; // uma por item da nota
  let hoje = ""; // a data da loja, dita pelo servidor (AAAA-MM-DD)

  // ------------------------------------------------------------------ utilidades
  function data(iso) {
    const p = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || "");
    return p ? p[3] + "/" + p[2] + "/" + p[1] : "—";
  }

  function mensagemSolta(el, texto) {
    el.textContent = texto || "";
    el.hidden = !texto;
  }

  function passo(nome) {
    raiz.querySelectorAll("[data-passo]").forEach(function (el) { el.hidden = el.dataset.passo !== nome; });
    // Durante a conferência, Esc não sai da tela (para não perder as escolhas sem querer).
    if (teclaEsc) teclaEsc.hidden = nome === "conferir";
  }

  function mostrarAba(nome) {
    raiz.querySelectorAll("[data-aba]").forEach(function (botao) {
      const ativa = botao.dataset.aba === nome;
      botao.classList.toggle("ativa", ativa);
      botao.setAttribute("aria-selected", ativa ? "true" : "false");
    });
    raiz.querySelectorAll("[data-painel]").forEach(function (painel) { painel.hidden = painel.dataset.painel !== nome; });
    fecharSugestoes();
    if (nome === "notas") carregarNotas();
  }

  /* Fator digitado: "24", "0,5" ou "0.5". "1.000" é recusado (seria mil ou um?). */
  function lerFator(texto) {
    const digitado = String(texto).trim();
    if (/^\d+\.\d{3}$/.test(digitado) || !/^\d+([.,]\d{1,3})?$/.test(digitado)) return null;
    const limpo = digitado.replace(",", ".");
    return Number(limpo) > 0 ? limpo : null;
  }

  // ------------------------------------------------------------------ escolha do produto (pesquisa no servidor)
  const sugestoes = M.el("ul", { class: "sugestoes flutua", role: "listbox", hidden: true });
  document.body.appendChild(sugestoes);
  let dona = null; // a linha que está com a lista de sugestões aberta
  let opcoes = [];
  let marcada = -1;
  let relogioDaBusca = 0;
  let pedido = 0;

  function fecharSugestoes() {
    clearTimeout(relogioDaBusca);
    pedido += 1;
    dona = null;
    opcoes = [];
    marcada = -1;
    sugestoes.hidden = true;
  }

  function posicionar(campo) {
    const r = campo.getBoundingClientRect();
    const largura = Math.max(r.width, 340);
    sugestoes.style.width = largura + "px";
    sugestoes.style.left = Math.max(8, Math.min(r.left, window.innerWidth - largura - 8)) + "px";
    const altura = sugestoes.offsetHeight;
    const cabeEmbaixo = r.bottom + 4 + altura <= window.innerHeight - 8;
    sugestoes.style.top = (cabeEmbaixo ? r.bottom + 4 : Math.max(8, r.top - altura - 4)) + "px";
  }

  function desenharSugestoes(vazio) {
    if (!dona) return;
    const linha = dona;
    if (!opcoes.length) {
      M.trocar(sugestoes, M.el("li", { class: "nada", text: vazio }));
    } else {
      M.trocar.apply(null, [sugestoes].concat(opcoes.map(function (p, i) {
        const li = M.el("li", { class: i === marcada ? "marcada" : "", role: "option" },
          M.el("span", { class: "cod", text: p.codigo }),
          M.el("span", { class: "nome", text: p.descricao }),
          M.el("span", { class: "doc", text: p.unidade }));
        li.addEventListener("mousedown", function (evento) { evento.preventDefault(); }); // o campo não perde o foco
        li.addEventListener("click", function () { escolherProduto(linha, p); });
        return li;
      })));
    }
    sugestoes.hidden = false;
    posicionar(linha.campoProduto);
  }

  function pesquisar(linha) {
    clearTimeout(relogioDaBusca);
    const termo = linha.campoProduto.value.trim();
    if (!termo) { fecharSugestoes(); return; }
    dona = linha;
    const meu = ++pedido;
    relogioDaBusca = setTimeout(async function () {
      const r = await M.api("GET", "/api/produtos?limite=8&busca=" + encodeURIComponent(termo));
      if (meu !== pedido) return; // a pessoa já digitou outra coisa
      opcoes = r.ok ? r.dados : [];
      marcada = opcoes.length ? 0 : -1;
      desenharSugestoes(r.ok ? "Nenhum produto com esse nome ou código. Se ele ainda não existe, escolha “Criar produto novo”." : r.erro);
    }, 200);
  }

  function escolherProduto(linha, p) {
    linha.produto = { id: p.id, codigo: p.codigo, descricao: p.descricao, unidade: p.unidade };
    linha.origem = null;
    linha.campoProduto.value = p.descricao;
    fecharSugestoes();
    atualizarLinha(linha);
    linha.campoFator.focus();
    linha.campoFator.select();
  }

  function teclaNoProduto(linha, evento) {
    const aberta = dona === linha && !sugestoes.hidden;
    if (evento.key === "Escape" && aberta) {
      evento.preventDefault();
      evento.stopPropagation(); // só fecha a lista; não limpa o campo
      fecharSugestoes();
    } else if ((evento.key === "ArrowDown" || evento.key === "ArrowUp") && aberta && opcoes.length) {
      evento.preventDefault();
      marcada = (marcada + (evento.key === "ArrowDown" ? 1 : opcoes.length - 1)) % opcoes.length;
      desenharSugestoes("");
    } else if (evento.key === "Enter") {
      evento.preventDefault(); // Enter num campo da tabela não importa a nota
      if (aberta && marcada >= 0) escolherProduto(linha, opcoes[marcada]);
    }
  }

  // ------------------------------------------------------------------ a tabela de conferência
  function unidadeDoProdutoNovo(item, fator) {
    if (Number(fator) === 1) return item.unidade;
    const dentro = item.unidade_tributavel;
    return dentro && dentro !== item.unidade ? dentro : "UN";
  }

  /* Prévia do que entra: { quantidade (número), unidade, custo (centavos), quebrada } ou null. */
  function previa(linha) {
    const acao = linha.selecao.value;
    const fator = lerFator(linha.campoFator.value);
    if ((acao !== "vincular" && acao !== "criar") || fator === null) return null;
    if (acao === "vincular" && !linha.produto) return null;
    const milesimos = Math.round(Math.round(Number(linha.item.quantidade) * 1000) * Math.round(Number(fator) * 1000) / 1000);
    if (milesimos <= 0) return null;
    const unidade = acao === "vincular" ? linha.produto.unidade : unidadeDoProdutoNovo(linha.item, fator);
    return {
      quantidade: milesimos / 1000,
      unidade: unidade,
      custo: Math.round(linha.item.custo_total_centavos * 1000 / milesimos),
      quebrada: milesimos % 1000 !== 0 && UNIDADES_FRACIONADAS.indexOf(unidade.toUpperCase()) < 0,
    };
  }

  function atualizarLinha(linha) {
    const acao = linha.selecao.value;
    const vincular = acao === "vincular";
    linha.campoProduto.hidden = !vincular;
    linha.campoFator.hidden = acao !== "vincular" && acao !== "criar";
    linha.tr.classList.toggle("sem-entrada", acao === "ignorar");
    let observacao = "";
    if (vincular) observacao = linha.produto ? (linha.origem ? ORIGENS[linha.origem] : "cód. " + linha.produto.codigo) : "digite o nome ou o código";
    else if (acao === "criar") observacao = "produto novo, sem preço de venda";
    else if (acao === "ignorar") observacao = "fica só registrado na nota";
    linha.notaProduto.textContent = observacao;
    linha.notaProduto.classList.toggle("negativo", vincular && !linha.produto);

    const p = previa(linha);
    if (acao === "ignorar") M.trocar(linha.celEntra, M.el("span", { class: "sub", text: "não entra" }));
    else if (!acao) M.trocar(linha.celEntra, M.el("span", { class: "sub", text: "escolha o que fazer" }));
    else if (!p) M.trocar(linha.celEntra, M.el("span", { class: "sub negativo", text: vincular && !linha.produto ? "escolha o produto" : "confira o fator" }));
    else if (p.quebrada) M.trocar(linha.celEntra, M.el("b", { class: "negativo", text: M.qtd(p.quantidade) + " " + p.unidade }), M.el("span", { class: "sub negativo", text: "quantidade quebrada: confira o fator" }));
    else M.trocar(linha.celEntra, M.el("b", { text: M.qtd(p.quantidade) + " " + p.unidade }), M.el("span", { class: "sub", text: M.formatarCentavos(p.custo) + " cada" }));
    atualizarLote();
  }

  function linhaDoItem(item) {
    const selecao = M.el("select", { class: "campo", "aria-label": "O que fazer com o item " + item.numero });
    ACOES.forEach(function (a) { selecao.appendChild(M.el("option", { value: a[0], text: a[1] })); });
    const campoProduto = M.el("input", { class: "campo", type: "text", autocomplete: "off", placeholder: "Nome ou código", "aria-label": "Nosso produto para o item " + item.numero });
    const campoFator = M.el("input", { class: "campo num", type: "text", inputMode: "decimal", value: M.qtd(item.sugestao_fator), "aria-label": "Fator de conversão do item " + item.numero });
    const notaProduto = M.el("span", { class: "sub" });
    const celEntra = M.el("td");
    const detalhes = [M.qtd(item.quantidade) + " " + item.unidade + " × " + M.reais(item.valor_unitario_centavos), "custo " + M.formatarCentavos(item.custo_total_centavos), "cód. " + item.codigo];
    if (item.ean) detalhes.push("barras " + item.ean);
    const dicaDoFator = item.fator_da_nota ? "A nota informa: 1 " + item.unidade + " = " + M.qtd(item.fator_da_nota) + " " + item.unidade_tributavel : "A nota não informa quantas unidades há em cada " + item.unidade;
    campoFator.title = dicaDoFator;
    const tr = M.el("tr", null,
      M.el("td", { text: String(item.numero) }),
      M.el("td", null, item.descricao, M.el("span", { class: "sub", text: detalhes.join(" · "), title: "O custo do item soma frete, seguro, outras despesas, IPI e ICMS-ST, e desconta o desconto." })),
      M.el("td", null, M.el("div", { class: "sel auto" }, selecao)),
      M.el("td", null, campoProduto, notaProduto),
      M.el("td", null, campoFator),
      celEntra);
    const linha = { item: item, tr: tr, selecao: selecao, campoProduto: campoProduto, campoFator: campoFator, notaProduto: notaProduto, celEntra: celEntra, produto: null, origem: null };
    if (item.sugestao_produto_id) {
      linha.produto = { id: item.sugestao_produto_id, codigo: item.sugestao_codigo, descricao: item.sugestao_descricao, unidade: item.sugestao_unidade };
      linha.origem = item.sugestao_origem;
      campoProduto.value = item.sugestao_descricao;
      selecao.value = "vincular";
    }
    selecao.addEventListener("change", function () {
      atualizarLinha(linha);
      if (selecao.value === "vincular" && !linha.produto) campoProduto.focus();
    });
    campoProduto.addEventListener("input", function () { linha.produto = null; linha.origem = null; atualizarLinha(linha); pesquisar(linha); });
    campoProduto.addEventListener("keydown", function (evento) { teclaNoProduto(linha, evento); });
    campoProduto.addEventListener("blur", function () { if (dona === linha) fecharSugestoes(); });
    campoFator.addEventListener("input", function () { atualizarLinha(linha); });
    campoFator.addEventListener("keydown", function (evento) { if (evento.key === "Enter") evento.preventDefault(); });
    return linha;
  }

  function atualizarLote() {
    const pendentes = linhas.filter(function (l) { return !l.selecao.value; }).length;
    lote.hidden = pendentes === 0 || !!(nota && nota.ja_importada);
    lote.querySelector("[data-lote-texto]").textContent = pendentes === 1 ? "1 item ainda sem decisão." : pendentes + " itens ainda sem decisão.";
  }

  function desenharContas() {
    const caixa = form.gerar_contas;
    const texto = form.querySelector("[data-contas-texto]");
    const semParcelas = form.querySelector("[data-sem-parcelas]");
    const contas = form.querySelector(".contas");
    contas.hidden = nota.total_centavos <= 0;
    if (nota.parcelas.length) {
      const partes = nota.parcelas.slice(0, 4).map(function (p) { return data(p.vencimento).slice(0, 5) + " " + M.formatarCentavos(p.valor_centavos); });
      if (nota.parcelas.length > 4) partes.push("e mais " + (nota.parcelas.length - 4));
      texto.textContent = (nota.parcelas.length === 1 ? "Criar a conta a pagar da parcela: " : "Criar as contas a pagar das " + nota.parcelas.length + " parcelas: ") + partes.join(" · ");
      caixa.checked = true;
      semParcelas.hidden = true;
    } else {
      texto.textContent = "A nota não traz parcelas. Criar uma conta a pagar de " + M.formatarCentavos(nota.total_centavos);
      caixa.checked = false;
      semParcelas.hidden = false;
      form.vencimento.value = M.dataBR(hoje);
    }
  }

  function desenharConferencia() {
    const valores = {
      fornecedor: nota.fornecedor_nome,
      documento: nota.fornecedor_documento,
      numero: "NF " + nota.numero + " · série " + nota.serie,
      emitida: "emitida em " + data(nota.emitida_em),
      total: M.formatarCentavos(nota.total_centavos),
      itens: nota.itens.length + (nota.itens.length === 1 ? " item" : " itens"),
    };
    raiz.querySelectorAll("[data-nf]").forEach(function (el) { el.textContent = valores[el.dataset.nf] || "—"; });

    const avisos = nota.avisos.slice();
    if (nota.ja_importada) avisos.unshift("Esta nota já foi importada em " + data(nota.importada_em) + ". Ela não entra duas vezes: para importar de novo, estorne a nota na aba “Notas importadas”.");
    const listaDeAvisos = raiz.querySelector("[data-avisos]");
    M.trocar.apply(null, [listaDeAvisos].concat(avisos.map(function (a) { return M.el("li", { text: a }); })));
    listaDeAvisos.hidden = !avisos.length;
    listaDeAvisos.classList.toggle("grave", nota.ja_importada || nota.autorizada === false);

    linhas = nota.itens.map(linhaDoItem);
    M.trocar.apply(null, [corpoItens].concat(linhas.map(function (l) { return l.tr; })));
    linhas.forEach(atualizarLinha);
    desenharContas();
    M.mensagem(form, "");
    document.getElementById("btn-importar").disabled = nota.ja_importada;
    passo("conferir");
    const primeira = linhas.find(function (l) { return !l.selecao.value; });
    if (primeira && !nota.ja_importada) primeira.selecao.focus();
  }

  // ------------------------------------------------------------------ escolher e ler o arquivo
  async function lerArquivo(escolhido) {
    mensagemSolta(msgArquivo, "");
    if (!escolhido) return;
    if (escolhido.size > TAMANHO_MAXIMO) { passo("arquivo"); mensagemSolta(msgArquivo, "O arquivo é grande demais para ser uma NF-e. Confira se escolheu o XML da nota."); return; }
    let texto;
    try {
      texto = await escolhido.text();
    } catch (falha) {
      passo("arquivo");
      mensagemSolta(msgArquivo, "Não consegui abrir o arquivo. Tente escolher de novo.");
      return;
    }
    const r = await M.api("POST", "/api/compras/conferir", { xml: texto });
    if (!r.ok) {
      passo("arquivo");
      mensagemSolta(msgArquivo, "“" + escolhido.name + "”: " + r.erro);
      return;
    }
    xml = texto;
    nota = r.dados;
    desenharConferencia();
  }

  function pedirArquivo() {
    fecharSugestoes();
    arquivo.value = ""; // escolher o mesmo arquivo de novo também dispara a leitura
    arquivo.click();
  }

  arquivo.addEventListener("change", function () {
    const escolhido = arquivo.files[0];
    arquivo.value = ""; // o mesmo arquivo pode ser escolhido de novo depois
    lerArquivo(escolhido);
  });
  document.getElementById("btn-escolher").addEventListener("click", pedirArquivo);
  document.getElementById("btn-trocar").addEventListener("click", pedirArquivo);
  document.getElementById("btn-outra").addEventListener("click", function () { passo("arquivo"); pedirArquivo(); });
  // Arquivo solto em cima da janela: lê como se tivesse sido escolhido (e não deixa a janela
  // "navegar" para o arquivo).
  document.addEventListener("dragover", function (evento) { evento.preventDefault(); });
  document.addEventListener("drop", function (evento) {
    evento.preventDefault();
    const solto = evento.dataTransfer && evento.dataTransfer.files ? evento.dataTransfer.files[0] : null;
    if (solto) { mostrarAba("importar"); lerArquivo(solto); }
  });

  lote.querySelectorAll("[data-lote-acao]").forEach(function (botao) {
    botao.addEventListener("click", function () {
      linhas.forEach(function (l) { if (!l.selecao.value) { l.selecao.value = botao.dataset.loteAcao; atualizarLinha(l); } });
    });
  });

  // ------------------------------------------------------------------ importar
  form.addEventListener("submit", async function (evento) {
    evento.preventDefault();
    if (!nota || nota.ja_importada) return;
    const decisoes = [];
    const conta = { vincular: 0, criar: 0, ignorar: 0 };
    for (let i = 0; i < linhas.length; i++) {
      const l = linhas[i];
      const acao = l.selecao.value;
      const n = l.item.numero;
      if (!acao) { M.mensagem(form, "Falta decidir o que fazer com o item " + n + " (" + l.item.descricao + ")."); l.selecao.focus(); return; }
      if (acao === "ignorar") { decisoes.push({ numero: n, acao: acao }); conta.ignorar += 1; continue; }
      if (acao === "vincular" && !l.produto) { M.mensagem(form, "Item " + n + ": escolha o nosso produto na lista que aparece ao digitar."); l.campoProduto.focus(); return; }
      const fator = lerFator(l.campoFator.value);
      if (fator === null) { M.mensagem(form, "Item " + n + ": o fator precisa ser um número maior que zero (use 1 quando a unidade da nota é a mesma da loja)."); l.campoFator.focus(); return; }
      const p = previa(l);
      if (!p || p.quebrada) { M.mensagem(form, "Item " + n + ": a quantidade que entra ficou quebrada ou zerada. Confira o fator."); l.campoFator.focus(); return; }
      decisoes.push({ numero: n, acao: acao, produto_id: acao === "vincular" ? l.produto.id : null, fator: fator });
      conta[acao] += 1;
    }
    const gerar = form.gerar_contas.checked && nota.total_centavos > 0;
    const semParcelas = !nota.parcelas.length;
    const vencimento = gerar && semParcelas ? M.lerData(form.vencimento.value) : null;
    if (gerar && semParcelas && !vencimento) { M.mensagem(form, "Digite o vencimento da conta a pagar. Assim: 15/11/2026"); form.vencimento.focus(); return; }
    M.mensagem(form, "");

    const partes = [];
    if (conta.vincular) partes.push(conta.vincular + (conta.vincular === 1 ? " item dá entrada" : " itens dão entrada") + " em produtos que já existem");
    if (conta.criar) partes.push(conta.criar + (conta.criar === 1 ? " produto novo é criado" : " produtos novos são criados") + " (sem preço de venda)");
    if (conta.ignorar) partes.push(conta.ignorar + (conta.ignorar === 1 ? " item fica" : " itens ficam") + " sem entrada no estoque");
    const quantas = !gerar ? 0 : (semParcelas ? 1 : nota.parcelas.length);
    const resposta = await M.confirmar({
      titulo: "Importar a NF " + nota.numero + "?",
      texto: partes.join("; ") + ". " + (quantas ? quantas + (quantas === 1 ? " conta a pagar é criada. " : " contas a pagar são criadas. ") : "Nenhuma conta a pagar é criada. ")
        + "O estoque e o custo dos produtos são atualizados. Depois de importar, só o estorno da nota desfaz.",
      sim: "Importar a nota",
    });
    if (!resposta.ok) return;
    const r = await M.api("POST", "/api/compras/importar", {
      xml: xml,
      itens: decisoes,
      gerar_contas: gerar,
      categoria_id: gerar && form.categoria.value ? Number(form.categoria.value) : null,
      vencimento_sem_parcelas: vencimento,
    });
    if (!r.ok) { M.mensagem(form, r.erro); return; }
    desenharFeito(r.dados);
  });

  function desenharFeito(feito) {
    const n = feito.nota;
    const itens = [M.el("li", null, M.el("b", { text: "NF " + n.numero + " de " + n.fornecedor_nome }), ", total de " + M.formatarCentavos(n.total_centavos) + ".")];
    n.itens.forEach(function (i) {
      if (i.entrou === null) itens.push(M.el("li", { class: "apagado", text: i.descricao + ": sem entrada no estoque." }));
      else itens.push(M.el("li", null, M.el("b", { text: i.produto_descricao }), ": entraram " + M.qtd(i.entrou) + " " + i.produto_unidade + " a " + M.formatarCentavos(i.custo_unitario_centavos) + " cada."));
    });
    feito.produtos_criados.forEach(function (p) {
      itens.push(M.el("li", { class: "destaque" }, "Produto novo: ", M.el("b", { text: p.descricao }), " (código " + p.codigo + "). Ele está SEM preço de venda: cadastre o preço em ", M.el("a", { href: "/produtos", text: "Produtos" }), " para poder vender."));
    });
    itens.push(M.el("li", null, feito.contas_a_pagar
      ? (feito.contas_a_pagar === 1 ? "1 conta a pagar criada" : feito.contas_a_pagar + " contas a pagar criadas") + " em "
      : "Nenhuma conta a pagar foi criada. Se a compra foi paga, lance o pagamento em ",
      M.el("a", { href: "/financeiro#lancamentos", text: "Financeiro" }), "."));
    M.trocar.apply(null, [raiz.querySelector("[data-feito]")].concat(itens));
    xml = "";
    nota = null;
    linhas = [];
    passo("feito");
    M.avisar("Nota importada: estoque e custo atualizados.");
    document.getElementById("btn-outra").focus();
  }

  // ------------------------------------------------------------------ notas importadas
  function linhaUnica(texto) {
    M.trocar(corpoNotas, M.el("tr", null, M.el("td", { class: "sem-linhas", colSpan: 8, text: texto })));
  }

  async function carregarNotas() {
    const r = await M.api("GET", "/api/compras?limite=200");
    if (!r.ok) { linhaUnica("Não foi possível carregar as notas: " + r.erro); return; }
    if (!r.dados.length) { linhaUnica("Nenhuma nota importada até agora. Use a aba “Importar XML”."); return; }
    M.trocar.apply(null, [corpoNotas].concat(r.dados.map(function (n) {
      const estornada = !!n.estornada_em;
      return M.el("tr", { class: estornada ? "inativa" : "" },
        M.el("td", { text: M.dataHora(n.importada_em) }),
        M.el("td", null, n.fornecedor_nome, M.el("span", { class: "sub", text: n.fornecedor_documento })),
        M.el("td", { text: String(n.numero), title: "Série " + n.serie + " · emitida em " + data(n.emitida_em) + " · chave " + n.chave }),
        M.el("td", { class: "num", text: M.reais(n.total_centavos) }),
        M.el("td", { class: "num", text: String(n.itens_quantidade) }),
        M.el("td", { class: "num", text: n.contas_a_pagar ? String(n.contas_a_pagar) : "—", title: n.contas_a_pagar ? "" : "nenhuma conta a pagar ligada a esta nota" }),
        M.el("td", null, M.el("span", { class: "tag " + (estornada ? "inativo" : "ativo"), text: estornada ? "Estornada" : "Importada", title: estornada ? "Estornada em " + M.dataHora(n.estornada_em) + ". Motivo: " + (n.motivo_estorno || "não informado") : "" })),
        M.el("td", { class: "acoes-linha" },
          M.el("button", { type: "button", class: "btn3d mini", text: "Ver", "aria-label": "Ver a nota " + n.numero, onclick: function () { verNota(n); } }),
          estornada ? null : M.el("button", { type: "button", class: "btn3d mini", text: "Estornar", "aria-label": "Estornar a nota " + n.numero, onclick: function () { estornar(n); } })));
    })));
  }

  async function verNota(n) {
    const r = await M.api("GET", "/api/compras/" + n.id);
    if (!r.ok) { M.avisar(r.erro); return; }
    const d = r.dados;
    dlgNota.querySelector("h2").textContent = "NF " + d.numero + " de " + d.fornecedor_nome;
    dlgNota.querySelector("[data-texto]").textContent = "Emitida em " + data(d.emitida_em) + ", importada em " + M.dataHora(d.importada_em) + ". Total " + M.formatarCentavos(d.total_centavos) + "."
      + (d.estornada_em ? " ESTORNADA em " + M.dataHora(d.estornada_em) + " (" + (d.motivo_estorno || "sem motivo") + "): as entradas abaixo foram desfeitas." : "");
    M.trocar.apply(null, [dlgNota.querySelector("tbody")].concat(d.itens.map(function (i) {
      const entrou = i.entrou !== null;
      return M.el("tr", null,
        M.el("td", { text: i.numero === null ? "—" : String(i.numero) }),
        M.el("td", null, i.descricao, M.el("span", { class: "sub", text: "cód. " + i.codigo_fornecedor })),
        M.el("td", { class: "num", text: M.qtd(i.quantidade) + " " + i.unidade }),
        M.el("td", { class: "num", text: M.reais(i.custo_total_centavos) }),
        M.el("td", { text: entrou ? i.produto_descricao : "—", title: entrou ? "cód. " + i.produto_codigo : "item sem entrada no estoque" }),
        M.el("td", { class: "num", text: entrou ? M.qtd(i.entrou) + " " + i.produto_unidade : "—" }),
        M.el("td", { class: "num", text: entrou ? M.reais(i.custo_unitario_centavos) : "—" }));
    })));
    dlgNota.showModal();
  }

  async function estornar(n) {
    const resposta = await M.confirmar({
      titulo: "Estornar a NF " + n.numero + "?",
      texto: n.fornecedor_nome + ", " + M.formatarCentavos(n.total_centavos) + ". O que entrou no estoque por esta nota sai de novo, o custo dos produtos volta e as contas a pagar em aberto desta nota são canceladas. A nota fica no histórico como estornada e pode ser importada de novo.",
      sim: "Estornar a nota",
      perigo: true,
      motivo: "obrigatorio",
    });
    if (!resposta.ok) return;
    const r = await M.api("POST", "/api/compras/" + n.id + "/estornar", { motivo: resposta.motivo });
    if (!r.ok) { mensagemSolta(msgNotas, "NF " + n.numero + ": " + r.erro); return; }
    const conferir = r.dados.custos_para_conferir;
    mensagemSolta(msgNotas, conferir.length ? "NF " + n.numero + " estornada. Não deu para refazer sozinho o custo de: " + conferir.join(", ") + ". Confira o custo em Produtos." : "");
    M.avisar("NF " + n.numero + " estornada: estoque e contas desfeitos.");
    carregarNotas();
  }

  raiz.querySelectorAll("[data-aba]").forEach(function (botao) {
    botao.addEventListener("click", function () { mostrarAba(botao.dataset.aba); });
  });
  raiz.querySelector('[data-passo="conferir"] .rolagem').addEventListener("scroll", fecharSugestoes);
  // Mexeu numa decisão: a mensagem de erro anterior já não vale.
  corpoItens.addEventListener("input", function () { M.mensagem(form, ""); });
  corpoItens.addEventListener("change", function () { M.mensagem(form, ""); });
  lote.addEventListener("click", function () { M.mensagem(form, ""); });
  form.gerar_contas.addEventListener("change", function () { M.mensagem(form, ""); });

  (async function iniciar() {
    const status = await M.api("GET", "/api/status");
    hoje = status.ok && status.dados.agora ? status.dados.agora.slice(0, 10) : "";
    const r = await M.api("GET", "/api/financeiro/categorias");
    const categorias = (r.ok ? r.dados : []).filter(function (c) { return c.serve_para.indexOf("despesa") >= 0; });
    categorias.forEach(function (c) { form.categoria.appendChild(M.el("option", { value: String(c.id), text: c.nome })); });
    const padrao = categorias.find(function (c) { return c.nome === "Compra de mercadorias para revenda"; });
    if (padrao) form.categoria.value = String(padrao.id);
    if (window.location.hash === "#notas") mostrarAba("notas");
  })();
})();

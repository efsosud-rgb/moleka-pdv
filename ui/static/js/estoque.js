/* Moleka PDV — tela Estoque (só o gerente): saldos, entrada, saída, contagem e histórico.
   Todos os números vêm de /api/estoque. A única conta feita aqui é a do aviso de confirmação
   ("o saldo passa de 48 para 44"), em milésimos inteiros; o saldo que fica é o que o servidor
   devolve. */

(function () {
  "use strict";

  const M = window.Moleka;
  const raiz = document.getElementById("estoque");
  if (!raiz) return;

  const corpo = raiz.querySelector("#tabela-estoque tbody");
  const busca = document.getElementById("busca");
  const situacao = document.getElementById("situacao");
  const verInativos = document.getElementById("ver-inativos");
  const contagem = raiz.querySelector("[data-contagem]");
  const form = document.getElementById("form-movimento");
  const dlgHistorico = document.getElementById("dlg-historico");

  const SITUACOES = {
    ok: { texto: "Em dia", classe: "ativo" },
    abaixo: { texto: "Baixo", classe: "alerta" },
    zerado: { texto: "Zerado", classe: "comum" },
    negativo: { texto: "Negativo", classe: "perigo" },
  };
  const TEXTOS = {
    entrada: { qtd: "Quantidade que entra", motivo: "Motivo", exemplo: "Por exemplo: produção do dia, compra sem nota", dica: "" },
    saida: { qtd: "Quantidade que sai", motivo: "Motivo", exemplo: "Por exemplo: quebra, consumo, validade vencida", dica: "" },
    contagem: {
      qtd: "Quantidade contada", motivo: "Observação (opcional)", exemplo: "Por exemplo: inventário do mês",
      dica: "Conte o que há de verdade na loja e digite. O sistema grava só a diferença.",
    },
  };

  let itens = [];
  let escolhido = null; // id do produto aberto na ficha
  let relogioDaBusca = 0;

  function linhaUnica(texto) {
    M.trocar(corpo, M.el("tr", null, M.el("td", { class: "sem-linhas", colSpan: 5, text: texto })));
  }

  function quantidade(valor, unidade) {
    return M.qtd(valor) + " " + unidade;
  }

  /* Milésimos inteiros, para somar e subtrair quantidades sem erro de casas decimais. */
  function milesimos(valor) { return Math.round(Number(valor) * 1000); }

  function item(id) { return itens.find(function (i) { return i.produto_id === id; }) || null; }

  // ------------------------------------------------------------------ desenho
  function desenharResumo(r) {
    const valores = {
      com_saldo: String(r.com_saldo),
      com_saldo_m: "de " + r.produtos + (r.produtos === 1 ? " produto ativo" : " produtos ativos"),
      abaixo: String(r.abaixo_do_minimo),
      negativos: String(r.negativos),
      valor: r.valor_centavos === null ? "—" : M.formatarCentavos(r.valor_centavos),
      valor_m: r.valor_centavos === null
        ? "Sem dados: " + r.motivo_do_valor + "."
        : (r.motivo_do_valor ? r.motivo_do_valor + "." : "saldo × custo médio de cada produto"),
    };
    raiz.querySelectorAll("[data-kpi]").forEach(function (el) { el.textContent = valores[el.dataset.kpi] || "—"; });
  }

  function desenharLista() {
    contagem.textContent = itens.length + (itens.length === 1 ? " produto" : " produtos");
    if (!itens.length) {
      const filtrado = busca.value.trim() || situacao.value;
      linhaUnica(filtrado ? "Nenhum produto com esse filtro." : "Nenhum produto cadastrado. Cadastre em Produtos (F5).");
      return;
    }
    M.trocar.apply(null, [corpo].concat(itens.map(function (i) {
      const s = SITUACOES[i.situacao] || SITUACOES.ok;
      const negativo = Number(i.saldo) < 0;
      return M.el("tr", { class: (i.produto_id === escolhido ? "selecionada" : "") + (i.ativo ? "" : " inativa") },
        M.el("td", null, i.descricao, M.el("span", { class: "sub", text: "cód. " + i.codigo + (i.categoria ? " · " + i.categoria : "") })),
        M.el("td", { class: "num" + (negativo ? " negativo" : ""), text: quantidade(i.saldo, i.unidade) }),
        M.el("td", { class: "num", text: i.custo_centavos === null ? "—" : M.reais(i.custo_centavos), title: i.custo_centavos === null ? "sem custo cadastrado" : "" }),
        M.el("td", null, M.el("span", { class: "tag " + s.classe, text: s.texto, title: i.situacao === "abaixo" ? "Abaixo do mínimo, que é " + quantidade(i.estoque_minimo, i.unidade) : "" })),
        M.el("td", null, M.el("button", { type: "button", class: "btn3d mini", text: "Movimentar", "aria-label": "Movimentar " + i.descricao, onclick: function () { escolher(i.produto_id); } })));
    })));
  }

  function desenharFicha() {
    const i = escolhido === null ? null : item(escolhido);
    raiz.querySelectorAll("[data-estado]").forEach(function (el) { el.hidden = el.dataset.estado !== (i ? "produto" : "nenhum"); });
    if (!i) return;
    const valores = {
      descricao: i.descricao,
      saldo: quantidade(i.saldo, i.unidade),
      custo: i.custo_centavos === null ? "—" : M.formatarCentavos(i.custo_centavos),
      valor: i.valor_centavos === null ? "—" : M.formatarCentavos(i.valor_centavos),
    };
    const motivos = {
      custo: i.custo_centavos === null ? "sem custo cadastrado: informe o custo numa entrada ou no cadastro do produto" : (i.ultimo_custo_centavos === null ? "" : "custo da última entrada: " + M.formatarCentavos(i.ultimo_custo_centavos)),
      valor: i.valor_centavos === null ? (i.custo_centavos === null ? "sem custo cadastrado" : "sem saldo") : "saldo × custo médio",
    };
    raiz.querySelectorAll("[data-ficha]").forEach(function (el) {
      el.textContent = valores[el.dataset.ficha] || "—";
      el.title = motivos[el.dataset.ficha] || "";
    });
  }

  function ajustarFormulario() {
    const t = TEXTOS[form.tipo.value];
    form.querySelector("[data-rotulo-qtd]").textContent = t.qtd;
    form.querySelector("[data-rotulo-motivo]").textContent = t.motivo;
    form.motivo.placeholder = t.exemplo;
    form.querySelector("[data-so-entrada]").hidden = form.tipo.value !== "entrada";
    const dica = form.querySelector("[data-dica]");
    dica.textContent = t.dica;
    dica.hidden = !t.dica;
  }

  function escolher(id) {
    escolhido = id;
    form.reset();
    M.mensagem(form, "");
    ajustarFormulario();
    desenharLista();
    desenharFicha();
    form.quantidade.focus();
  }

  // ------------------------------------------------------------------ carga
  async function carregar() {
    const filtros = new URLSearchParams();
    if (busca.value.trim()) filtros.set("busca", busca.value.trim());
    if (situacao.value) filtros.set("situacao", situacao.value);
    if (verInativos.checked) filtros.set("inativos", "true");
    const vale = M.novaCarga("estoque");
    const r = await M.api("GET", "/api/estoque?" + filtros.toString());
    if (!vale()) return; // já saiu uma pesquisa mais nova: esta resposta não serve mais
    if (!r.ok) { contagem.textContent = "—"; linhaUnica("Não foi possível carregar o estoque: " + r.erro); return; }
    itens = r.dados.itens;
    desenharResumo(r.dados.resumo);
    desenharLista();
    desenharFicha();
  }

  // ------------------------------------------------------------------ lançar entrada, saída ou contagem
  /* Quantidade digitada: "10", "2,350" ou "2.5". Devolve { valor } (com ponto decimal) ou { erro }.
     "1.000" é recusado: com ponto e três casas não dá para saber se é mil ou um. */
  function lerQuantidade(texto) {
    const limpo = texto.trim();
    if (/^\d+\.\d{3}$/.test(limpo)) return { erro: "Com ponto fica a dúvida: " + limpo + " é " + limpo.replace(".", "") + " ou " + limpo.replace(".", ",") + "? Digite sem o ponto, ou com vírgula." };
    if (!/^\d+([.,]\d{1,3})?$/.test(limpo)) return { erro: "" };
    return { valor: limpo.replace(",", ".") };
  }

  form.addEventListener("submit", async function (evento) {
    evento.preventDefault();
    const i = item(escolhido);
    if (!i) return;
    const tipo = form.tipo.value;
    const lida = lerQuantidade(form.quantidade.value);
    const qtd = lida.valor;
    if (qtd === undefined || (tipo !== "contagem" && Number(qtd) <= 0)) {
      M.mensagem(form, lida.erro || (tipo === "contagem" ? "Digite a quantidade contada (se não há nenhum, digite 0)." : "Digite a quantidade. Por exemplo: 10 ou 2,5"));
      form.quantidade.focus();
      return;
    }
    const motivo = form.motivo.value.trim();
    if (tipo !== "contagem" && !motivo) { M.mensagem(form, "Escreva o motivo (fica registrado no histórico)."); form.motivo.focus(); return; }
    let custo = null;
    if (tipo === "entrada" && form.custo.value.trim()) {
      custo = M.lerReais(form.custo.value);
      if (custo === null || custo < 0) { M.mensagem(form, "Custo inválido. Digite assim: 2,50"); form.custo.focus(); return; }
    }
    M.mensagem(form, "");

    const antes = milesimos(i.saldo);
    const digitado = milesimos(qtd);
    const texto = quantidade(qtd, i.unidade);
    let pergunta;
    if (tipo === "entrada") {
      pergunta = {
        titulo: "Dar entrada de " + texto + "?",
        texto: i.descricao + ": o saldo passa de " + quantidade(i.saldo, i.unidade) + " para " + quantidade((antes + digitado) / 1000, i.unidade) + ". "
          + (custo === null ? "Sem custo informado: o custo médio não muda. " : "Custo de " + M.formatarCentavos(custo) + " cada: o custo médio é refeito. ")
          + "Fica registrado com o seu nome.",
        sim: "Dar entrada",
      };
    } else if (tipo === "saida") {
      pergunta = {
        titulo: "Dar saída de " + texto + "?",
        texto: i.descricao + ": o saldo passa de " + quantidade(i.saldo, i.unidade) + " para " + quantidade((antes - digitado) / 1000, i.unidade) + ". Motivo: " + motivo + ". Fica registrado com o seu nome.",
        sim: "Dar saída",
        perigo: true,
      };
    } else if (digitado !== antes) {
      const diferenca = (digitado - antes) / 1000;
      pergunta = {
        titulo: "Gravar a contagem de " + texto + "?",
        texto: i.descricao + ": o sistema tem " + quantidade(i.saldo, i.unidade) + " e você contou " + texto + ". Será lançada a diferença de " + (diferenca > 0 ? "+" : "") + quantidade(diferenca, i.unidade) + ". Fica registrado com o seu nome.",
        sim: "Gravar a contagem",
        perigo: diferenca < 0,
      };
    }
    if (pergunta) {
      const resposta = await M.confirmar(pergunta);
      if (!resposta.ok) return;
    }

    const r = tipo === "contagem"
      ? await M.api("POST", "/api/estoque/contagens", { produto_id: i.produto_id, contado: qtd, motivo: motivo })
      : await M.api("POST", "/api/estoque/ajustes", { produto_id: i.produto_id, tipo: tipo, quantidade: qtd, motivo: motivo, custo_unitario_centavos: custo });
    if (!r.ok) { M.mensagem(form, r.erro); return; }
    const novo = tipo === "contagem" ? r.dados.item : r.dados;
    const saldo = quantidade(novo.saldo, novo.unidade);
    if (tipo === "contagem" && Number(r.dados.diferenca) === 0) M.avisar("A contagem bateu com o sistema (" + saldo + "): nada foi alterado.");
    else M.avisar({ entrada: "Entrada lançada", saida: "Saída lançada", contagem: "Contagem gravada" }[tipo] + ". Saldo de " + novo.descricao + ": " + saldo + ".");
    form.reset();
    form.tipo.value = tipo;
    ajustarFormulario();
    await carregar();
    form.quantidade.focus();
  });

  // ------------------------------------------------------------------ histórico
  document.getElementById("btn-historico").addEventListener("click", async function () {
    const i = item(escolhido);
    if (!i) return;
    const r = await M.api("GET", "/api/estoque/" + i.produto_id + "/movimentos?limite=200");
    if (!r.ok) { M.avisar("Não foi possível carregar o histórico: " + r.erro); return; }
    const corpoHistorico = dlgHistorico.querySelector("tbody");
    dlgHistorico.querySelector("h2").textContent = "Histórico de " + i.descricao;
    dlgHistorico.querySelector("[data-texto]").textContent = r.dados.length
      ? "Do mais novo para o mais antigo" + (r.dados.length >= 200 ? " (os últimos 200 movimentos)" : "") + ". Saldo atual: " + quantidade(i.saldo, i.unidade) + "."
      : "";
    if (!r.dados.length) {
      M.trocar(corpoHistorico, M.el("tr", null, M.el("td", { class: "sem-linhas", colSpan: 7, text: "Este produto ainda não teve movimento de estoque." })));
    } else {
      M.trocar.apply(null, [corpoHistorico].concat(r.dados.map(function (m) {
        const q = Number(m.quantidade);
        return M.el("tr", null,
          M.el("td", { text: M.dataHora(m.em) }),
          M.el("td", { text: m.rotulo }),
          M.el("td", { class: "num " + (q < 0 ? "negativo" : "positivo"), text: (q > 0 ? "+" : "") + M.qtd(m.quantidade) }),
          M.el("td", { class: "num", text: M.qtd(m.saldo_depois) }),
          M.el("td", { class: "num", text: m.custo_unitario_centavos === null ? "—" : M.reais(m.custo_unitario_centavos), title: m.custo_unitario_centavos === null ? "movimento sem custo" : "" }),
          M.el("td", { text: m.motivo || "—" }),
          M.el("td", { text: m.operador || "—" }));
      })));
    }
    dlgHistorico.showModal();
  });

  // ------------------------------------------------------------------ imprimir (impressora comum)
  document.getElementById("btn-imprimir").addEventListener("click", function () {
    const pesquisa = busca.value.trim();
    M.imprimirRelatorio({
      titulo: "Posição do estoque",
      detalhes: ["Lista: " + situacao.selectedOptions[0].textContent + (pesquisa ? " · pesquisa “" + pesquisa + "”" : "")
        + (verInativos.checked ? " · com os inativos" : "") + " · " + contagem.textContent],
      resumo: M.cartoesParaOPapel(raiz),
      tabelas: [document.getElementById("tabela-estoque")],
    });
  });

  // A planilha leva a mesma lista da tela: mesma pesquisa, mesmo filtro.
  document.getElementById("btn-excel").addEventListener("click", function () {
    const filtros = new URLSearchParams();
    if (busca.value.trim()) filtros.set("busca", busca.value.trim());
    if (situacao.value) filtros.set("situacao", situacao.value);
    if (verInativos.checked) filtros.set("inativos", "true");
    M.baixarPlanilha("/api/planilhas/estoque?" + filtros.toString());
  });

  form.tipo.addEventListener("change", function () { M.mensagem(form, ""); ajustarFormulario(); });
  situacao.addEventListener("change", carregar);
  verInativos.addEventListener("change", carregar);
  busca.addEventListener("input", function () { clearTimeout(relogioDaBusca); relogioDaBusca = setTimeout(carregar, 250); });

  ajustarFormulario();
  carregar();
})();

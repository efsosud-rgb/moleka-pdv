/* Moleka PDV — tela Financeiro (só o gerente): contas a pagar e a receber, fluxo de caixa, DRE,
   rentabilidade por produto e categorias. Todos os números vêm de /api/financeiro; a tela não
   faz conta nenhuma. Sem dado, mostra "—" e o motivo que o servidor manda. */

(function () {
  "use strict";

  const M = window.Moleka;
  const raiz = document.getElementById("financeiro");
  if (!raiz) return;

  const ABAS = ["lancamentos", "fluxo", "dre", "rentabilidade", "categorias"];
  const SEMANA = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"];
  const FORMAS = { dinheiro: "Dinheiro", pix: "Pix", debito: "Débito", credito: "Crédito" };
  const DICAS_DOS_GRUPOS = {
    receita_bruta: "Vendas feitas fora do caixa (encomendas, eventos). Somam na receita do DRE.",
    deducao: "Impostos sobre a venda (DAS) e taxas de cartão e Pix. Diminuem a receita líquida.",
    cmv: "Custo do que foi vendido, lançado como despesa: matéria-prima, embalagens. Entra no CMV do DRE.",
    despesa_operacional: "Despesas para a loja funcionar: aluguel, luz, água, salários, contador.",
    outras_receitas: "Receitas que não são venda: rendimentos, reembolsos.",
    outras_despesas: "Despesas fora da rotina: multas, juros, perdas.",
    fora_do_dre: "Saídas que só entram no fluxo de caixa, não no resultado: compra de mercadoria para revenda (o custo dela já aparece no CMV quando o produto é vendido), retirada dos sócios, parcela de empréstimo.",
    entrada_fora_do_dre: "Entradas que só entram no fluxo de caixa, não no resultado: dinheiro que os sócios puseram na loja, empréstimo recebido.",
  };

  const periodo = document.getElementById("periodo");
  const pdInicio = document.getElementById("pd-inicio");
  const pdFim = document.getElementById("pd-fim");
  const lcTipo = document.getElementById("lc-tipo");
  const lcSituacao = document.getElementById("lc-situacao");
  const dlgLancamento = document.getElementById("dlg-lancamento");
  const formLancamento = document.getElementById("form-lancamento");
  const dlgBaixa = document.getElementById("dlg-baixa");
  const formBaixa = document.getElementById("form-baixa");
  const formCategoria = document.getElementById("form-categoria");

  let hoje = ""; // a data da loja, dita pelo servidor (AAAA-MM-DD)
  let aba = "lancamentos";
  let categorias = []; // todas, inclusive inativas
  let grupos = [];
  let editando = null; // lançamento em alteração
  let baixando = null; // lançamento recebendo a baixa
  let categoriaEmEdicao = null;

  // ------------------------------------------------------------------ datas e período
  function partes(texto) {
    const p = /^(\d{4})-(\d{2})-(\d{2})/.exec(texto || "");
    return p ? { a: Number(p[1]), m: Number(p[2]), d: Number(p[3]) } : null;
  }

  function iso(a, m, d) {
    return a + "-" + String(m).padStart(2, "0") + "-" + String(d).padStart(2, "0");
  }

  function ultimoDia(a, m) { return new Date(a, m, 0).getDate(); }

  function somarDias(texto, n) {
    const p = partes(texto);
    const dia = new Date(p.a, p.m - 1, p.d + n);
    return iso(dia.getFullYear(), dia.getMonth() + 1, dia.getDate());
  }

  /* "03/12/2026" */
  function data(texto) {
    const p = partes(texto);
    return p ? String(p.d).padStart(2, "0") + "/" + String(p.m).padStart(2, "0") + "/" + p.a : "—";
  }

  /* "03/12" */
  function diaMes(texto) { return data(texto).slice(0, 5); }

  function diaDaSemana(texto) {
    const p = partes(texto);
    return p ? SEMANA[new Date(p.a, p.m - 1, p.d).getDay()] : "";
  }

  /* [início, fim] do período escolhido, ou null se as datas digitadas não servem. */
  function intervalo() {
    const h = partes(hoje);
    if (!h) return null;
    switch (periodo.value) {
      case "mes-passado": {
        const m = h.m === 1 ? 12 : h.m - 1;
        const a = h.m === 1 ? h.a - 1 : h.a;
        return [iso(a, m, 1), iso(a, m, ultimoDia(a, m))];
      }
      case "hoje": return [hoje, hoje];
      case "7": return [somarDias(hoje, -6), hoje];
      case "30": return [somarDias(hoje, -29), hoje];
      case "prox30": return [hoje, somarDias(hoje, 29)];
      case "mes-que-vem": {
        const m = h.m === 12 ? 1 : h.m + 1;
        const a = h.m === 12 ? h.a + 1 : h.a;
        return [iso(a, m, 1), iso(a, m, ultimoDia(a, m))];
      }
      case "ano": return [iso(h.a, 1, 1), iso(h.a, 12, 31)];
      case "datas": {
        const inicio = M.lerData(pdInicio.value);
        const fim = M.lerData(pdFim.value);
        return inicio && fim ? [inicio, fim] : null;
      }
      default: return [iso(h.a, h.m, 1), iso(h.a, h.m, ultimoDia(h.a, h.m))];
    }
  }

  function textoDoPeriodo(inicio, fim) {
    return inicio === fim ? data(inicio) : data(inicio) + " a " + data(fim);
  }

  function linhaUnica(corpo, colunas, texto) {
    M.trocar(corpo, M.el("tr", null, M.el("td", { class: "sem-linhas", colSpan: colunas, text: texto })));
  }

  function preencher(seletor, atributo, valores, motivos) {
    raiz.querySelectorAll(seletor).forEach(function (el) {
      const chave = el.dataset[atributo];
      el.textContent = valores[chave] === undefined || valores[chave] === null ? "—" : valores[chave];
      el.title = (motivos && motivos[chave]) || "";
    });
  }

  function dinheiro(centavos) {
    return centavos === null || centavos === undefined ? "—" : M.formatarCentavos(centavos);
  }

  /* Resposta que chegou depois de outra carga mais nova ter começado: é descartada. */
  const VELHA = {};

  /* Pede uma visão do período à API. Devolve os dados; null depois de mostrar o erro; ou VELHA
     quando, na volta, `vale()` diz que já há uma carga mais nova (ver Moleka.novaCarga). */
  async function pedir(caminho, corpo, colunas, extras, vale) {
    const faixa = intervalo();
    if (!faixa) { linhaUnica(corpo, colunas, "Digite a data inicial e a data final do período, assim: 01/11/2026."); return null; }
    const consulta = new URLSearchParams({ inicio: faixa[0], fim: faixa[1] });
    Object.keys(extras || {}).forEach(function (chave) { if (extras[chave]) consulta.set(chave, extras[chave]); });
    const r = await M.api("GET", caminho + "?" + consulta.toString());
    if (!vale()) return VELHA;
    if (!r.ok) { linhaUnica(corpo, colunas, "Não foi possível carregar: " + r.erro); return null; }
    return r.dados;
  }

  // ------------------------------------------------------------------ contas a pagar e a receber
  const corpoLancamentos = raiz.querySelector("#tabela-lancamentos tbody");
  const faixaFora = raiz.querySelector("[data-lc-fora]");
  const textoFora = raiz.querySelector("[data-lc-fora-texto]");

  /* `dados`: as contas com vencimento no período. `abertas`: tudo o que está em aberto, de
     qualquer data, quando é esse o filtro da lista (os dois primeiros cartões acompanham). */
  function desenharTotais(dados, abertas) {
    const t = dados.totais;
    const tem = dados.itens.length > 0;
    const sem = "Sem dados: nenhuma conta com vencimento no período.";
    const valores = {
      a_pagar: tem ? dinheiro(t.a_pagar) : "—",
      a_pagar_m: !tem ? sem : (t.vencido_a_pagar ? dinheiro(t.vencido_a_pagar) + " já venceu" : "nada vencido no período"),
      a_receber: tem ? dinheiro(t.a_receber) : "—",
      a_receber_m: !tem ? sem : (t.vencido_a_receber ? dinheiro(t.vencido_a_receber) + " já venceu" : "nada vencido no período"),
      pago: tem ? dinheiro(t.pago) : "—",
      pago_m: tem ? "das contas com vencimento no período" : sem,
      recebido: tem ? dinheiro(t.recebido) : "—",
      recebido_m: tem ? "das contas com vencimento no período" : sem,
    };
    if (abertas) {
      const a = abertas.totais;
      const texto = function (vencido) { return "em aberto, de qualquer data" + (vencido ? " · " + dinheiro(vencido) + " já venceu" : ""); };
      valores.a_pagar = dinheiro(a.a_pagar);
      valores.a_pagar_m = texto(a.vencido_a_pagar);
      valores.a_receber = dinheiro(a.a_receber);
      valores.a_receber_m = texto(a.vencido_a_receber);
    }
    preencher("[data-lk]", "lk", valores);
  }

  function etiquetaDaSituacao(l) {
    const despesa = l.tipo === "despesa";
    if (l.situacao === "pago") return M.el("span", { class: "tag ativo", text: (despesa ? "Pago " : "Recebido ") + diaMes(l.pago_em), title: (despesa ? "Pago em " : "Recebido em ") + data(l.pago_em) + (l.forma_rotulo ? ", em " + l.forma_rotulo : "") });
    if (l.situacao === "vencido") return M.el("span", { class: "tag perigo", text: "Vencido" });
    if (l.situacao === "cancelado") return M.el("span", { class: "tag inativo", text: "Cancelado" });
    return M.el("span", { class: "tag comum", text: "Em aberto" });
  }

  function botao(texto, rotulo, acao) {
    return M.el("button", { type: "button", class: "btn3d mini", text: texto, "aria-label": rotulo, onclick: acao });
  }

  function linhaDoLancamento(l) {
    const despesa = l.tipo === "despesa";
    const detalhes = [l.categoria];
    if (l.origem === "compra") detalhes.push("da nota de compra");
    if (l.competencia !== l.vencimento) detalhes.push("competência " + data(l.competencia));
    const acoes = [];
    if (l.situacao === "aberto" || l.situacao === "vencido") {
      acoes.push(botao("Dar baixa", "Dar baixa em " + l.descricao, function () { abrirBaixa(l); }));
      acoes.push(botao("Alterar", "Alterar " + l.descricao, function () { abrirLancamento(l); }));
      if (l.origem !== "compra") acoes.push(botao("Cancelar", "Cancelar " + l.descricao, function () { cancelar(l); }));
    } else if (l.situacao === "pago") {
      acoes.push(botao("Desfazer baixa", "Desfazer a baixa de " + l.descricao, function () { desfazerBaixa(l); }));
    }
    const celulaDeAcoes = M.el("td", { class: "acoes-linha", title: l.origem === "compra" && l.situacao !== "pago" && l.situacao !== "cancelado" ? "Conta de nota de compra: para tirá-la, estorne a nota em Entrada de NF." : "" });
    acoes.forEach(function (b) { celulaDeAcoes.appendChild(b); });
    return M.el("tr", { class: l.situacao === "cancelado" ? "inativa" : "" },
      M.el("td", { text: data(l.vencimento) }),
      M.el("td", null, l.descricao, M.el("span", { class: "sub", text: detalhes.join(" · ") })),
      M.el("td", null, M.el("span", { class: "tag " + (despesa ? "despesa" : "receita"), text: despesa ? "Despesa" : "Receita" })),
      M.el("td", { class: "num", text: M.reais(l.valor_centavos) }),
      M.el("td", null, etiquetaDaSituacao(l)),
      celulaDeAcoes);
  }

  async function carregarLancamentos() {
    const vale = M.novaCarga("lancamentos");
    // Os filtros valem como estavam quando a carga começou.
    const tipo = lcTipo.value;
    const situacao = lcSituacao.value;
    const filtrado = !!(tipo || situacao);
    const caminho = "/api/financeiro/lancamentos";
    const dados = await pedir(caminho, corpoLancamentos, 6, { tipo: tipo, situacao: situacao }, vale);
    if (dados === VELHA) return;
    const contagem = raiz.querySelector("[data-lc-contagem]");
    if (!dados) { contagem.textContent = "—"; faixaFora.hidden = true; return; }
    // Os cartões de cima são sempre do período inteiro, mesmo com a lista filtrada.
    const doPeriodo = filtrado ? await pedir(caminho, corpoLancamentos, 6, null, vale) : dados;
    if (doPeriodo === VELHA) return;
    // Com o filtro "em aberto (qualquer data)", "A pagar" e "A receber" somam tudo o que está em
    // aberto, de despesas e de receitas, mesmo que a lista mostre só um dos tipos.
    let abertas = null;
    if (situacao === "todas_em_aberto") abertas = tipo ? await pedir(caminho, corpoLancamentos, 6, { situacao: situacao }, vale) : dados;
    if (abertas === VELHA) return;
    if (doPeriodo) desenharTotais(doPeriodo, abertas);
    const n = dados.itens.length;
    const deQualquerData = situacao === "vencido" || situacao === "todas_em_aberto";
    contagem.textContent = (n === 1 ? "1 lançamento" : n + " lançamentos") + (deQualquerData ? ", de qualquer data" : ", vencimento de " + textoDoPeriodo(dados.inicio, dados.fim));
    // Conta em aberto que vence fora do período não aparece na lista: a tela avisa que existe.
    const fora = dados.em_aberto_fora_do_periodo || 0;
    faixaFora.hidden = fora === 0;
    textoFora.textContent = fora === 1
      ? "Há mais 1 conta em aberto com vencimento fora deste período."
      : "Há mais " + fora + " contas em aberto com vencimento fora deste período.";
    if (!n) { linhaUnica(corpoLancamentos, 6, filtrado ? "Nenhum lançamento com esse filtro." : "Nenhuma conta com vencimento neste período. Use “Novo lançamento (F3)” para lançar uma despesa ou receita."); return; }
    M.trocar.apply(null, [corpoLancamentos].concat(dados.itens.map(linhaDoLancamento)));
  }

  // ---- novo lançamento e alteração
  function preencherCategoriasDoLancamento(tipo, atual) {
    const selecao = formLancamento.categoria;
    const servem = categorias.filter(function (c) { return c.serve_para.indexOf(tipo) >= 0 && (c.ativo || c.id === atual); });
    M.trocar.apply(null, [selecao, M.el("option", { value: "", text: servem.length ? "— escolha —" : "Nenhuma categoria para este tipo" })].concat(servem.map(function (c) {
      return M.el("option", { value: String(c.id), text: c.nome });
    })));
    selecao.value = atual ? String(atual) : "";
  }

  function ajustarTextosDoTipo() {
    const receita = formLancamento.tipo.value === "receita";
    formLancamento.querySelector("[data-rotulo-pago]").textContent = receita ? "Já foi recebido" : "Já foi pago";
    formLancamento.querySelector("[data-rotulo-data]").textContent = receita ? "Recebido em" : "Pago em";
    formLancamento.descricao.placeholder = receita ? "Por exemplo: encomenda da festa de sábado" : "Por exemplo: conta de luz de novembro";
  }

  function abrirLancamento(l) {
    editando = l || null;
    formLancamento.reset();
    M.mensagem(formLancamento, "");
    dlgLancamento.querySelector("h2").textContent = l ? "Alterar lançamento" : "Novo lançamento";
    formLancamento.tipo.disabled = !!l;
    formLancamento.querySelector("[data-so-no-novo]").hidden = !!l;
    formLancamento.querySelector("[data-pagamento]").hidden = true;
    if (l) {
      formLancamento.tipo.value = l.tipo;
      formLancamento.descricao.value = l.descricao;
      formLancamento.valor.value = M.reais(l.valor_centavos);
      formLancamento.vencimento.value = M.dataBR(l.vencimento);
      formLancamento.competencia.value = l.competencia === l.vencimento ? "" : M.dataBR(l.competencia);
    } else {
      formLancamento.vencimento.value = M.dataBR(hoje);
      formLancamento.pago_em.value = M.dataBR(hoje);
    }
    preencherCategoriasDoLancamento(formLancamento.tipo.value, l ? l.categoria_id : null);
    ajustarTextosDoTipo();
    dlgLancamento.showModal();
    (l ? formLancamento.descricao : formLancamento.tipo).focus();
  }

  formLancamento.tipo.addEventListener("change", function () {
    preencherCategoriasDoLancamento(formLancamento.tipo.value, null);
    ajustarTextosDoTipo();
  });
  formLancamento.ja_pago.addEventListener("change", function () {
    formLancamento.querySelector("[data-pagamento]").hidden = !formLancamento.ja_pago.checked;
  });

  formLancamento.addEventListener("submit", async function (evento) {
    evento.preventDefault();
    const f = formLancamento;
    if (!f.categoria.value) { M.mensagem(f, "Escolha a categoria."); f.categoria.focus(); return; }
    const descricao = f.descricao.value.trim();
    if (!descricao) { M.mensagem(f, "Escreva a descrição (por exemplo: conta de luz de novembro)."); f.descricao.focus(); return; }
    const valor = M.lerReais(f.valor.value);
    if (valor === null || valor <= 0) { M.mensagem(f, "Digite o valor. Assim: 150,00"); f.valor.focus(); return; }
    const vencimento = M.lerData(f.vencimento.value);
    if (!vencimento) { M.mensagem(f, "Digite o vencimento com dia, mês e ano. Assim: 15/11/2026"); f.vencimento.focus(); return; }
    const competencia = f.competencia.value.trim() ? M.lerData(f.competencia.value) : "";
    if (competencia === null) { M.mensagem(f, "Competência inválida. Digite assim: 15/11/2026 (ou deixe em branco)."); f.competencia.focus(); return; }
    const dados = {
      categoria_id: Number(f.categoria.value),
      descricao: descricao,
      valor_centavos: valor,
      vencimento: vencimento,
      competencia: competencia || null,
    };
    let r;
    if (editando) {
      r = await M.api("PUT", "/api/financeiro/lancamentos/" + editando.id, dados);
    } else {
      const pago = f.ja_pago.checked;
      const pagoEm = pago ? M.lerData(f.pago_em.value) : null;
      if (pago && !pagoEm) { M.mensagem(f, "Digite o dia do pagamento. Assim: 15/11/2026"); f.pago_em.focus(); return; }
      dados.tipo = f.tipo.value;
      dados.pago_em = pagoEm;
      dados.forma = pago && f.forma.value ? f.forma.value : null;
      r = await M.api("POST", "/api/financeiro/lancamentos", dados);
    }
    if (!r.ok) { M.mensagem(f, r.erro); return; }
    dlgLancamento.close();
    M.avisar((r.dados.tipo === "despesa" ? "Despesa" : "Receita") + " de " + M.formatarCentavos(r.dados.valor_centavos) + (editando ? " alterada." : " lançada."));
    editando = null;
    recarregar();
  });

  // ---- baixa, desfazer e cancelar
  function abrirBaixa(l) {
    baixando = l;
    formBaixa.reset();
    M.mensagem(formBaixa, "");
    const receita = l.tipo === "receita";
    dlgBaixa.querySelector("h2").textContent = receita ? "Marcar como recebido" : "Marcar como pago";
    dlgBaixa.querySelector("[data-texto]").textContent = l.descricao + ", " + M.formatarCentavos(l.valor_centavos) + ", vencimento em " + data(l.vencimento) + ".";
    formBaixa.querySelector("[data-rotulo-data]").textContent = receita ? "Recebido em" : "Pago em";
    formBaixa.data.value = M.dataBR(hoje);
    dlgBaixa.showModal();
    formBaixa.data.focus();
  }

  formBaixa.addEventListener("submit", async function (evento) {
    evento.preventDefault();
    if (!baixando) return;
    const dia = M.lerData(formBaixa.data.value);
    if (!dia) { M.mensagem(formBaixa, "Digite o dia. Assim: 15/11/2026"); formBaixa.data.focus(); return; }
    const r = await M.api("POST", "/api/financeiro/lancamentos/" + baixando.id + "/baixa", { data: dia, forma: formBaixa.forma.value || null });
    if (!r.ok) { M.mensagem(formBaixa, r.erro); return; }
    dlgBaixa.close();
    M.avisar(r.dados.descricao + ": " + (r.dados.tipo === "despesa" ? "pago" : "recebido") + " em " + data(r.dados.pago_em) + ".");
    baixando = null;
    recarregar();
  });

  async function desfazerBaixa(l) {
    const resposta = await M.confirmar({
      titulo: "Desfazer a baixa?",
      texto: l.descricao + ", " + M.formatarCentavos(l.valor_centavos) + ": volta a ficar em aberto, como se não tivesse sido " + (l.tipo === "despesa" ? "pago" : "recebido") + ".",
      sim: "Desfazer a baixa",
      perigo: true,
    });
    if (!resposta.ok) return;
    const r = await M.api("DELETE", "/api/financeiro/lancamentos/" + l.id + "/baixa");
    if (!r.ok) { M.avisar(r.erro); return; }
    M.avisar("Baixa desfeita: " + l.descricao + " voltou a ficar em aberto.");
    recarregar();
  }

  async function cancelar(l) {
    const resposta = await M.confirmar({
      titulo: "Cancelar este lançamento?",
      texto: l.descricao + ", " + M.formatarCentavos(l.valor_centavos) + ". Ele sai das contas e dos relatórios e fica guardado como cancelado, com o seu nome. Isto não pode ser desfeito.",
      sim: "Cancelar o lançamento",
      perigo: true,
    });
    if (!resposta.ok) return;
    const r = await M.api("POST", "/api/financeiro/lancamentos/" + l.id + "/cancelar");
    if (!r.ok) { M.avisar(r.erro); return; }
    M.avisar("Lançamento cancelado.");
    recarregar();
  }

  // ------------------------------------------------------------------ fluxo de caixa
  const corpoFluxo = raiz.querySelector("#tabela-fluxo tbody");

  function celula(centavos, sinal) {
    const zero = centavos === 0;
    const classe = "num" + (zero ? " zero" : (sinal ? (centavos < 0 ? " negativo" : " positivo") : ""));
    return M.el("td", { class: classe, text: M.reais(centavos) });
  }

  async function carregarFluxo() {
    const d = await pedir("/api/financeiro/fluxo", corpoFluxo, 8, null, M.novaCarga("fluxo"));
    if (!d || d === VELHA) return;
    const sem = d.motivo ? "Sem dados: " + d.motivo + "." : "";
    const vencidos = [];
    if (d.vencidos_a_pagar_centavos) vencidos.push(dinheiro(d.vencidos_a_pagar_centavos) + " a pagar");
    if (d.vencidos_a_receber_centavos) vencidos.push(dinheiro(d.vencidos_a_receber_centavos) + " a receber");
    preencher("[data-fk]", "fk", {
      entradas: dinheiro(d.entradas_centavos),
      entradas_m: sem || "vendas " + dinheiro(d.vendas_centavos) + " + outros recebimentos " + dinheiro(d.recebimentos_centavos),
      saidas: dinheiro(d.pagamentos_centavos),
      saidas_m: sem || "despesas pagas no período",
      saldo: dinheiro(d.saldo_centavos),
      saldo_m: sem || "o que entrou menos o que saiu",
      aberto: "a pagar " + dinheiro(d.a_pagar_centavos) + " · a receber " + dinheiro(d.a_receber_centavos),
      aberto_m: vencidos.length ? "Vencido, de qualquer data: " + vencidos.join(" e ") + "." : "nada vencido",
    });
    const saldo = raiz.querySelector('[data-fk="saldo"]');
    saldo.classList.toggle("negativo", d.saldo_centavos !== null && d.saldo_centavos < 0);
    saldo.classList.toggle("positivo", d.saldo_centavos !== null && d.saldo_centavos > 0);

    const nota = raiz.querySelector("[data-fluxo-nota]");
    const formas = Object.keys(d.recebido_por_forma).map(function (f) { return (FORMAS[f] || f) + " " + dinheiro(d.recebido_por_forma[f]); });
    nota.textContent = (formas.length ? "Recebido nas vendas, por forma: " + formas.join(" · ") + ". " : "")
      + "Venda entra no dia em que foi feita, inclusive no cartão (o prazo e a taxa da maquininha ainda não são considerados). Sangria e suprimento são da gaveta e ficam no Controle de Caixa.";

    if (!d.dias.length) { linhaUnica(corpoFluxo, 8, "Sem dados: sem vendas, pagamentos ou contas com vencimento de " + textoDoPeriodo(d.inicio, d.fim) + "."); return; }
    const linhas = d.dias.map(function (dia) {
      return M.el("tr", { class: dia.dia === hoje ? "selecionada" : "" },
        M.el("td", null, diaMes(dia.dia), M.el("span", { class: "sub em-linha", text: " " + diaDaSemana(dia.dia) + (dia.dia === hoje ? " · hoje" : "") })),
        celula(dia.vendas_centavos), celula(dia.recebimentos_centavos), celula(dia.pagamentos_centavos),
        celula(dia.saldo_centavos, true), celula(dia.acumulado_centavos, true),
        celula(dia.a_receber_centavos), celula(dia.a_pagar_centavos));
    });
    if (d.motivo === "") {
      linhas.push(M.el("tr", { class: "final" },
        M.el("td", { text: "Total" }),
        M.el("td", { class: "num", text: M.reais(d.vendas_centavos) }),
        M.el("td", { class: "num", text: M.reais(d.recebimentos_centavos) }),
        M.el("td", { class: "num", text: M.reais(d.pagamentos_centavos) }),
        M.el("td", { class: "num", text: M.reais(d.saldo_centavos) }),
        M.el("td", { class: "num", text: "" }),
        M.el("td", { class: "num", text: M.reais(d.a_receber_centavos) }),
        M.el("td", { class: "num", text: M.reais(d.a_pagar_centavos) })));
    }
    M.trocar.apply(null, [corpoFluxo].concat(linhas));
  }

  // ------------------------------------------------------------------ DRE
  const corpoDre = raiz.querySelector("#tabela-dre tbody");

  async function carregarDre() {
    const d = await pedir("/api/financeiro/dre", corpoDre, 3, null, M.novaCarga("dre"));
    if (!d || d === VELHA) return;
    raiz.querySelector("[data-dre-periodo]").textContent = textoDoPeriodo(d.inicio, d.fim);
    const avisos = raiz.querySelector("[data-dre-avisos]");
    M.trocar.apply(null, [avisos].concat(d.avisos.map(function (a) { return M.el("li", { text: a }); })));
    avisos.hidden = !d.avisos.length;

    const porChave = {};
    M.trocar.apply(null, [corpoDre].concat(d.linhas.map(function (l) {
      if (l.chave) porChave[l.chave] = l;
      const parcial = l.motivo.indexOf("parcial") === 0;
      const semValor = l.valor_centavos === null;
      const classe = l.chave === "resultado" ? "final" : (l.nivel === "total" ? "forte" : (l.nivel === "detalhe" ? "detalhe" : "principal"));
      return M.el("tr", { class: classe },
        M.el("td", null, l.rotulo,
          parcial ? M.el("span", { class: "tag alerta parcial", text: "parcial", title: l.motivo }) : null,
          semValor && l.nivel !== "detalhe" && d.tem_dados ? M.el("span", { class: "sub", text: "Sem dados: " + l.motivo + "." }) : null),
        M.el("td", { class: "num" + (l.valor_centavos !== null && l.valor_centavos < 0 && l.nivel === "total" ? " negativo" : ""), text: M.reais(l.valor_centavos), title: semValor ? l.motivo : "" }),
        M.el("td", { class: "num", text: l.percentual || "" }));
    })));
    if (!d.tem_dados) corpoDre.appendChild(M.el("tr", null, M.el("td", { class: "sem-linhas", colSpan: 3, text: "Sem dados: " + d.motivo + " (" + textoDoPeriodo(d.inicio, d.fim) + ")." })));

    function valor(chave) { return porChave[chave] ? dinheiro(porChave[chave].valor_centavos) : "—"; }
    function nota(chave, texto) {
      const l = porChave[chave];
      if (!l) return "—";
      if (l.valor_centavos === null) return "Sem dados: " + l.motivo + ".";
      return (l.percentual ? l.percentual + " da receita líquida" : texto) + (l.motivo ? " (parcial)" : "");
    }
    const motivos = {};
    ["lucro_bruto", "resultado"].forEach(function (chave) { if (porChave[chave] && porChave[chave].motivo) motivos[chave + "_m"] = porChave[chave].motivo; });
    preencher("[data-dk]", "dk", {
      receita_liquida: valor("receita_liquida"),
      receita_liquida_m: porChave.receita_liquida && porChave.receita_liquida.valor_centavos === null ? "Sem dados: " + d.motivo + "." : "vendas menos descontos e deduções",
      lucro_bruto: valor("lucro_bruto"),
      lucro_bruto_m: nota("lucro_bruto", "receita líquida menos o CMV"),
      resultado: valor("resultado"),
      resultado_m: nota("resultado", "o que sobrou no período"),
      vendas: d.tem_dados ? String(d.vendas_quantidade) : "—",
      vendas_m: d.tem_dados ? "vendas finalizadas no período" : "Sem dados: " + d.motivo + ".",
    }, motivos);
    const resultado = raiz.querySelector('[data-dk="resultado"]');
    const centavos = porChave.resultado ? porChave.resultado.valor_centavos : null;
    resultado.classList.toggle("negativo", centavos !== null && centavos < 0);
    resultado.classList.toggle("positivo", centavos !== null && centavos > 0);
  }

  // ------------------------------------------------------------------ rentabilidade
  const corpoRent = raiz.querySelector("#tabela-rentabilidade tbody");

  async function carregarRentabilidade() {
    const d = await pedir("/api/financeiro/rentabilidade", corpoRent, 7, null, M.novaCarga("rentabilidade"));
    if (!d || d === VELHA) return;
    raiz.querySelector("[data-rent-periodo]").textContent = textoDoPeriodo(d.inicio, d.fim);
    const nota = raiz.querySelector("[data-rent-nota]");
    nota.textContent = d.linhas.length
      ? "Total vendido no período: " + dinheiro(d.receita_centavos) + "." + (d.motivo ? " Produto vendido sem custo gravado aparece com “—”: cadastre o custo em Produtos ou dê entrada pela nota (vale para as vendas feitas depois)." : "")
      : "";
    nota.hidden = !nota.textContent;
    if (!d.linhas.length) { linhaUnica(corpoRent, 7, "Sem dados: " + d.motivo + " (" + textoDoPeriodo(d.inicio, d.fim) + ")."); return; }
    const linhas = d.linhas.map(function (l) {
      const sem = l.custo_centavos === null;
      return M.el("tr", null,
        M.el("td", { text: l.codigo }),
        M.el("td", { text: l.descricao }),
        M.el("td", { class: "num", text: M.qtd(l.quantidade) + " " + l.unidade }),
        M.el("td", { class: "num", text: M.reais(l.receita_centavos) }),
        M.el("td", { class: "num", text: M.reais(l.custo_centavos), title: sem ? l.motivo : "" }),
        M.el("td", { class: "num" + (l.margem_centavos !== null && l.margem_centavos < 0 ? " negativo" : ""), text: M.reais(l.margem_centavos), title: sem ? l.motivo : "" }),
        M.el("td", { class: "num", text: l.margem_percentual || "—", title: sem ? l.motivo : "" }));
    });
    // Com produto sem custo, a margem é só de quem tem custo: os totais vêm separados.
    if (d.produtos_sem_custo) {
      linhas.push(M.el("tr", { class: "forte" },
        M.el("td", { colSpan: 3, text: "Sem custo gravado na venda (" + (d.produtos_sem_custo === 1 ? "1 produto" : d.produtos_sem_custo + " produtos") + "): fora da margem" }),
        M.el("td", { class: "num", text: M.reais(d.receita_sem_custo_centavos) }),
        M.el("td", { class: "num", text: "—" }), M.el("td", { class: "num", text: "—" }), M.el("td", { class: "num", text: "—" })));
    }
    linhas.push(M.el("tr", { class: "final" },
      M.el("td", { colSpan: 3, text: d.produtos_sem_custo ? "Total dos produtos com custo" : "Total" }),
      M.el("td", { class: "num", text: M.reais(d.produtos_sem_custo ? d.receita_com_custo_centavos : d.receita_centavos), title: d.receita_com_custo_centavos === null ? d.motivo : "" }),
      M.el("td", { class: "num", text: M.reais(d.custo_centavos), title: d.custo_centavos === null ? d.motivo : "" }),
      M.el("td", { class: "num", text: M.reais(d.margem_centavos), title: d.margem_centavos === null ? d.motivo : "" }),
      M.el("td", { class: "num", text: d.margem_percentual || "—" })));
    M.trocar.apply(null, [corpoRent].concat(linhas));
  }

  // ------------------------------------------------------------------ categorias
  const corpoCategorias = raiz.querySelector("#tabela-categorias tbody");
  const verInativas = document.getElementById("cat-inativas");

  function desenharCategorias() {
    const visiveis = categorias.filter(function (c) { return c.ativo || verInativas.checked; });
    raiz.querySelector("[data-cat-contagem]").textContent = visiveis.length + (visiveis.length === 1 ? " categoria" : " categorias");
    if (!visiveis.length) { linhaUnica(corpoCategorias, 4, "Nenhuma categoria. Preencha a ficha ao lado e salve."); return; }
    M.trocar.apply(null, [corpoCategorias].concat(visiveis.map(function (c) {
      return M.el("tr", { class: (categoriaEmEdicao === c.id ? "selecionada" : "") + (c.ativo ? "" : " inativa") },
        M.el("td", { text: c.nome }),
        M.el("td", { text: c.grupo_rotulo }),
        M.el("td", null, M.el("span", { class: "tag " + (c.ativo ? "ativo" : "inativo"), text: c.ativo ? "Ativa" : "Inativa" })),
        M.el("td", null, botao("Alterar", "Alterar a categoria " + c.nome, function () { abrirCategoria(c); })));
    })));
  }

  function dicaDoGrupo() {
    formCategoria.querySelector("[data-cat-dica]").textContent = DICAS_DOS_GRUPOS[formCategoria.grupo.value] || "";
  }

  function novaCategoria() {
    categoriaEmEdicao = null;
    formCategoria.reset();
    M.mensagem(formCategoria, "");
    document.getElementById("t-cat-ficha").textContent = "Nova categoria";
    formCategoria.querySelector("[data-so-na-edicao]").hidden = true;
    formCategoria.grupo.value = "despesa_operacional";
    dicaDoGrupo();
    desenharCategorias();
  }

  function abrirCategoria(c) {
    categoriaEmEdicao = c.id;
    M.mensagem(formCategoria, "");
    document.getElementById("t-cat-ficha").textContent = "Alterar categoria";
    formCategoria.nome.value = c.nome;
    formCategoria.grupo.value = c.grupo;
    formCategoria.ativo.checked = c.ativo;
    formCategoria.querySelector("[data-so-na-edicao]").hidden = false;
    dicaDoGrupo();
    desenharCategorias();
    formCategoria.nome.focus();
  }

  async function carregarCategorias() {
    const r = await M.api("GET", "/api/financeiro/categorias?todas=true");
    if (!r.ok) { linhaUnica(corpoCategorias, 4, "Não foi possível carregar as categorias: " + r.erro); return; }
    categorias = r.dados;
    desenharCategorias();
  }

  formCategoria.addEventListener("submit", async function (evento) {
    evento.preventDefault();
    const nome = formCategoria.nome.value.trim();
    if (!nome) { M.mensagem(formCategoria, "Digite o nome da categoria."); formCategoria.nome.focus(); return; }
    const dados = { nome: nome, grupo: formCategoria.grupo.value, ativo: categoriaEmEdicao === null ? true : formCategoria.ativo.checked };
    const r = categoriaEmEdicao === null
      ? await M.api("POST", "/api/financeiro/categorias", dados)
      : await M.api("PUT", "/api/financeiro/categorias/" + categoriaEmEdicao, dados);
    if (!r.ok) { M.mensagem(formCategoria, r.erro); return; }
    M.avisar("Categoria " + r.dados.nome + " salva.");
    await carregarCategorias();
    novaCategoria();
  });
  formCategoria.grupo.addEventListener("change", dicaDoGrupo);
  formCategoria.querySelector("[data-limpar]").addEventListener("click", novaCategoria);
  verInativas.addEventListener("change", desenharCategorias);

  // ------------------------------------------------------------------ abas, período e início
  const CARGAS = { lancamentos: carregarLancamentos, fluxo: carregarFluxo, dre: carregarDre, rentabilidade: carregarRentabilidade, categorias: carregarCategorias };

  function recarregar() { return CARGAS[aba](); }

  function mostrarAba(nome, semMexerNoEndereco) {
    aba = ABAS.indexOf(nome) >= 0 ? nome : "lancamentos";
    raiz.querySelectorAll("[data-aba]").forEach(function (b) {
      const ativa = b.dataset.aba === aba;
      b.classList.toggle("ativa", ativa);
      b.setAttribute("aria-selected", ativa ? "true" : "false");
    });
    raiz.querySelectorAll("[data-painel]").forEach(function (p) { p.hidden = p.dataset.painel !== aba; });
    raiz.querySelector("[data-periodo]").hidden = aba === "categorias"; // categoria não tem período
    if (!semMexerNoEndereco) window.history.replaceState(null, "", "#" + aba);
    recarregar();
  }

  raiz.querySelectorAll("[data-aba]").forEach(function (b) {
    b.addEventListener("click", function () { mostrarAba(b.dataset.aba); });
  });
  window.addEventListener("hashchange", function () { mostrarAba(window.location.hash.slice(1), true); });
  periodo.addEventListener("change", function () {
    const escolher = periodo.value === "datas";
    raiz.querySelector("[data-datas]").hidden = !escolher;
    if (escolher && !pdInicio.value) { // começa do dia 1 do mês até hoje
      pdInicio.value = M.dataBR(hoje.slice(0, 8) + "01");
      pdFim.value = M.dataBR(hoje);
    }
    if (escolher) { pdInicio.focus(); pdInicio.select(); }
    recarregar();
  });
  pdInicio.addEventListener("change", recarregar);
  pdFim.addEventListener("change", recarregar);
  lcTipo.addEventListener("change", carregarLancamentos);
  lcSituacao.addEventListener("change", carregarLancamentos);
  raiz.querySelector("[data-lc-ver-abertas]").addEventListener("click", function () {
    lcSituacao.value = "todas_em_aberto";
    carregarLancamentos();
  });
  document.getElementById("btn-novo").addEventListener("click", function () { abrirLancamento(null); });
  // F3 abre um lançamento novo em qualquer aba desta tela.
  document.addEventListener("keydown", function (evento) {
    if (evento.key !== "F3" || evento.ctrlKey || evento.altKey || evento.metaKey || document.querySelector("dialog[open]")) return;
    evento.preventDefault();
    abrirLancamento(null);
  });

  (async function iniciar() {
    const status = await M.api("GET", "/api/status");
    hoje = status.ok && status.dados.agora ? status.dados.agora.slice(0, 10) : "";
    const g = await M.api("GET", "/api/financeiro/grupos");
    grupos = g.ok ? g.dados : [];
    grupos.forEach(function (grupo) { formCategoria.grupo.appendChild(M.el("option", { value: grupo.grupo, text: grupo.rotulo })); });
    const c = await M.api("GET", "/api/financeiro/categorias?todas=true");
    categorias = c.ok ? c.dados : [];
    novaCategoria();
    if (!hoje) { linhaUnica(corpoLancamentos, 6, "Sem resposta do sistema: não foi possível saber a data de hoje."); return; }
    mostrarAba(window.location.hash.slice(1), true);
  })();
})();

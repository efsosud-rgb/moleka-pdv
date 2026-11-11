/* Moleka PDV — tela Controle de Caixa: abrir com fundo de troco, sangria, suprimento, vendas
   da sessão, fechamento com conferência por forma de pagamento e (só o gerente) os fechamentos
   anteriores. Todos os números vêm de /api/caixa e /api/vendas; nada é calculado "de cabeça"
   aqui, a não ser a diferença (contado - esperado) enquanto a pessoa digita o fechamento. */

(function () {
  "use strict";

  const M = window.Moleka;
  const raiz = document.getElementById("controle");
  if (!raiz) return;

  const gerente = raiz.dataset.gerente === "sim";
  const corpoFormas = raiz.querySelector("#tabela-formas tbody");
  const corpoMovimentos = raiz.querySelector("#tabela-movimentos tbody");
  const corpoVendas = raiz.querySelector("#tabela-vendas tbody");
  const corpoHistorico = raiz.querySelector("#tabela-historico tbody"); // só existe para o gerente
  const resumo = raiz.querySelector("[data-resumo-cx]");
  const formAbrir = document.getElementById("form-abrir");
  const formMovimento = document.getElementById("form-movimento");
  const dlgFechar = document.getElementById("dlg-fechar");
  const formFechar = document.getElementById("form-fechar");
  const corpoFechar = formFechar.querySelector("tbody");
  const colunasDeVendas = gerente ? 7 : 6;

  let situacao = null; // { aberto, sessao }, de /api/caixa
  let vendas = []; // vendas encerradas da sessão mostrada
  let historico = []; // últimos fechamentos (só o gerente)
  let fechada = null; // o fechamento feito agora, nesta tela (para mostrar o resultado)
  let aba = "formas";
  let primeiraCarga = true;
  let avisouDiferenca = false;

  function linhaUnica(corpo, colunas, texto) {
    M.trocar(corpo, M.el("tr", null, M.el("td", { class: "sem-linhas", colSpan: colunas, text: texto })));
  }

  function comSinal(centavos) {
    return (centavos > 0 ? "+" : "") + M.reais(centavos);
  }

  function celulaDeDiferenca(centavos) {
    if (centavos === null || centavos === undefined) return M.el("td", { class: "num", text: "—" });
    return M.el("td", { class: "num " + (centavos === 0 ? "positivo" : "negativo"), text: comSinal(centavos) });
  }

  // ------------------------------------------------------------------ abas
  function mostrarAba(nome) {
    aba = nome;
    raiz.querySelectorAll("[data-aba]").forEach(function (botao) {
      const ativa = botao.dataset.aba === nome;
      botao.classList.toggle("ativa", ativa);
      botao.setAttribute("aria-selected", ativa ? "true" : "false");
    });
    raiz.querySelectorAll("[data-painel]").forEach(function (painel) { painel.hidden = painel.dataset.painel !== nome; });
    desenharResumo();
  }

  // ------------------------------------------------------------------ desenho
  function sessaoMostrada() {
    if (situacao && situacao.aberto) return situacao.sessao;
    return fechada;
  }

  function desenharNumeros(s) {
    const valores = {
      aberto_em: M.dataHora(s.aberto_em),
      aberto_por: "por " + s.operador + " · " + s.caixa,
      vendas_quantidade: String(s.vendas_quantidade),
      vendas_total: s.vendas_quantidade ? M.formatarCentavos(s.vendas_total_centavos) : "—",
      vendas_motivo: s.vendas_quantidade ? "somando todas as formas de pagamento" : "Sem dados: nenhuma venda finalizada neste caixa.",
      dinheiro_esperado: M.formatarCentavos(s.dinheiro_esperado_centavos),
    };
    raiz.querySelectorAll("[data-cx]").forEach(function (el) { el.textContent = valores[el.dataset.cx] || "—"; });
  }

  function desenharFormas(s) {
    const fechado = !!(s && s.fechado_em);
    raiz.querySelectorAll("[data-col-fechado]").forEach(function (th) { th.hidden = !fechado; });
    if (!s) { linhaUnica(corpoFormas, 5, "O caixa está fechado. Abra o caixa ao lado para começar a vender."); return; }
    M.trocar.apply(null, [corpoFormas].concat(s.formas.map(function (f) {
      return M.el("tr", null,
        M.el("td", { text: f.rotulo }),
        M.el("td", { class: "num", text: M.reais(f.recebido_centavos) }),
        M.el("td", { class: "num", text: M.reais(f.esperado_centavos) }),
        fechado ? M.el("td", { class: "num", text: M.reais(f.contado_centavos) }) : null,
        fechado ? celulaDeDiferenca(f.diferenca_centavos) : null);
    })));
  }

  function desenharMovimentos(s) {
    if (!s) { linhaUnica(corpoMovimentos, 4, "O caixa está fechado."); return; }
    if (!s.movimentos.length) { linhaUnica(corpoMovimentos, 4, "Nenhuma sangria ou suprimento neste caixa."); return; }
    M.trocar.apply(null, [corpoMovimentos].concat(s.movimentos.map(function (m) {
      const sangria = m.tipo === "sangria";
      return M.el("tr", null,
        M.el("td", { text: M.hora(m.em) }),
        M.el("td", null, M.el("span", { class: "tag " + (sangria ? "inativo" : "ativo"), text: sangria ? "Sangria" : "Suprimento" })),
        M.el("td", { class: "num", text: (sangria ? "-" : "+") + M.reais(m.valor_centavos) }),
        M.el("td", { text: m.motivo || "—" }));
    })));
  }

  function textoDosPagamentos(v) {
    if (!v.pagamentos.length) return "—";
    return v.pagamentos.map(function (p) { return p.rotulo + " " + M.reais(p.valor_centavos); }).join(" + ");
  }

  function desenharVendas(s) {
    if (!s) { linhaUnica(corpoVendas, colunasDeVendas, "O caixa está fechado."); return; }
    if (!vendas.length) { linhaUnica(corpoVendas, colunasDeVendas, "Nenhuma venda encerrada neste caixa."); return; }
    const podeCancelar = gerente && !s.fechado_em;
    M.trocar.apply(null, [corpoVendas].concat(vendas.map(function (v) {
      const finalizada = v.status === "finalizada";
      const situacaoDaVenda = M.el("span", {
        class: "tag " + (finalizada ? "ativo" : "inativo"),
        text: finalizada ? "Finalizada" : "Cancelada",
        title: finalizada ? "" : "Motivo: " + (v.motivo_cancelamento || "não informado"),
      });
      const pagamentos = textoDosPagamentos(v);
      return M.el("tr", { class: finalizada ? "" : "inativa" },
        M.el("td", { text: String(v.numero) }),
        M.el("td", { text: M.hora(v.finalizada_em || v.cancelada_em) }),
        M.el("td", { text: v.cliente ? v.cliente.nome : "Consumidor final" }),
        M.el("td", { text: pagamentos, title: pagamentos === "—" ? "sem pagamento lançado" : "" }),
        M.el("td", { class: "num", text: M.reais(v.total_centavos) }),
        M.el("td", null, situacaoDaVenda),
        gerente ? M.el("td", null, finalizada && podeCancelar
          ? M.el("button", { type: "button", class: "btn3d mini", text: "Cancelar", "aria-label": "Cancelar a venda nº " + v.numero, onclick: function () { cancelarVenda(v); } })
          : null) : null);
    })));
  }

  function desenharHistorico() {
    if (!corpoHistorico) return;
    if (!historico.length) { linhaUnica(corpoHistorico, 7, "Nenhum caixa fechado até agora."); return; }
    M.trocar.apply(null, [corpoHistorico].concat(historico.map(function (s) {
      const dinheiro = s.formas.find(function (f) { return f.forma === "dinheiro"; });
      const outras = s.formas.filter(function (f) { return f.forma !== "dinheiro"; });
      const difOutras = outras.every(function (f) { return f.diferenca_centavos === null; })
        ? null
        : outras.reduce(function (soma, f) { return soma + (f.diferenca_centavos || 0); }, 0);
      return M.el("tr", null,
        M.el("td", { text: M.dataHora(s.aberto_em) }),
        M.el("td", { text: M.dataHora(s.fechado_em) }),
        M.el("td", { text: s.operador + (s.fechado_por && s.fechado_por !== s.operador ? " / " + s.fechado_por : ""), title: s.observacao ? "Observação: " + s.observacao : "" }),
        M.el("td", { class: "num", text: String(s.vendas_quantidade) }),
        M.el("td", { class: "num", text: s.vendas_quantidade ? M.reais(s.vendas_total_centavos) : "—", title: s.vendas_quantidade ? "" : "sem vendas finalizadas" }),
        celulaDeDiferenca(dinheiro ? dinheiro.diferenca_centavos : null),
        celulaDeDiferenca(difOutras));
    })));
  }

  function desenharResumo() {
    const s = sessaoMostrada();
    if (!s || aba === "historico") { resumo.hidden = true; return; }
    const partes = [
      M.el("span", null, "Fundo de troco: ", M.el("b", { text: M.formatarCentavos(s.fundo_troco_centavos) })),
      M.el("span", null, " · Suprimentos: ", M.el("b", { text: M.formatarCentavos(s.suprimentos_centavos) })),
      M.el("span", null, " · Sangrias: ", M.el("b", { text: M.formatarCentavos(s.sangrias_centavos) })),
    ];
    if (s.fechado_em) {
      partes.unshift(M.el("span", null, M.el("b", { text: "Caixa fechado em " + M.dataHora(s.fechado_em) + (s.fechado_por ? " por " + s.fechado_por : "") + ". " })));
      if (s.observacao) partes.push(M.el("span", { text: " · Observação: " + s.observacao }));
    }
    M.trocar.apply(null, [resumo].concat(partes));
    resumo.hidden = false;
  }

  function desenhar() {
    const aberto = !!(situacao && situacao.aberto);
    const estado = situacao ? (aberto ? "aberto" : "fechado") : "carregando";
    raiz.querySelectorAll("[data-estado]").forEach(function (el) { el.hidden = el.dataset.estado !== estado; });
    raiz.querySelector("[data-so-aberto]").hidden = !aberto;
    const s = sessaoMostrada();
    if (aberto) desenharNumeros(s);
    desenharFormas(s);
    desenharMovimentos(s);
    desenharVendas(s);
    desenharHistorico();
    mostrarAba(aba);
  }

  // ------------------------------------------------------------------ carga
  async function carregar() {
    const r = await M.api("GET", "/api/caixa");
    if (!r.ok) {
      linhaUnica(corpoFormas, 5, "Não foi possível carregar a situação do caixa: " + r.erro);
      return;
    }
    situacao = r.dados;
    const s = sessaoMostrada();
    vendas = [];
    if (s) {
      const v = await M.api("GET", "/api/vendas?sessao_id=" + s.id);
      if (v.ok) vendas = v.dados;
      else M.avisar("Não foi possível carregar as vendas deste caixa: " + v.erro);
    }
    if (gerente) {
      const h = await M.api("GET", "/api/caixa/historico");
      historico = h.ok ? h.dados : [];
    }
    if (primeiraCarga) {
      primeiraCarga = false;
      if (!situacao.aberto && gerente && historico.length) aba = "historico";
    }
    desenhar();
    if (!situacao.aberto) formAbrir.fundo.focus();
  }

  // ------------------------------------------------------------------ abrir
  formAbrir.addEventListener("submit", async function (evento) {
    evento.preventDefault();
    const texto = formAbrir.fundo.value.trim();
    if (!texto) { M.mensagem(formAbrir, "Digite o fundo de troco. Se a gaveta está vazia, digite 0."); formAbrir.fundo.focus(); return; }
    const centavos = M.lerReais(texto);
    if (centavos === null || centavos < 0) { M.mensagem(formAbrir, "Valor inválido. Digite assim: 100,00"); formAbrir.fundo.focus(); return; }
    const r = await M.api("POST", "/api/caixa/abrir", { fundo_troco_centavos: centavos });
    if (!r.ok) {
      M.mensagem(formAbrir, r.erro);
      if (r.status === 409) carregar(); // já estava aberto (outra pessoa abriu)
      return;
    }
    fechada = null;
    aba = "formas";
    formAbrir.reset();
    M.mensagem(formAbrir, "");
    M.avisar("Caixa aberto com fundo de troco de " + M.formatarCentavos(centavos) + ".");
    await carregar();
    M.atualizarStatus();
  });

  // ------------------------------------------------------------------ sangria e suprimento
  formMovimento.addEventListener("submit", async function (evento) {
    evento.preventDefault();
    const tipo = formMovimento.tipo.value;
    const nome = tipo === "sangria" ? "sangria" : "suprimento";
    const centavos = M.lerReais(formMovimento.valor.value);
    const motivo = formMovimento.motivo.value.trim();
    if (centavos === null || centavos <= 0) { M.mensagem(formMovimento, "Digite o valor. Assim: 50,00"); formMovimento.valor.focus(); return; }
    if (!motivo) { M.mensagem(formMovimento, "Escreva o motivo (por exemplo: pagamento do gelo)."); formMovimento.motivo.focus(); return; }
    M.mensagem(formMovimento, "");
    const resposta = await M.confirmar({
      titulo: "Lançar " + nome + " de " + M.formatarCentavos(centavos) + "?",
      texto: (tipo === "sangria" ? "O dinheiro sai da gaveta. " : "O dinheiro entra na gaveta. ") + "Motivo: " + motivo + ". O lançamento fica registrado com o seu nome e não pode ser apagado.",
      sim: "Lançar " + nome,
    });
    if (!resposta.ok) return;
    const r = await M.api("POST", "/api/caixa/movimentos", { tipo: tipo, valor_centavos: centavos, motivo: motivo });
    if (!r.ok) {
      M.mensagem(formMovimento, r.erro);
      if (r.status === 409) carregar();
      return;
    }
    situacao = r.dados;
    formMovimento.reset();
    aba = "movimentos";
    desenhar();
    const valor = M.formatarCentavos(centavos);
    M.avisar(tipo === "sangria" ? "Sangria de " + valor + " lançada." : "Suprimento de " + valor + " lançado.");
  });

  // ------------------------------------------------------------------ cancelar venda encerrada (só o gerente)
  async function cancelarVenda(v) {
    const resposta = await M.confirmar({
      titulo: "Cancelar a venda nº " + v.numero + "?",
      texto: "Total de " + M.formatarCentavos(v.total_centavos) + ". A venda sai dos totais do caixa e os produtos voltam para o estoque. Isto não pode ser desfeito.",
      sim: "Cancelar a venda",
      perigo: true,
      motivo: "obrigatorio",
    });
    if (!resposta.ok) return;
    const r = await M.api("POST", "/api/vendas/" + v.id + "/cancelar", { motivo: resposta.motivo });
    if (!r.ok) { M.avisar(r.erro); return; }
    M.avisar("Venda nº " + v.numero + " cancelada.");
    await carregar();
  }

  // ------------------------------------------------------------------ fechar
  function linhaDeFechamento(f) {
    const campo = M.el("input", {
      class: "campo num", type: "text", inputMode: "decimal", placeholder: "0,00",
      value: f.esperado_centavos === 0 ? "0,00" : "", "aria-label": "Contado em " + f.rotulo,
    });
    campo.dataset.forma = f.forma;
    campo.dataset.rotulo = f.rotulo;
    campo.dataset.esperado = String(f.esperado_centavos);
    const diferenca = M.el("td", { class: "num", text: "—" });
    function atualizar() {
      avisouDiferenca = false;
      const contado = campo.value.trim() ? M.lerReais(campo.value) : null;
      if (contado === null) { diferenca.textContent = "—"; diferenca.className = "num"; return; }
      const d = contado - f.esperado_centavos;
      diferenca.textContent = comSinal(d);
      diferenca.className = "num " + (d === 0 ? "positivo" : "negativo");
    }
    campo.addEventListener("input", atualizar);
    atualizar();
    return M.el("tr", null,
      M.el("td", { text: f.rotulo }),
      M.el("td", { class: "num", text: M.reais(f.esperado_centavos) }),
      M.el("td", null, campo),
      diferenca);
  }

  document.getElementById("btn-fechar").addEventListener("click", async function () {
    await carregar(); // números frescos antes de conferir
    if (!situacao || !situacao.aberto) return;
    avisouDiferenca = false;
    M.mensagem(formFechar, "");
    formFechar.observacao.value = "";
    M.trocar.apply(null, [corpoFechar].concat(situacao.sessao.formas.map(linhaDeFechamento)));
    dlgFechar.showModal();
    const primeiro = corpoFechar.querySelector("input");
    if (primeiro) { primeiro.focus(); primeiro.select(); }
  });

  formFechar.addEventListener("submit", async function (evento) {
    evento.preventDefault();
    const contado = {};
    const diferencas = [];
    const campos = corpoFechar.querySelectorAll("input");
    for (let i = 0; i < campos.length; i++) {
      const campo = campos[i];
      const texto = campo.value.trim();
      if (!texto) { M.mensagem(formFechar, "Digite o valor contado em " + campo.dataset.rotulo + " (se não entrou nada, digite 0)."); campo.focus(); return; }
      const centavos = M.lerReais(texto);
      if (centavos === null || centavos < 0) { M.mensagem(formFechar, "Valor inválido em " + campo.dataset.rotulo + ". Digite assim: 150,00"); campo.focus(); return; }
      contado[campo.dataset.forma] = centavos;
      const d = centavos - Number(campo.dataset.esperado);
      if (d !== 0) diferencas.push(campo.dataset.rotulo + " " + comSinal(d));
    }
    if (diferencas.length && !avisouDiferenca) {
      avisouDiferenca = true;
      M.mensagem(formFechar, "Há diferença: " + diferencas.join("; ") + ". Confira a contagem. Para fechar assim mesmo, clique de novo em “Fechar o caixa”.");
      return;
    }
    const r = await M.api("POST", "/api/caixa/fechar", { contado: contado, observacao: formFechar.observacao.value.trim() || null });
    if (!r.ok) { M.mensagem(formFechar, r.erro); return; }
    dlgFechar.close();
    fechada = r.dados;
    aba = "formas";
    M.avisar("Caixa fechado.");
    await carregar();
    M.atualizarStatus();
  });

  raiz.querySelectorAll("[data-aba]").forEach(function (botao) {
    botao.addEventListener("click", function () { mostrarAba(botao.dataset.aba); });
  });

  carregar();
})();

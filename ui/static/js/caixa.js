/* Moleka PDV — tela do Caixa (venda).

   A venda mora no servidor: cada pedido (/api/venda/...) devolve a venda inteira, com as contas
   refeitas, e a tela só desenha o que chegou. Nenhum valor é calculado aqui.

   O que a tela faz:
   - produto por leitor, código ou nome (lista de sugestões); "3*codigo" lança três de uma vez;
   - quantidade editável em cada item (o preço por quantidade entra sozinho);
   - cliente escolhido no cadastro, trocado ou retirado a qualquer momento;
   - pagamento em uma ou mais formas, com o percentual de cada forma; a forma de um pagamento
     já lançado pode ser trocada; só o dinheiro dá troco;
   - ao finalizar, a escolha "com NFC-e" ou "sem NFC-e";
   - saldo das vendas do dia no topo. */

(function () {
  "use strict";

  const M = window.Moleka;
  const pdv = document.getElementById("pdv");
  if (!pdv) return;

  function porId(id) { return document.getElementById(id); }

  const formItem = porId("form-item");
  const campoProd = porId("prod");
  const campoQtd = porId("qtd");
  const campoCli = porId("cli");
  const corpoItens = document.querySelector("#tabela-itens tbody");
  const lancados = porId("lancados");
  const btnFinalizar = porId("btn-finalizar");
  const btnDesconto = porId("btn-desconto"); // só existe para o gerente
  const dlgFinalizar = porId("dlg-finalizar");
  const dlgFim = porId("dlg-fim");
  const dlgSaldo = porId("dlg-saldo");

  const COMO = { dinheiro: "em dinheiro", pix: "no Pix", debito: "no débito", credito: "no crédito" };

  let estado = null; // último retrato do servidor: { caixa_aberto, venda, nfce_disponivel, nfce_motivo }
  let tabelas = []; // tabelas de preço, para mostrar o preço nas sugestões de produto
  let formasDaLoja = []; // percentuais das formas, para mostrar nos botões antes de haver venda
  let ultima = null; // última venda encerrada nesta tela (só para avisar o que aconteceu)
  let fila = Promise.resolve(); // os pedidos vão um de cada vez, na ordem em que foram feitos

  function venda() {
    const v = estado ? estado.venda : null;
    return v && v.status === "aberta" ? v : null;
  }

  // ------------------------------------------------------------------ pedidos ao servidor
  function aplicar(novo) {
    estado = novo;
    if (novo.venda && novo.venda.status !== "aberta") ultima = novo.venda;
    desenhar();
    if (novo.aviso) M.avisar(novo.aviso);
  }

  async function recarregar() {
    const r = await M.api("GET", "/api/venda");
    if (r.ok) aplicar(r.dados);
    else M.avisar("Não foi possível carregar a venda: " + r.erro);
  }

  /* Manda um pedido que muda a venda e redesenha com a resposta. Os pedidos entram em fila: dois
     bipes seguidos do leitor não se atropelam.
     opcoes.calado: não mostra o erro (quem chamou mostra do seu jeito);
     opcoes.mexeNaVenda: mudou item ou desconto — o servidor desfaz os pagamentos, e a tela avisa. */
  function pedir(metodo, caminho, corpo, opcoes) {
    const o = opcoes || {};
    const tarefa = fila.then(async function () {
      const antes = venda();
      const tinhaPagamentos = !!(antes && antes.pagamentos.length);
      const r = await M.api(metodo, caminho, corpo);
      if (r.ok) {
        aplicar(r.dados);
        const depois = venda();
        if (o.mexeNaVenda && tinhaPagamentos && depois && !depois.pagamentos.length && !r.dados.aviso) {
          M.avisar("A venda mudou: os pagamentos foram desfeitos. Lance o pagamento de novo.");
        }
      } else {
        if (!o.calado) M.avisar(r.erro);
        if (r.status === 409) await recarregar(); // o caixa fechou ou a venda mudou por outro caminho
      }
      return r;
    });
    fila = tarefa.catch(function () {});
    return tarefa;
  }

  // ------------------------------------------------------------------ lista de sugestões (produto e cliente)
  function criarSugestoes(campo, lista, desenharLinha, aoEscolher) {
    let itens = [];
    let marcada = -1;
    let moveu = false; // a pessoa andou na lista com as setas

    function fechar() {
      itens = [];
      marcada = -1;
      moveu = false;
      lista.hidden = true;
      M.trocar(lista);
      campo.setAttribute("aria-expanded", "false");
    }

    function marcar(i) {
      marcada = i;
      Array.prototype.forEach.call(lista.children, function (li, n) {
        li.classList.toggle("marcada", n === i);
        li.setAttribute("aria-selected", n === i ? "true" : "false");
      });
      if (i >= 0 && lista.children[i]) lista.children[i].scrollIntoView({ block: "nearest" });
    }

    function escolher(i) {
      const item = itens[i];
      if (!item) return false;
      fechar();
      aoEscolher(item);
      return true;
    }

    function mostrar(novos, textoSeVazio) {
      itens = novos;
      moveu = false;
      if (!novos.length) {
        if (!textoSeVazio) { fechar(); return; }
        M.trocar(lista, M.el("li", { class: "nada", text: textoSeVazio }));
        marcada = -1;
      } else {
        M.trocar.apply(null, [lista].concat(novos.map(function (item, i) {
          const li = M.el("li", { role: "option", onclick: function () { escolher(i); } });
          desenharLinha(li, item);
          return li;
        })));
        marcar(0);
      }
      lista.hidden = false;
      campo.setAttribute("aria-expanded", "true");
    }

    /* Setas para cima e para baixo andam na lista. Devolve true se a tecla foi usada aqui. */
    function tecla(evento) {
      if (lista.hidden || !itens.length) return false;
      if (evento.key !== "ArrowDown" && evento.key !== "ArrowUp") return false;
      evento.preventDefault();
      moveu = true;
      marcar((marcada + (evento.key === "ArrowDown" ? 1 : itens.length - 1)) % itens.length);
      return true;
    }

    lista.addEventListener("mousedown", function (evento) { evento.preventDefault(); }); // o campo não perde o foco
    campo.addEventListener("blur", function () { setTimeout(fechar, 150); });

    return {
      mostrar: mostrar,
      fechar: fechar,
      escolher: escolher,
      tecla: tecla,
      aberta: function () { return !lista.hidden && itens.length > 0; },
      marcada: function () { return marcada; },
      moveu: function () { return moveu; },
    };
  }

  // ------------------------------------------------------------------ produto
  function tabelaPadrao() {
    return tabelas.find(function (t) { return t.padrao; }) || null;
  }

  /* Preço unitário a partir de 1, na tabela da venda (ou na padrão, como o servidor faz). */
  function precoDeLista(produto) {
    const v = venda();
    const daVenda = v ? tabelas.find(function (t) { return t.nome === v.tabela; }) : null;
    function menor(tabela) {
      if (!tabela) return null;
      const faixas = produto.precos.filter(function (f) { return f.tabela_id === tabela.id; });
      faixas.sort(function (a, b) { return Number(a.qtd_min) - Number(b.qtd_min); });
      return faixas.length ? faixas[0].preco_centavos : null;
    }
    const preco = menor(daVenda || tabelaPadrao());
    return preco !== null ? preco : menor(tabelaPadrao());
  }

  const sugProd = criarSugestoes(campoProd, porId("sugestoes-prod"), function (li, p) {
    const preco = precoDeLista(p);
    li.appendChild(M.el("span", { class: "cod", text: p.codigo }));
    li.appendChild(M.el("span", { class: "nome", text: p.descricao }));
    li.appendChild(M.el("span", {
      class: "preco",
      text: preco === null ? "sem preço" : M.formatarCentavos(preco) + " / " + p.unidade.toLowerCase(),
      title: preco === null ? "produto sem preço cadastrado" : "preço a partir de 1; o preço por quantidade entra sozinho na venda",
    }));
  }, function (p) { adicionar({ produto_id: p.id }, p.descricao); });

  let relogioProd = 0;
  let pedidoProd = 0;
  let textoDaLista = ""; // para qual texto a lista de produtos na tela foi pesquisada

  async function buscarProdutos(texto, depoisDoEnter) {
    const numero = ++pedidoProd;
    const r = await M.api("GET", "/api/produtos?limite=8&busca=" + encodeURIComponent(texto));
    if (numero !== pedidoProd) return null; // já saiu uma pesquisa mais nova
    if (!r.ok) { sugProd.fechar(); return null; }
    if (!depoisDoEnter && campoProd.value.trim() !== texto) return null; // a pessoa continuou digitando
    textoDaLista = texto;
    sugProd.mostrar(r.dados, "Nenhum produto encontrado para “" + texto + "”.");
    return r.dados;
  }

  campoProd.addEventListener("input", function () {
    clearTimeout(relogioProd);
    const texto = campoProd.value.trim();
    // Só números (código ou leitor): não pesquisa enquanto digita; o Enter resolve.
    if (texto.length < 2 || /^[\d*.,\s]+$/.test(texto)) { sugProd.fechar(); return; }
    relogioProd = setTimeout(function () { buscarProdutos(texto, false); }, 220);
  });

  campoProd.addEventListener("keydown", function (evento) {
    if (sugProd.tecla(evento)) return;
    if (evento.key !== "Escape" || (!campoProd.value && !sugProd.aberta())) return; // vazio: o Esc volta ao início
    evento.preventDefault();
    evento.stopPropagation();
    clearTimeout(relogioProd);
    sugProd.fechar();
    campoProd.value = "";
  });

  campoQtd.addEventListener("keydown", function (evento) {
    if (evento.key !== "Escape") return;
    evento.preventDefault();
    evento.stopPropagation();
    campoQtd.value = "1";
    campoProd.focus();
  });

  async function adicionar(alvo, textoDigitado) {
    // A quantidade fica no campo Qtd até o item entrar: se for preciso escolher o produto na
    // lista, ela continua valendo.
    const quantidade = (campoQtd.value.trim() || "1").replace(",", ".");
    const digitado = campoProd.value;
    const porCodigo = alvo.codigo !== undefined;
    campoProd.select(); // o próximo bipe do leitor substitui o texto
    const corpo = Object.assign({ quantidade: quantidade }, alvo);
    const r = await pedir("POST", "/api/venda/itens", corpo, { calado: porCodigo, mexeNaVenda: true });
    if (r.ok) {
      campoQtd.value = "1";
      if (campoProd.value === digitado) campoProd.value = "";
      sugProd.fechar();
      campoProd.focus();
      return;
    }
    if (!porCodigo) return; // o erro já foi mostrado
    if (r.status !== 404) { M.avisar(r.erro); return; }
    // Não é código nem código de barras: procura pelo nome.
    if (sugProd.aberta() && textoDaLista === textoDigitado) { sugProd.escolher(sugProd.marcada()); return; }
    const achados = await buscarProdutos(textoDigitado, true);
    if (!achados) return;
    if (achados.length === 1) sugProd.escolher(0);
    else if (achados.length > 1) M.avisar("Escolha o produto na lista: setas ↑ ↓ e Enter.");
    else M.avisar("Produto não encontrado: “" + textoDigitado + "”.");
  }

  formItem.addEventListener("submit", function (evento) {
    evento.preventDefault();
    clearTimeout(relogioProd);
    let texto = campoProd.value.trim();
    if (!texto) { campoProd.focus(); return; }
    // "3*7891234567895": três unidades do produto bipado.
    const vezes = /^(\d+(?:[.,]\d+)?)\s*\*\s*(.+)$/.exec(texto);
    if (vezes) { campoQtd.value = vezes[1]; texto = vezes[2].trim(); }
    if (sugProd.aberta() && sugProd.moveu()) { sugProd.escolher(sugProd.marcada()); return; }
    adicionar({ codigo: texto }, texto);
  });

  // ------------------------------------------------------------------ itens
  function textoDosPagamentos(v) {
    return v.pagamentos.map(function (p) { return p.rotulo + " " + M.formatarCentavos(p.valor_centavos); }).join(" + ");
  }

  function textoDaUltima() {
    const u = ultima;
    if (u.status === "cancelada") return "Venda nº " + u.numero + " cancelada.";
    return "Última venda: nº " + u.numero + " · " + M.formatarCentavos(u.total_centavos) + " · " + textoDosPagamentos(u)
      + (u.troco_centavos ? " · troco " + M.formatarCentavos(u.troco_centavos) : "") + " · " + M.hora(u.finalizada_em);
  }

  function linhaDeItem(item, i) {
    const original = M.qtd(item.quantidade);
    const campo = M.el("input", {
      class: "campo num qtd-item", type: "text", inputMode: "decimal", maxLength: 9, value: original,
      title: "Digite a nova quantidade e aperte Enter", "aria-label": "Quantidade de " + item.descricao,
    });
    campo.dataset.item = String(item.id);
    campo.addEventListener("focus", function () { campo.select(); });
    campo.addEventListener("keydown", function (evento) {
      if (evento.key === "Enter") { evento.preventDefault(); campoProd.focus(); } // ao sair do campo, grava
      if (evento.key === "Escape") { evento.preventDefault(); evento.stopPropagation(); campo.value = original; campoProd.focus(); }
    });
    campo.addEventListener("blur", function () {
      if (!campo.isConnected) return;
      const texto = campo.value.trim().replace(",", ".");
      if (texto === "" || Number(texto) === Number(item.quantidade)) { campo.value = original; return; }
      pedir("PUT", "/api/venda/itens/" + item.id, { quantidade: texto }, { mexeNaVenda: true }).then(function (r) {
        if (!r.ok && campo.isConnected) campo.value = original;
      });
    });
    const faixa = Number(item.faixa_qtd_min) > 1
      ? M.el("span", { class: "tag atacado", text: "a partir de " + M.qtd(item.faixa_qtd_min), title: "Preço por quantidade: vale a partir de " + M.qtd(item.faixa_qtd_min) + " " + item.unidade })
      : null;
    return M.el("tr", null,
      M.el("td", { text: String(i + 1) }),
      M.el("td", { text: item.codigo }),
      M.el("td", null, item.descricao, faixa),
      M.el("td", { class: "num" }, campo, M.el("span", { class: "un", text: item.unidade })),
      M.el("td", { class: "num", text: M.reais(item.preco_unitario_centavos) }),
      M.el("td", { class: "num", text: M.reais(item.total_centavos) }),
      M.el("td", null, M.el("button", {
        type: "button", class: "btn-x", text: "×", title: "Tirar este item da venda", "aria-label": "Tirar " + item.descricao + " da venda",
        onclick: function () { pedir("DELETE", "/api/venda/itens/" + item.id, undefined, { mexeNaVenda: true }); campoProd.focus(); },
      })));
  }

  function linhaVazia(texto) {
    return M.el("tr", null, M.el("td", { class: "sem-linhas", colSpan: 7, text: texto }));
  }

  function desenharItens(v) {
    // Se a pessoa estava digitando a quantidade de outro item, o foco e o texto voltam para ele.
    const foco = document.activeElement;
    const itemComFoco = foco && foco.dataset && corpoItens.contains(foco) ? foco.dataset.item : null;
    const textoComFoco = itemComFoco ? foco.value : "";

    porId("v-cont").textContent = v && v.itens.length ? v.itens.length + (v.itens.length === 1 ? " item" : " itens") : "—";
    if (!v || !v.itens.length) {
      let texto = "Nenhuma venda aberta. Passe o leitor ou digite o produto para começar.";
      if (!estado || !estado.caixa_aberto) texto = "O caixa está fechado.";
      else if (v) texto = "Venda nº " + v.numero + " aberta, ainda sem itens. Passe o leitor ou digite o produto.";
      M.trocar(corpoItens, linhaVazia(texto), ultima && !v ? linhaVazia(textoDaUltima()) : null);
      return;
    }
    M.trocar.apply(null, [corpoItens].concat(v.itens.map(linhaDeItem)));
    if (itemComFoco) {
      const campo = corpoItens.querySelector('input[data-item="' + itemComFoco + '"]');
      if (campo) { campo.focus(); campo.value = textoComFoco; }
    }
  }

  // ------------------------------------------------------------------ total, cliente e pagamentos
  function desenharTotal(v) {
    const total = porId("v-total");
    const situacao = porId("v-situacao");
    const ajuste = porId("v-ajuste");
    if (!v || !v.itens.length) {
      total.textContent = "—";
      total.title = v ? "venda sem itens" : "nenhuma venda aberta";
      porId("v-subtotal").textContent = "Subtotal: —";
      porId("v-desconto").textContent = "Desconto: —";
      ajuste.hidden = true;
      situacao.hidden = true;
      return;
    }
    total.textContent = M.formatarCentavos(v.total_centavos);
    total.title = "";
    porId("v-subtotal").textContent = "Subtotal: " + M.formatarCentavos(v.subtotal_centavos);
    porId("v-desconto").textContent = "Desconto: " + (v.desconto_centavos ? M.formatarCentavos(-v.desconto_centavos) : "nenhum");
    ajuste.hidden = !v.ajuste_pagamento_centavos;
    ajuste.textContent = "Forma: " + (v.ajuste_pagamento_centavos > 0 ? "+" : "") + M.formatarCentavos(v.ajuste_pagamento_centavos);
    ajuste.title = "Desconto ou acréscimo das formas de pagamento já lançadas";
    const rotulo = situacao.children[0];
    const valor = situacao.children[1];
    situacao.hidden = false;
    if (v.restante_centavos > 0) {
      situacao.className = "situacao falta";
      rotulo.textContent = "Falta pagar";
      valor.textContent = M.formatarCentavos(v.restante_centavos);
    } else if (v.troco_centavos > 0) {
      situacao.className = "situacao troco";
      rotulo.textContent = "Troco";
      valor.textContent = M.formatarCentavos(v.troco_centavos);
    } else {
      situacao.className = "situacao pago";
      rotulo.textContent = "Pago";
      valor.textContent = "sem troco";
    }
  }

  function desenharCliente(v) {
    const c = v ? v.cliente : null;
    const nome = porId("cli-nome");
    nome.textContent = c ? c.nome : "Consumidor final";
    nome.title = c ? c.nome + " · " + (c.documento || "sem CPF ou CNPJ no cadastro") : "";
    const tag = porId("cli-tabela");
    const padrao = tabelaPadrao();
    tag.hidden = !v;
    if (v) {
      tag.textContent = v.tabela;
      tag.className = "tag " + (padrao && padrao.nome === v.tabela ? "comum" : "atacado");
      tag.title = "Tabela de preço desta venda";
    }
    porId("cli-tirar").hidden = !c;
  }

  function linhaDePagamento(v, p) {
    const selecao = M.el("select", { class: "campo", title: "Trocar a forma deste pagamento", "aria-label": "Forma deste pagamento" });
    v.formas.forEach(function (f) {
      if (!f.ativo && f.forma !== p.forma) return;
      const pct = M.pct(f.ajuste_bp);
      selecao.appendChild(M.el("option", { value: f.forma, text: f.rotulo + (pct ? " " + pct : "") }));
    });
    selecao.value = p.forma;
    selecao.addEventListener("change", function () {
      pedir("PUT", "/api/venda/pagamentos/" + p.id, { forma: selecao.value }).then(function (r) {
        if (!r.ok && selecao.isConnected) selecao.value = p.forma;
      });
    });
    const detalhes = [];
    if (p.ajuste_centavos < 0) detalhes.push("desconto " + M.reais(-p.ajuste_centavos));
    if (p.ajuste_centavos > 0) detalhes.push("acréscimo " + M.reais(p.ajuste_centavos));
    if (p.troco_centavos > 0) detalhes.push("troco " + M.reais(p.troco_centavos));
    return M.el("div", { class: "pg" },
      M.el("div", { class: "sel auto" }, selecao),
      M.el("div", { class: "valor" }, M.formatarCentavos(p.valor_centavos), detalhes.length ? M.el("small", { text: detalhes.join(" · ") }) : null),
      M.el("button", {
        type: "button", class: "btn-x", text: "×", title: "Tirar este pagamento", "aria-label": "Tirar o pagamento " + COMO[p.forma],
        onclick: function () { pedir("DELETE", "/api/venda/pagamentos/" + p.id); },
      }));
  }

  function desenharPagamentos(v) {
    const comItens = !!(v && v.itens.length);
    const falta = comItens ? v.restante_centavos : 0;
    pdv.querySelectorAll("[data-forma]").forEach(function (botao) {
      const f = (v ? v.formas : formasDaLoja).find(function (x) { return x.forma === botao.dataset.forma; });
      const linha2 = botao.querySelector(".l2");
      if (!f) { linha2.textContent = ""; botao.setAttribute("aria-disabled", "true"); return; }
      const pct = M.pct(f.ajuste_bp);
      if (!f.ativo) linha2.textContent = "desativada";
      else if (falta > 0) linha2.textContent = M.formatarCentavos(f.a_pagar_centavos) + (pct ? " (" + pct + ")" : "");
      else linha2.textContent = pct ? pct.slice(1) + (f.ajuste_bp < 0 ? " de desconto" : " de acréscimo") : "";
      botao.setAttribute("aria-disabled", !f.ativo || falta <= 0 ? "true" : "false");
    });
    if (!v || !v.pagamentos.length) {
      lancados.hidden = true;
      M.trocar(lancados);
    } else {
      const titulo = M.el("h3", { text: "Pagamentos lançados", title: "A forma de cada pagamento pode ser trocada na própria linha" });
      M.trocar.apply(null, [lancados, titulo].concat(v.pagamentos.map(function (p) { return linhaDePagamento(v, p); })));
      lancados.hidden = false;
    }
    btnFinalizar.setAttribute("aria-disabled", v && v.pode_finalizar ? "false" : "true");
  }

  function desenhar() {
    const v = venda();
    const aberto = !!(estado && estado.caixa_aberto);
    porId("aviso-fechado").hidden = aberto;
    [campoProd, campoQtd, campoCli, formItem.querySelector('button[type="submit"]')].forEach(function (el) { el.disabled = !aberto; });
    porId("v-numero").textContent = v ? String(v.numero) : "—";
    desenharItens(v);
    desenharTotal(v);
    desenharCliente(v);
    desenharPagamentos(v);
  }

  // ------------------------------------------------------------------ cliente
  const sugCli = criarSugestoes(campoCli, porId("sugestoes-cli"), function (li, c) {
    li.appendChild(M.el("span", { class: "nome", text: c.nome }));
    li.appendChild(M.el("span", { class: "doc", text: c.documento || "sem documento" }));
    if (c.tabela_nome) li.appendChild(M.el("span", { class: "tag atacado", text: c.tabela_nome }));
  }, function (c) { escolherCliente(c.id); });

  let relogioCli = 0;
  let pedidoCli = 0;

  async function buscarClientes(texto) {
    const numero = ++pedidoCli;
    const r = await M.api("GET", "/api/clientes?limite=8&busca=" + encodeURIComponent(texto));
    if (numero !== pedidoCli || campoCli.value.trim() !== texto) return null;
    if (!r.ok) { sugCli.fechar(); return null; }
    sugCli.mostrar(r.dados, "Nenhum cliente encontrado. Cadastre no menu Cadastros → Clientes.");
    return r.dados;
  }

  async function escolherCliente(id) {
    clearTimeout(relogioCli);
    campoCli.value = "";
    sugCli.fechar();
    await pedir("PUT", "/api/venda/cliente", { cliente_id: id });
    campoProd.focus();
  }

  campoCli.addEventListener("input", function () {
    clearTimeout(relogioCli);
    const texto = campoCli.value.trim();
    if (texto.length < 2) { sugCli.fechar(); return; }
    relogioCli = setTimeout(function () { buscarClientes(texto); }, 220);
  });

  campoCli.addEventListener("keydown", async function (evento) {
    if (sugCli.tecla(evento)) return;
    if (evento.key === "Enter") {
      evento.preventDefault();
      if (sugCli.aberta()) { sugCli.escolher(sugCli.marcada()); return; }
      const texto = campoCli.value.trim();
      if (texto.length < 2) return;
      clearTimeout(relogioCli);
      const achados = await buscarClientes(texto);
      if (achados && achados.length === 1) sugCli.escolher(0);
    } else if (evento.key === "Escape") {
      evento.preventDefault();
      evento.stopPropagation();
      clearTimeout(relogioCli);
      sugCli.fechar();
      campoCli.value = "";
      campoProd.focus();
    }
  });

  porId("cli-tirar").addEventListener("click", function () { escolherCliente(null); });

  // ------------------------------------------------------------------ pagamento
  async function pagar(forma) {
    const v = venda();
    if (!v || !v.itens.length) { M.avisar("Adicione um produto antes de receber."); return; }
    const f = v.formas.find(function (x) { return x.forma === forma; });
    if (!f || !f.ativo) { M.avisar("Esta forma de pagamento está desativada (Cadastros → Tabelas de preço e pagamento)."); return; }
    if (v.restante_centavos <= 0) { M.avisar("A venda já está toda paga. Finalize (F10) ou tire um pagamento para mudar."); return; }
    const partes = ["Falta pagar " + M.formatarCentavos(v.restante_centavos) + "."];
    if (f.ajuste_bp) {
      partes.push("Pagando " + COMO[forma] + " há " + M.pct(f.ajuste_bp).slice(1) + (f.ajuste_bp < 0 ? " de desconto" : " de acréscimo") + ": fica " + M.formatarCentavos(f.a_pagar_centavos) + ".");
    }
    partes.push(forma === "dinheiro"
      ? "Digite quanto o cliente entregou. Se for a mais, o sistema calcula o troco; se for a menos, o resto fica para outra forma."
      : "Para dividir em duas formas, digite só a parte paga " + COMO[forma] + ".");
    const texto = await M.perguntarValor({
      titulo: "Receber " + COMO[forma],
      texto: partes.join(" "),
      rotulo: forma === "dinheiro" ? "Valor entregue (R$)" : "Valor " + COMO[forma] + " (R$)",
      valor: M.reais(f.a_pagar_centavos),
      confirmar: "Lançar (Enter)",
    });
    if (texto === null) { campoProd.focus(); return; }
    const centavos = M.lerReais(texto);
    if (centavos === null || centavos <= 0) { M.avisar("Valor inválido. Digite assim: 10,00"); return; }
    const r = await pedir("POST", "/api/venda/pagamentos", { forma: forma, valor_centavos: centavos });
    const depois = venda();
    if (r.ok && depois && depois.pode_finalizar) btnFinalizar.focus();
    else campoProd.focus();
  }

  pdv.querySelectorAll("[data-forma]").forEach(function (botao) {
    botao.addEventListener("click", function () { pagar(botao.dataset.forma); });
  });

  // ------------------------------------------------------------------ desconto (só o gerente)
  if (btnDesconto) {
    btnDesconto.addEventListener("click", async function () {
      const v = venda();
      if (!v || !v.itens.length) { M.avisar("Adicione um produto antes de dar desconto."); return; }
      const texto = await M.perguntarValor({
        titulo: "Desconto na venda",
        texto: "Subtotal: " + M.formatarCentavos(v.subtotal_centavos) + ". Digite o desconto em reais (por exemplo 5,00) ou em porcentagem (por exemplo 10%). Para tirar o desconto, digite 0.",
        rotulo: "Desconto (R$ ou %)",
        valor: v.desconto_centavos ? M.reais(v.desconto_centavos) : "",
        confirmar: "Aplicar (Enter)",
      });
      if (texto === null) { campoProd.focus(); return; }
      const t = texto.trim();
      let corpo;
      if (t.slice(-1) === "%") {
        const pct = Number(t.slice(0, -1).trim().replace(",", "."));
        if (t.length < 2 || !isFinite(pct)) { M.avisar("Percentual inválido. Digite assim: 10%"); return; }
        corpo = { percentual: String(pct) };
      } else {
        const centavos = t === "" ? 0 : M.lerReais(t);
        if (centavos === null || centavos < 0) { M.avisar("Valor inválido. Digite assim: 5,00 ou 10%"); return; }
        corpo = { centavos: centavos };
      }
      await pedir("PUT", "/api/venda/desconto", corpo, { mexeNaVenda: true });
      campoProd.focus();
    });
  }

  // ------------------------------------------------------------------ finalizar (com ou sem NFC-e)
  btnFinalizar.addEventListener("click", function () {
    const v = venda();
    if (!v || !v.itens.length) { M.avisar("Não há venda aberta."); return; }
    if (!v.pode_finalizar) {
      M.avisar("Ainda falta pagar " + M.formatarCentavos(v.restante_centavos) + ". Escolha a forma de pagamento (F6 a F9).");
      return;
    }
    const valores = {
      total: M.formatarCentavos(v.total_centavos),
      pagamento: textoDosPagamentos(v),
      troco: v.troco_centavos ? M.formatarCentavos(v.troco_centavos) : "sem troco",
    };
    dlgFinalizar.querySelectorAll("[data-fim]").forEach(function (el) {
      if (valores[el.dataset.fim] !== undefined) el.textContent = valores[el.dataset.fim];
    });
    const nfce = dlgFinalizar.querySelector('[data-fim="nfce"]');
    const comNfce = porId("df-com");
    comNfce.disabled = !estado.nfce_disponivel;
    nfce.textContent = estado.nfce_disponivel ? "" : "Nesta versão a NFC-e ainda não é emitida: falta configurar a parte fiscal. Por enquanto a venda é finalizada sem NFC-e.";
    nfce.title = estado.nfce_disponivel ? "" : estado.nfce_motivo;
    M.mensagem(dlgFinalizar, "");
    dlgFinalizar.showModal();
    (estado.nfce_disponivel ? comNfce : porId("df-sem")).focus();
  });

  let concluindo = false; // um Enter repetido não finaliza duas vezes

  async function concluir(comNfce) {
    if (concluindo) return;
    concluindo = true;
    const r = await pedir("POST", "/api/venda/finalizar", { emitir_nfce: comNfce }, { calado: true });
    concluindo = false;
    if (!r.ok) { M.mensagem(dlgFinalizar, r.erro); return; }
    dlgFinalizar.close();
    const feita = r.dados.venda;
    campoQtd.value = "1";
    M.atualizarResumoDoDia();
    if (feita.troco_centavos > 0) {
      porId("dt-titulo").textContent = "Venda nº " + feita.numero + " finalizada";
      dlgFim.querySelector("[data-troco-resumo]").textContent = "Total " + M.formatarCentavos(feita.total_centavos) + " · " + textoDosPagamentos(feita);
      dlgFim.querySelector("[data-troco-valor]").textContent = M.formatarCentavos(feita.troco_centavos);
      dlgFim.showModal();
    } else {
      M.avisar("Venda nº " + feita.numero + " finalizada: " + M.formatarCentavos(feita.total_centavos) + ".");
      campoProd.focus();
    }
  }

  porId("df-sem").addEventListener("click", function () { concluir(false); });
  porId("df-com").addEventListener("click", function () { concluir(true); });
  dlgFim.addEventListener("close", function () { campoProd.focus(); });

  // ------------------------------------------------------------------ cancelar a venda aberta
  porId("btn-cancelar").addEventListener("click", async function () {
    const v = venda();
    if (!v) { M.avisar("Não há venda aberta para cancelar."); return; }
    const n = v.itens.length;
    const resposta = await M.confirmar({
      titulo: "Cancelar a venda nº " + v.numero + "?",
      texto: n
        ? (n === 1 ? "O item e" : "Os " + n + " itens e") + " os pagamentos lançados serão descartados. A venda fica registrada como cancelada, com o seu nome."
        : "A venda está sem itens e será descartada.",
      sim: "Cancelar a venda",
      perigo: true,
      motivo: "opcional",
    });
    if (!resposta.ok) { campoProd.focus(); return; }
    const r = await pedir("POST", "/api/venda/cancelar", { motivo: resposta.motivo });
    if (r.ok) M.avisar("Venda nº " + v.numero + " cancelada.");
    campoProd.focus();
  });

  // ------------------------------------------------------------------ saldo de vendas do dia
  porId("saldo-do-dia").addEventListener("click", async function () {
    const d = await M.atualizarResumoDoDia();
    const tem = !!(d && d.quantidade);
    const valores = {
      total: tem ? M.formatarCentavos(d.total_centavos) : "—",
      quantidade: d ? String(d.quantidade) : "—",
      ticket: tem ? M.formatarCentavos(d.ticket_medio_centavos) : "—",
    };
    ["dinheiro", "pix", "debito", "credito"].forEach(function (forma) {
      valores[forma] = tem ? M.formatarCentavos(d.recebido[forma] || 0) : "—";
    });
    dlgSaldo.querySelectorAll("[data-saldo]").forEach(function (el) { el.textContent = valores[el.dataset.saldo] || "—"; });
    const motivo = dlgSaldo.querySelector("[data-saldo-motivo]");
    motivo.textContent = d ? (tem ? "" : "Sem dados: " + d.motivo + ".") : "Sem dados: sem resposta do servidor local.";
    motivo.hidden = !motivo.textContent;
    dlgSaldo.showModal();
  });

  // ------------------------------------------------------------------ início
  (async function iniciar() {
    const respostas = await Promise.all([M.api("GET", "/api/tabelas-preco"), M.api("GET", "/api/formas-pagamento")]);
    tabelas = respostas[0].ok ? respostas[0].dados : [];
    formasDaLoja = respostas[1].ok ? respostas[1].dados : [];
    await recarregar();
    if (estado && estado.caixa_aberto) campoProd.focus();
  })();
})();

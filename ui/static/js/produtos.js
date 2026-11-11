/* Moleka PDV — tela Produtos (só o gerente): lista com pesquisa e ficha com preços por tabela
   e por quantidade. Tudo vem de /api/produtos; nada de exemplo. Preços em centavos na API. */

(function () {
  "use strict";

  const M = window.Moleka;
  const form = document.getElementById("form-produto");
  const corpo = document.querySelector("#tabela-produtos tbody");
  if (!form || !corpo) return;

  const corpoPrecos = document.querySelector("#tabela-precos tbody");
  const titulo = document.getElementById("t-ficha");
  const contagem = document.querySelector("[data-contagem]");
  const busca = document.getElementById("busca");
  const verInativos = document.getElementById("ver-inativos");
  const soNaEdicao = form.querySelector("[data-so-na-edicao]");

  const LIMITE = 500; // o máximo que a API devolve de uma vez
  let produtos = [];
  let tabelas = [];
  let editando = null;
  let relogioDaBusca = 0;

  function padrao() { return tabelas.find(function (t) { return t.padrao; }) || tabelas[0]; }

  /* Preço que aparece na lista: o da tabela padrão, a partir de 1. */
  function precoDeLista(p) {
    const t = padrao();
    if (!t) return null;
    const faixas = p.precos.filter(function (f) { return f.tabela_id === t.id; });
    faixas.sort(function (a, b) { return Number(a.qtd_min) - Number(b.qtd_min); });
    return faixas.length ? faixas[0].preco_centavos : null;
  }

  function linhaUnica(texto) {
    M.trocar(corpo, M.el("tr", null, M.el("td", { class: "sem-linhas", colSpan: 5, text: texto })));
  }

  function desenhar() {
    contagem.textContent = produtos.length >= LIMITE
      ? "os primeiros " + LIMITE + " (use a pesquisa para achar os outros)"
      : produtos.length + (produtos.length === 1 ? " produto" : " produtos");
    if (!produtos.length) {
      linhaUnica(busca.value.trim() ? "Nenhum produto encontrado para essa pesquisa." : "Nenhum produto cadastrado. Preencha a ficha ao lado e salve.");
      return;
    }
    M.trocar.apply(null, [corpo].concat(produtos.map(function (p) {
      const preco = precoDeLista(p);
      return M.el("tr", { class: (p.id === editando ? "selecionada" : "") + (p.ativo ? "" : " inativa") },
        M.el("td", { text: p.codigo }),
        M.el("td", null, p.descricao, p.categoria ? M.el("span", { class: "sub", text: p.categoria }) : null),
        M.el("td", { class: "num", text: preco === null ? "—" : M.reais(preco), title: preco === null ? "sem preço na tabela padrão" : "" }),
        M.el("td", null, M.el("span", { class: "tag " + (p.ativo ? "ativo" : "inativo"), text: p.ativo ? "Ativo" : "Inativo" })),
        M.el("td", null, M.el("button", { type: "button", class: "btn3d mini", text: "Alterar", "aria-label": "Alterar " + p.descricao, onclick: function () { abrir(p.id); } })));
    })));
  }

  async function carregar() {
    const filtros = new URLSearchParams({ limite: String(LIMITE) });
    if (busca.value.trim()) filtros.set("busca", busca.value.trim());
    if (verInativos.checked) filtros.set("inativos", "true");
    const vale = M.novaCarga("produtos");
    const r = await M.api("GET", "/api/produtos?" + filtros.toString());
    if (!vale()) return; // já saiu uma pesquisa mais nova: esta resposta não serve mais
    if (!r.ok) { contagem.textContent = "—"; linhaUnica("Não foi possível carregar os produtos: " + r.erro); return; }
    produtos = r.dados;
    desenhar();
  }

  async function carregarCategorias() {
    const r = await M.api("GET", "/api/produtos/categorias");
    if (!r.ok) return;
    M.trocar.apply(null, [document.getElementById("categorias")].concat(r.dados.map(function (c) { return M.el("option", { value: c }); })));
  }

  // ------------------------------------------------------------------ faixas de preço da ficha
  function linhaDeFaixa(faixa) {
    const selecao = M.el("select", { class: "campo", "aria-label": "Tabela de preço" });
    tabelas.forEach(function (t) { selecao.appendChild(M.el("option", { value: String(t.id), text: t.nome })); });
    selecao.value = String(faixa.tabela_id);
    const tr = M.el("tr", null,
      M.el("td", null, M.el("div", { class: "sel auto" }, selecao)),
      M.el("td", null, M.el("input", { class: "campo num", type: "text", inputMode: "decimal", value: M.qtd(faixa.qtd_min), "aria-label": "A partir de quantas unidades" })),
      M.el("td", null, M.el("input", { class: "campo num", type: "text", inputMode: "decimal", value: faixa.preco_centavos === null ? "" : M.reais(faixa.preco_centavos), placeholder: "0,00", "aria-label": "Preço unitário" })),
      M.el("td", null, M.el("button", { type: "button", class: "btn-x", title: "Remover esta faixa", "aria-label": "Remover esta faixa", text: "×", onclick: function () { tr.remove(); } })));
    return tr;
  }

  function desenharFaixas(precos) {
    M.trocar.apply(null, [corpoPrecos].concat(precos.map(linhaDeFaixa)));
  }

  /* Lê as faixas digitadas. Devolve a lista ou um texto de erro. Linha sem preço é ignorada. */
  function lerFaixas() {
    const faixas = [];
    const linhas = corpoPrecos.querySelectorAll("tr");
    for (let i = 0; i < linhas.length; i++) {
      const campos = linhas[i].querySelectorAll("select, input");
      const textoPreco = campos[2].value.trim();
      if (!textoPreco) continue;
      const preco = M.lerReais(textoPreco);
      const qtd = Number(campos[1].value.trim().replace(",", "."));
      if (preco === null || preco < 0) return "Preço inválido na linha " + (i + 1) + ". Digite assim: 5,00";
      if (!isFinite(qtd) || qtd <= 0) return "Quantidade inválida na linha " + (i + 1) + ".";
      faixas.push({ tabela_id: Number(campos[0].value), qtd_min: String(qtd), preco_centavos: preco });
    }
    return faixas;
  }

  // ------------------------------------------------------------------ ficha
  function novo() {
    editando = null;
    form.reset();
    M.mensagem(form, "");
    titulo.textContent = "Novo produto";
    soNaEdicao.hidden = true;
    form.querySelector("details").open = false;
    desenharFaixas(tabelas.map(function (t) { return { tabela_id: t.id, qtd_min: 1, preco_centavos: null }; }));
    desenhar();
    form.descricao.focus();
  }

  function abrir(id) {
    const p = produtos.find(function (x) { return x.id === id; });
    if (!p) return;
    editando = id;
    form.reset();
    M.mensagem(form, "");
    titulo.textContent = "Alterar produto";
    form.codigo.value = p.codigo;
    form.ean.value = p.ean || "";
    if (!Array.from(form.unidade.options).some(function (o) { return o.value === p.unidade; })) form.unidade.appendChild(M.el("option", { value: p.unidade, text: p.unidade }));
    form.unidade.value = p.unidade;
    form.descricao.value = p.descricao;
    form.categoria.value = p.categoria || "";
    form.custo.value = p.custo_centavos === null ? "" : M.reais(p.custo_centavos);
    form.minimo.value = Number(p.estoque_minimo) ? M.qtd(p.estoque_minimo) : "";
    form.ncm.value = p.ncm || "";
    form.cest.value = p.cest || "";
    form.cst_csosn.value = p.cst_csosn || "";
    form.origem.value = p.origem || "0";
    form.ativo.checked = p.ativo;
    soNaEdicao.hidden = false;
    desenharFaixas(p.precos.length ? p.precos : [{ tabela_id: padrao().id, qtd_min: 1, preco_centavos: null }]);
    desenhar();
    form.descricao.focus();
  }

  form.addEventListener("submit", async function (evento) {
    evento.preventDefault();
    const descricao = form.descricao.value.trim();
    if (!descricao) { M.mensagem(form, "Digite a descrição do produto."); form.descricao.focus(); return; }
    const faixas = lerFaixas();
    if (typeof faixas === "string") { M.mensagem(form, faixas); return; }
    const custo = form.custo.value.trim() ? M.lerReais(form.custo.value) : null;
    if (form.custo.value.trim() && custo === null) { M.mensagem(form, "Custo inválido. Digite assim: 2,50"); form.custo.focus(); return; }
    const minimo = Number((form.minimo.value.trim() || "0").replace(",", "."));
    if (!isFinite(minimo) || minimo < 0) { M.mensagem(form, "Estoque mínimo inválido."); form.minimo.focus(); return; }
    const dados = {
      codigo: form.codigo.value.trim() || null, descricao: descricao, categoria: form.categoria.value.trim() || null,
      ean: form.ean.value.trim() || null, unidade: form.unidade.value, ncm: form.ncm.value.trim() || null,
      cest: form.cest.value.trim() || null, cst_csosn: form.cst_csosn.value.trim() || null, origem: form.origem.value.trim() || "0",
      custo_centavos: custo, estoque_minimo: String(minimo), ativo: editando === null ? true : form.ativo.checked, precos: faixas,
    };
    const r = editando === null ? await M.api("POST", "/api/produtos", dados) : await M.api("PUT", "/api/produtos/" + editando, dados);
    if (!r.ok) { M.mensagem(form, r.erro); return; }
    M.avisar(editando === null ? "Produto " + r.dados.descricao + " cadastrado (código " + r.dados.codigo + ")." : "Produto " + r.dados.descricao + " salvo.");
    if (!faixas.length) M.avisar("Produto salvo SEM preço: ele não poderá ser vendido até ter preço.");
    editando = null;
    await carregar();
    carregarCategorias();
    novo();
  });

  form.addEventListener("keydown", function (evento) {
    const emUso = editando !== null || form.descricao.value !== "" || form.codigo.value !== "";
    if (evento.key !== "Escape" || !emUso) return;
    evento.preventDefault();
    evento.stopPropagation();
    novo();
  });
  form.querySelector("[data-nova-faixa]").addEventListener("click", function () {
    corpoPrecos.appendChild(linhaDeFaixa({ tabela_id: padrao().id, qtd_min: 10, preco_centavos: null }));
    const campos = corpoPrecos.lastElementChild.querySelectorAll("input");
    campos[0].focus();
    campos[0].select();
  });
  form.querySelector("[data-limpar]").addEventListener("click", novo);
  document.querySelector("[data-novo]").addEventListener("click", novo);
  verInativos.addEventListener("change", carregar);
  busca.addEventListener("input", function () { clearTimeout(relogioDaBusca); relogioDaBusca = setTimeout(carregar, 250); });

  (async function iniciar() {
    const r = await M.api("GET", "/api/tabelas-preco");
    tabelas = r.ok ? r.dados : [];
    if (!tabelas.length) { M.mensagem(form, "Cadastre antes uma tabela de preço em Cadastros → Tabelas de preço e pagamento."); }
    const coluna = document.querySelector("[data-coluna-preco]");
    if (padrao()) coluna.textContent = "Preço " + padrao().nome.toLowerCase() + " (R$)";
    await carregar();
    carregarCategorias();
    novo();
  })();
})();

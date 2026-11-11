/* Moleka PDV — tela Tabelas de Preço (só o gerente): as tabelas (varejo, atacado...) e o
   percentual de desconto ou acréscimo de cada forma de pagamento. */

(function () {
  "use strict";

  const M = window.Moleka;
  const form = document.getElementById("form-tabela");
  const corpo = document.querySelector("#tabela-tabelas tbody");
  const corpoFormas = document.querySelector("#tabela-formas tbody");
  if (!form || !corpo || !corpoFormas) return;

  const rotulo = document.getElementById("t-ficha");
  const contagem = document.querySelector("[data-contagem]");
  const soNaEdicao = form.querySelector("[data-so-na-edicao]");
  const msgFormas = document.getElementById("msg-formas");
  let tabelas = [];
  let editando = null;

  function desenhar() {
    contagem.textContent = tabelas.length + (tabelas.length === 1 ? " tabela" : " tabelas");
    if (!tabelas.length) {
      M.trocar(corpo, M.el("tr", null, M.el("td", { class: "sem-linhas", colSpan: 4, text: "Nenhuma tabela cadastrada. Crie a primeira abaixo." })));
      return;
    }
    M.trocar.apply(null, [corpo].concat(tabelas.map(function (t) {
      return M.el("tr", { class: (t.id === editando ? "selecionada" : "") + (t.ativo ? "" : " inativa") },
        M.el("td", { text: t.nome }),
        M.el("td", null, t.padrao ? M.el("span", { class: "tag gerente", text: "Padrão" }) : null),
        M.el("td", null, M.el("span", { class: "tag " + (t.ativo ? "ativo" : "inativo"), text: t.ativo ? "Ativa" : "Inativa" })),
        M.el("td", null, M.el("button", { type: "button", class: "btn3d mini", text: "Alterar", "aria-label": "Alterar a tabela " + t.nome, onclick: function () { abrir(t.id); } })));
    })));
  }

  async function carregar() {
    const r = await M.api("GET", "/api/tabelas-preco?todas=true");
    if (!r.ok) { M.trocar(corpo, M.el("tr", null, M.el("td", { class: "sem-linhas", colSpan: 4, text: "Não foi possível carregar: " + r.erro }))); return; }
    tabelas = r.dados;
    desenhar();
  }

  function novo() {
    editando = null;
    form.reset();
    M.mensagem(form, "");
    rotulo.textContent = "Nova tabela";
    soNaEdicao.hidden = true;
    desenhar();
  }

  function abrir(id) {
    const t = tabelas.find(function (x) { return x.id === id; });
    if (!t) return;
    editando = id;
    M.mensagem(form, "");
    rotulo.textContent = "Alterar a tabela";
    form.nome.value = t.nome;
    form.padrao.checked = t.padrao;
    form.ativo.checked = t.ativo;
    soNaEdicao.hidden = false;
    desenhar();
    form.nome.focus();
  }

  form.addEventListener("submit", async function (evento) {
    evento.preventDefault();
    const nome = form.nome.value.trim();
    if (!nome) { M.mensagem(form, "Digite o nome da tabela."); form.nome.focus(); return; }
    const r = editando === null
      ? await M.api("POST", "/api/tabelas-preco", { nome: nome, padrao: form.padrao.checked })
      : await M.api("PUT", "/api/tabelas-preco/" + editando, { nome: nome, padrao: form.padrao.checked, ativo: form.ativo.checked });
    if (!r.ok) { M.mensagem(form, r.erro); return; }
    M.avisar("Tabela " + r.dados.nome + " salva.");
    await carregar();
    novo();
  });
  form.querySelector("[data-limpar]").addEventListener("click", novo);

  // ------------------------------------------------------------------ formas de pagamento
  function avisoFormas(texto) {
    msgFormas.textContent = texto || "";
    msgFormas.hidden = !texto;
  }

  function linhaDeForma(f) {
    const ajuste = M.el("input", { class: "campo num", type: "text", inputMode: "decimal", value: String(f.ajuste_bp / 100).replace(".", ","), "aria-label": "Ajuste em % para " + f.rotulo });
    const ativa = M.el("input", { type: "checkbox", checked: f.ativo, "aria-label": f.rotulo + " ativa" });
    async function salvar() {
      const pct = Number(ajuste.value.trim().replace(",", ".") || "0");
      if (!isFinite(pct)) { avisoFormas("Percentual inválido em " + f.rotulo + ". Digite assim: -5 ou 3,5"); ajuste.focus(); return; }
      const r = await M.api("PUT", "/api/formas-pagamento/" + f.forma, { ajuste_bp: Math.round(pct * 100), ativo: ativa.checked });
      if (!r.ok) { avisoFormas(r.erro); return; }
      avisoFormas("");
      M.avisar(r.dados.rotulo + ": " + (r.dados.ajuste_bp ? M.pct(r.dados.ajuste_bp) : "sem ajuste") + (r.dados.ativo ? "" : " (desativada)") + ".");
      carregarFormas();
    }
    const botao = M.el("button", { type: "button", class: "btn3d mini", text: "Salvar", "aria-label": "Salvar " + f.rotulo, onclick: salvar });
    // O botão fica amarelo enquanto houver mudança ainda não salva nesta linha.
    function mudou() { botao.classList.add("amarelo"); }
    ajuste.addEventListener("input", mudou);
    ativa.addEventListener("change", mudou);
    ajuste.addEventListener("keydown", function (evento) { if (evento.key === "Enter") { evento.preventDefault(); salvar(); } });
    return M.el("tr", null,
      M.el("td", { text: f.rotulo }),
      M.el("td", null, ajuste),
      M.el("td", null, M.el("label", { class: "check" }, ativa)),
      M.el("td", null, botao));
  }

  async function carregarFormas() {
    const r = await M.api("GET", "/api/formas-pagamento");
    if (!r.ok) { M.trocar(corpoFormas, M.el("tr", null, M.el("td", { class: "sem-linhas", colSpan: 4, text: "Não foi possível carregar: " + r.erro }))); return; }
    M.trocar.apply(null, [corpoFormas].concat(r.dados.map(linhaDeForma)));
  }

  carregar().then(novo);
  carregarFormas();
})();

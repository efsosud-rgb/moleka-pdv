/* Moleka PDV — tela Clientes: lista com pesquisa e ficha. O CPF ou CNPJ é conferido pelo
   servidor (dígitos verificadores). A tabela de preço do cliente, só o gerente define. */

(function () {
  "use strict";

  const M = window.Moleka;
  const form = document.getElementById("form-cliente");
  const corpo = document.querySelector("#tabela-clientes tbody");
  if (!form || !corpo) return;

  const titulo = document.getElementById("t-ficha");
  const contagem = document.querySelector("[data-contagem]");
  const busca = document.getElementById("busca");
  const verInativos = document.getElementById("ver-inativos");
  const soNaEdicao = form.querySelector("[data-so-na-edicao]");

  let clientes = [];
  let editando = null;
  let relogioDaBusca = 0;
  let nomeDaPadrao = ""; // nome da tabela padrão da loja (ex.: VAREJO), para mostrar na lista

  function linhaUnica(texto) {
    M.trocar(corpo, M.el("tr", null, M.el("td", { class: "sem-linhas", colSpan: 5, text: texto })));
  }

  function desenhar() {
    contagem.textContent = clientes.length + (clientes.length === 1 ? " cliente" : " clientes");
    if (!clientes.length) {
      linhaUnica(busca.value.trim() ? "Nenhum cliente encontrado para essa pesquisa." : "Nenhum cliente cadastrado. Preencha a ficha ao lado e salve.");
      return;
    }
    M.trocar.apply(null, [corpo].concat(clientes.map(function (c) {
      return M.el("tr", { class: (c.id === editando ? "selecionada" : "") + (c.ativo ? "" : " inativa") },
        M.el("td", null, c.nome, c.telefone ? M.el("span", { class: "sub", text: c.telefone }) : null),
        M.el("td", { text: c.documento || "—", title: c.documento ? "" : "sem documento cadastrado" }),
        M.el("td", null, M.el("span", { class: "tag " + (c.tabela_nome ? "gerente" : "comum"), text: c.tabela_nome || nomeDaPadrao || "Padrão", title: c.tabela_nome ? "" : "tabela padrão da loja" })),
        M.el("td", null, M.el("span", { class: "tag " + (c.ativo ? "ativo" : "inativo"), text: c.ativo ? "Ativo" : "Inativo" })),
        M.el("td", null, M.el("button", { type: "button", class: "btn3d mini", text: "Alterar", "aria-label": "Alterar " + c.nome, onclick: function () { abrir(c.id); } })));
    })));
  }

  async function carregar() {
    const filtros = new URLSearchParams();
    if (busca.value.trim()) filtros.set("busca", busca.value.trim());
    if (verInativos && verInativos.checked) filtros.set("inativos", "true");
    const r = await M.api("GET", "/api/clientes?" + filtros.toString());
    if (!r.ok) { contagem.textContent = "—"; linhaUnica("Não foi possível carregar os clientes: " + r.erro); return; }
    clientes = r.dados;
    desenhar();
  }

  function novo() {
    editando = null;
    form.reset();
    M.mensagem(form, "");
    titulo.textContent = "Novo cliente";
    soNaEdicao.hidden = true;
    desenhar();
    form.nome.focus();
  }

  function abrir(id) {
    const c = clientes.find(function (x) { return x.id === id; });
    if (!c) return;
    editando = id;
    form.reset();
    M.mensagem(form, "");
    titulo.textContent = "Alterar cliente";
    form.nome.value = c.nome;
    form.cpf_cnpj.value = c.documento || "";
    form.telefone.value = c.telefone || "";
    form.email.value = c.email || "";
    form.endereco.value = c.endereco || "";
    const tabela = c.tabela_id === null ? "" : String(c.tabela_id);
    // Tabela que não está na lista (inativa, ou a própria padrão): entra só para este cliente.
    if (tabela && !Array.from(form.tabela_id.options).some(function (o) { return o.value === tabela; })) {
      form.tabela_id.appendChild(M.el("option", { value: tabela, text: c.tabela_nome || "Tabela " + tabela }));
    }
    form.tabela_id.value = tabela;
    form.observacao.value = c.observacao || "";
    form.ativo.checked = c.ativo;
    soNaEdicao.hidden = false;
    desenhar();
    form.nome.focus();
  }

  form.addEventListener("submit", async function (evento) {
    evento.preventDefault();
    const nome = form.nome.value.trim();
    if (!nome) { M.mensagem(form, "Digite o nome do cliente."); form.nome.focus(); return; }
    const dados = {
      nome: nome, cpf_cnpj: form.cpf_cnpj.value.trim() || null, telefone: form.telefone.value.trim() || null,
      email: form.email.value.trim() || null, endereco: form.endereco.value.trim() || null,
      tabela_id: form.tabela_id.value ? Number(form.tabela_id.value) : null,
      observacao: form.observacao.value.trim() || null, ativo: editando === null ? true : form.ativo.checked,
    };
    const r = editando === null ? await M.api("POST", "/api/clientes", dados) : await M.api("PUT", "/api/clientes/" + editando, dados);
    if (!r.ok) { M.mensagem(form, r.erro); return; }
    M.avisar(editando === null ? "Cliente " + r.dados.nome + " cadastrado." : "Cadastro de " + r.dados.nome + " salvo.");
    editando = null;
    await carregar();
    novo();
  });

  form.addEventListener("keydown", function (evento) {
    const emUso = editando !== null || form.nome.value !== "" || form.cpf_cnpj.value !== "";
    if (evento.key !== "Escape" || !emUso) return;
    evento.preventDefault();
    evento.stopPropagation();
    novo();
  });
  form.querySelector("[data-limpar]").addEventListener("click", novo);
  document.querySelector("[data-novo]").addEventListener("click", novo);
  if (verInativos) verInativos.addEventListener("change", carregar);
  busca.addEventListener("input", function () { clearTimeout(relogioDaBusca); relogioDaBusca = setTimeout(carregar, 250); });

  (async function iniciar() {
    const r = await M.api("GET", "/api/tabelas-preco");
    (r.ok ? r.dados : []).forEach(function (t) {
      if (t.padrao) {
        nomeDaPadrao = t.nome;
        form.tabela_id.options[0].textContent = t.nome + " (padrão da loja)";
      } else {
        form.tabela_id.appendChild(M.el("option", { value: String(t.id), text: t.nome }));
      }
    });
    await carregar();
    novo();
  })();
})();

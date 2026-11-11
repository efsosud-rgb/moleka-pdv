/* Moleka PDV — tela Operadores (só o gerente): lista, novo, alterar, inativar e trocar senha.
   A lista vem de /api/operadores. Os nomes entram na página como texto (textContent), nunca
   como HTML. */

(function () {
  "use strict";

  const Moleka = window.Moleka;
  const tabela = document.getElementById("tabela-operadores");
  const form = document.getElementById("form-operador");
  if (!tabela || !form) return;

  const corpo = tabela.querySelector("tbody");
  const eu = Number(tabela.dataset.eu);
  const titulo = document.getElementById("t-ficha");
  const contagem = document.querySelector("[data-contagem]");
  const soNaEdicao = form.querySelector("[data-so-na-edicao]");
  const dicaSenha = form.querySelector("[data-dica-senha]");
  const ROTULO_PERFIL = { gerente: "Gerente", operador: "Operador" };

  let operadores = [];
  let editando = null; // id do operador aberto na ficha, ou null para um novo

  function celula(texto) {
    const td = document.createElement("td");
    td.textContent = texto;
    return td;
  }

  function etiqueta(texto, classe) {
    const span = document.createElement("span");
    span.className = "tag " + classe;
    span.textContent = texto;
    return span;
  }

  function linhaUnica(texto) {
    corpo.replaceChildren();
    const tr = document.createElement("tr");
    const td = celula(texto);
    td.className = "sem-linhas";
    td.colSpan = 5;
    tr.appendChild(td);
    corpo.appendChild(tr);
  }

  function desenhar() {
    if (!operadores.length) { linhaUnica("Nenhum operador cadastrado."); return; }
    corpo.replaceChildren();
    operadores.forEach(function (op) {
      const tr = document.createElement("tr");
      if (op.id === editando) tr.className = "selecionada";
      if (!op.ativo) tr.classList.add("inativa");
      tr.appendChild(celula(op.nome + (op.id === eu ? " (você)" : "")));
      tr.appendChild(celula(op.login));
      const perfil = document.createElement("td");
      perfil.appendChild(etiqueta(ROTULO_PERFIL[op.perfil] || op.perfil, op.perfil === "gerente" ? "gerente" : "comum"));
      tr.appendChild(perfil);
      const situacao = document.createElement("td");
      situacao.appendChild(etiqueta(op.ativo ? "Ativo" : "Inativo", op.ativo ? "ativo" : "inativo"));
      tr.appendChild(situacao);
      const acoes = document.createElement("td");
      const botao = document.createElement("button");
      botao.type = "button";
      botao.className = "btn3d mini";
      botao.textContent = "Alterar";
      botao.setAttribute("aria-label", "Alterar " + op.nome);
      botao.addEventListener("click", function () { abrir(op.id); });
      acoes.appendChild(botao);
      tr.appendChild(acoes);
      corpo.appendChild(tr);
    });
    const ativos = operadores.filter(function (op) { return op.ativo; }).length;
    contagem.textContent = operadores.length + (operadores.length === 1 ? " cadastrado" : " cadastrados") + " · " + ativos + (ativos === 1 ? " ativo" : " ativos");
  }

  async function carregar() {
    const r = await Moleka.api("GET", "/api/operadores");
    if (!r.ok) {
      contagem.textContent = "—";
      linhaUnica("Não foi possível carregar os operadores: " + r.erro);
      return;
    }
    operadores = r.dados;
    desenhar();
  }

  function fichaEmUso() {
    return editando !== null || form.nome.value !== "" || form.login.value !== "" || form.senha.value !== "";
  }

  function novo() {
    editando = null;
    form.reset();
    Moleka.mensagem(form, "");
    titulo.textContent = "Novo operador";
    soNaEdicao.hidden = true;
    dicaSenha.hidden = true;
    form.perfil.disabled = false;
    form.ativo.disabled = false;
    desenhar();
    form.nome.focus();
  }

  function abrir(id) {
    const op = operadores.find(function (o) { return o.id === id; });
    if (!op) return;
    editando = id;
    form.reset();
    Moleka.mensagem(form, "");
    titulo.textContent = "Alterar operador";
    form.nome.value = op.nome;
    form.login.value = op.login;
    form.perfil.value = op.perfil;
    form.ativo.checked = op.ativo;
    soNaEdicao.hidden = false;
    dicaSenha.hidden = false;
    // Ninguém muda o próprio perfil nem se inativa (o servidor também recusa).
    form.perfil.disabled = id === eu;
    form.ativo.disabled = id === eu;
    if (id === eu) Moleka.mensagem(form, "Este é o seu usuário: o perfil e a situação só outro gerente muda.", "dica");
    desenhar();
    form.nome.focus();
  }

  form.addEventListener("submit", async function (evento) {
    evento.preventDefault();
    const nome = form.nome.value.trim();
    const login = form.login.value.trim();
    const senha = form.senha.value;
    if (!nome) { Moleka.mensagem(form, "Digite o nome do operador."); form.nome.focus(); return; }
    if (!login) { Moleka.mensagem(form, "Escolha o usuário, por exemplo o primeiro nome."); form.login.focus(); return; }
    if (editando === null && !senha) { Moleka.mensagem(form, "Crie uma senha para o operador."); form.senha.focus(); return; }
    if (senha && senha.length < 4) { Moleka.mensagem(form, "A senha precisa ter pelo menos 4 caracteres."); form.senha.focus(); return; }
    if (senha !== form.senha2.value) { Moleka.mensagem(form, "As duas senhas estão diferentes. Digite de novo."); form.senha2.value = ""; form.senha2.focus(); return; }

    const dados = { nome: nome, login: login, perfil: form.perfil.value, ativo: editando === null ? true : form.ativo.checked };
    if (senha) dados.senha = senha;
    const r = editando === null
      ? await Moleka.api("POST", "/api/operadores", dados)
      : await Moleka.api("PUT", "/api/operadores/" + editando, dados);
    if (!r.ok) { Moleka.mensagem(form, r.erro); return; }
    Moleka.avisar(editando === null ? "Operador " + r.dados.nome + " cadastrado." : "Cadastro de " + r.dados.nome + " salvo.");
    editando = null;
    await carregar();
    novo();
  });

  // Esc com a ficha em uso limpa a ficha; com a ficha vazia, segue para o Início (atalho comum).
  form.addEventListener("keydown", function (evento) {
    if (evento.key !== "Escape" || !fichaEmUso()) return;
    evento.preventDefault();
    evento.stopPropagation();
    novo();
  });

  document.querySelector("[data-novo-operador]").addEventListener("click", novo);
  form.querySelector("[data-cancelar-operador]").addEventListener("click", novo);
  Moleka.cuidarDasSenhas(form);
  carregar();
})();

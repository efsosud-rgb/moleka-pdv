/* Moleka PDV — capa: primeiro acesso (cria o gerente) e login do operador.
   A senha vai só para o servidor local (127.0.0.1); nada fica guardado na janela. A lista já
   vem do servidor aberta em quem entrou por último. */

(function () {
  "use strict";

  const Moleka = window.Moleka;

  /* "Maria Aparecida" → "maria": sugestão de usuário a partir do nome. */
  function sugerirUsuario(nome) {
    const primeiro = nome.trim().split(/\s+/)[0] || "";
    return primeiro.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9._-]/g, "").slice(0, 30);
  }

  function ocupar(form, ocupado) {
    form.querySelectorAll("button, input, select").forEach(function (el) { el.disabled = ocupado; });
  }

  // ------------------------------------------------------------------ primeiro acesso
  function iniciarPrimeiroAcesso(form) {
    Moleka.cuidarDasSenhas(form);
    let usuarioDigitado = false;
    form.login.addEventListener("input", function () { usuarioDigitado = form.login.value !== ""; });
    form.nome.addEventListener("input", function () {
      if (!usuarioDigitado) form.login.value = sugerirUsuario(form.nome.value);
    });
    form.addEventListener("submit", async function (evento) {
      evento.preventDefault();
      const nome = form.nome.value.trim();
      const login = form.login.value.trim();
      const senha = form.senha.value;
      if (!nome) { Moleka.mensagem(form, "Digite o seu nome."); form.nome.focus(); return; }
      if (!login) { Moleka.mensagem(form, "Escolha um usuário, por exemplo o seu primeiro nome."); form.login.focus(); return; }
      if (senha.length < 4) { Moleka.mensagem(form, "A senha precisa ter pelo menos 4 caracteres."); form.senha.focus(); return; }
      if (senha !== form.senha2.value) { Moleka.mensagem(form, "As duas senhas estão diferentes. Digite de novo."); form.senha2.value = ""; form.senha2.focus(); return; }
      ocupar(form, true);
      const r = await Moleka.api("POST", "/api/configuracao-inicial", { nome: nome, login: login, senha: senha });
      if (!r.ok) {
        ocupar(form, false);
        Moleka.mensagem(form, r.erro);
        if (r.status === 409) window.setTimeout(function () { window.location.reload(); }, 2500); // já existe gerente: mostra o login
        return;
      }
      window.location.href = "/inicio";
    });
  }

  // ------------------------------------------------------------------ login
  function iniciarLogin(form) {
    Moleka.cuidarDasSenhas(form);
    form.login.addEventListener("change", function () { form.senha.value = ""; form.senha.focus(); });
    form.senha.focus();
    form.addEventListener("submit", async function (evento) {
      evento.preventDefault();
      const login = form.login.value;
      const senha = form.senha.value;
      if (!senha) { Moleka.mensagem(form, "Digite a senha."); form.senha.focus(); return; }
      ocupar(form, true);
      const r = await Moleka.api("POST", "/api/login", { login: login, senha: senha });
      if (!r.ok) {
        ocupar(form, false);
        Moleka.mensagem(form, r.erro);
        form.senha.value = "";
        form.senha.focus();
        return;
      }
      window.location.href = "/inicio";
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    const inicial = document.getElementById("form-inicial");
    if (inicial) iniciarPrimeiroAcesso(inicial);
    const login = document.getElementById("form-login");
    if (login) iniciarLogin(login);
  });
})();

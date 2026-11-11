/* Moleka PDV — JS comum da interface.
   Regra: nenhum número inventado. Tudo o que aparece vem do backend; sem resposta, fica "—"
   e o motivo vai na dica do indicador. */

(function () {
  "use strict";

  const Moleka = {};
  const EM_BREVE = "Em construção: esta função entra numa próxima versão.";

  // ------------------------------------------------------------------ formatação
  Moleka.formatarCentavos = function (centavos) {
    if (centavos === null || centavos === undefined) return "—";
    const negativo = centavos < 0;
    const abs = Math.abs(centavos);
    const reais = Math.floor(abs / 100).toLocaleString("pt-BR");
    const cents = String(abs % 100).padStart(2, "0");
    return (negativo ? "-" : "") + "R$ " + reais + "," + cents;
  };

  Moleka.dataHojePorExtenso = function () {
    return new Date().toLocaleDateString("pt-BR", { weekday: "long", day: "2-digit", month: "2-digit", year: "numeric" });
  };

  Moleka.mesAno = function () {
    return new Date().toLocaleDateString("pt-BR", { month: "long", year: "numeric" });
  };

  // ------------------------------------------------------------------ aviso rápido ("torrada")
  let torrada = null;
  let torradaRelogio = 0;
  Moleka.avisar = function (texto) {
    if (!torrada) {
      torrada = document.createElement("div");
      torrada.className = "torrada";
      torrada.setAttribute("role", "status");
      document.body.appendChild(torrada);
    }
    torrada.textContent = texto;
    torrada.classList.add("visivel");
    clearTimeout(torradaRelogio);
    torradaRelogio = setTimeout(function () { torrada.classList.remove("visivel"); }, 3200);
  };

  // ------------------------------------------------------------------ indicadores (/api/status)
  /* Marcação: <span class="chip" data-status="fiscal" data-rotulo="SEFAZ"><span class="dot"></span><span class="texto"></span></span> */
  Moleka.status = null;
  Moleka.atualizarStatus = async function () {
    let status = null;
    try {
      const resposta = await fetch("/api/status", { cache: "no-store" });
      if (resposta.ok) status = await resposta.json();
    } catch (erro) {
      status = null;
    }
    Moleka.status = status;
    document.querySelectorAll("[data-status]").forEach(function (el) {
      const chave = el.dataset.status;
      const rotulo = el.dataset.rotulo || chave;
      const texto = el.querySelector(".texto") || el;
      const info = status ? status[chave] : null;
      el.classList.remove("ok", "erro");
      if (!info) {
        texto.textContent = rotulo + ": —";
        el.title = "sem resposta do servidor local";
        el.classList.add("erro");
      } else if (info.ok) {
        texto.textContent = rotulo + ": " + (info.texto || "ok");
        el.title = info.motivo || "";
        el.classList.add("ok");
      } else {
        texto.textContent = rotulo + ": —";
        el.title = info.motivo || "não disponível";
      }
    });
    document.querySelectorAll("[data-versao]").forEach(function (el) {
      el.textContent = status ? status.app + " v" + status.versao : "—";
    });
    preencherSobre(status);
    return status;
  };

  function preencherSobre(status) {
    const valores = {
      versao: status ? status.versao : "—",
      banco: status && status.banco.ok ? status.banco.motivo : "—",
      fiscal: status ? (status.fiscal.ok ? status.fiscal.texto : "— (" + status.fiscal.motivo + ")") : "—",
    };
    document.querySelectorAll("[data-sobre]").forEach(function (el) {
      el.textContent = valores[el.dataset.sobre] || "—";
    });
  }

  // ------------------------------------------------------------------ ações da janela
  function ponte() {
    return window.pywebview && window.pywebview.api ? window.pywebview.api : null;
  }

  const acoes = {
    sair: function () {
      const api = ponte();
      if (api && api.sair) api.sair();
      else Moleka.avisar("Para sair, feche esta janela.");
    },
    "tela-cheia": function () {
      const api = ponte();
      if (api && api.tela_cheia) api.tela_cheia();
      else Moleka.avisar("A tela cheia só funciona na janela do programa.");
    },
    sobre: function () {
      const dialogo = document.getElementById("sobre");
      if (dialogo && !dialogo.open) dialogo.showModal();
    },
  };

  // ------------------------------------------------------------------ menus do topo
  function fecharMenus(excecao) {
    document.querySelectorAll(".menu.aberto").forEach(function (menu) {
      if (menu === excecao) return;
      menu.classList.remove("aberto");
      menu.querySelector(".menu-botao").setAttribute("aria-expanded", "false");
    });
  }

  function iniciarMenus() {
    document.querySelectorAll(".menu").forEach(function (menu) {
      const botao = menu.querySelector(".menu-botao");
      botao.addEventListener("click", function (evento) {
        evento.stopPropagation();
        const abrir = !menu.classList.contains("aberto");
        fecharMenus(menu);
        menu.classList.toggle("aberto", abrir);
        botao.setAttribute("aria-expanded", abrir ? "true" : "false");
      });
      // Com um menu aberto, passar o mouse pelos vizinhos troca de menu, como nos programas de mesa.
      botao.addEventListener("mouseenter", function () {
        if (document.querySelector(".menu.aberto") && !menu.classList.contains("aberto")) botao.click();
      });
    });
    document.addEventListener("click", function () { fecharMenus(null); });
  }

  // ------------------------------------------------------------------ cliques: ações e "em breve"
  function iniciarCliques() {
    document.addEventListener("click", function (evento) {
      const comAcao = evento.target.closest("[data-acao]");
      if (comAcao && acoes[comAcao.dataset.acao]) {
        evento.preventDefault();
        fecharMenus(null);
        acoes[comAcao.dataset.acao]();
        return;
      }
      const emBreve = evento.target.closest("[data-em-breve]");
      if (emBreve && emBreve.tagName !== "FORM") { // nos formulários, o aviso sai ao enviar
        evento.preventDefault();
        fecharMenus(null);
        Moleka.avisar(emBreve.dataset.emBreve || EM_BREVE);
      }
    });
    // Formulários ainda sem função não recarregam a página ao apertar Enter.
    document.querySelectorAll("form[data-em-breve]").forEach(function (form) {
      form.addEventListener("submit", function (evento) { evento.preventDefault(); Moleka.avisar(form.dataset.emBreve || EM_BREVE); });
    });
  }

  // ------------------------------------------------------------------ teclas de atalho
  /* Qualquer elemento com data-atalho="F2" (ou "Enter", "Escape"...) é "clicado" pela tecla. */
  function iniciarAtalhos() {
    document.addEventListener("keydown", function (evento) {
      if (evento.ctrlKey || evento.altKey || evento.metaKey) return;
      const dialogo = document.querySelector("dialog[open]");
      if (dialogo) return; // a caixa aberta cuida das próprias teclas (Esc fecha)
      if (evento.key === "Escape" && document.querySelector(".menu.aberto")) {
        fecharMenus(null);
        evento.preventDefault();
        return;
      }
      const alvo = document.querySelector('[data-atalho="' + evento.key + '"]');
      if (!alvo) return;
      evento.preventDefault();
      if (alvo.matches("input, select, textarea")) {
        alvo.focus();
        if (alvo.select) alvo.select();
      } else {
        alvo.click();
      }
    });
  }

  // ------------------------------------------------------------------ capa: a arte se inclina com o mouse
  function iniciarCapa() {
    const vitrine = document.querySelector(".vitrine");
    const arte = document.querySelector(".arte");
    if (!vitrine || !arte || !document.body.classList.contains("anim")) return;
    vitrine.addEventListener("mousemove", function (evento) {
      const r = vitrine.getBoundingClientRect();
      const x = (evento.clientX - r.left) / r.width - 0.5;
      const y = (evento.clientY - r.top) / r.height - 0.5;
      arte.style.transform = "rotateX(" + (-y * 4).toFixed(1) + "deg) rotateY(" + (x * 5).toFixed(1) + "deg)";
    });
    vitrine.addEventListener("mouseleave", function () { arte.style.transform = "rotateX(0deg) rotateY(0deg)"; });
  }

  Moleka.iniciar = function () {
    document.querySelectorAll("[data-hoje]").forEach(function (el) { el.textContent = Moleka.dataHojePorExtenso(); });
    document.querySelectorAll("[data-mes-ano]").forEach(function (el) { el.textContent = Moleka.mesAno(); });
    iniciarMenus();
    iniciarCliques();
    iniciarAtalhos();
    iniciarCapa();
    Moleka.atualizarStatus();
    setInterval(Moleka.atualizarStatus, 30000);
  };

  window.Moleka = Moleka;
  document.addEventListener("DOMContentLoaded", Moleka.iniciar);
})();

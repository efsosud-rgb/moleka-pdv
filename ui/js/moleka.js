/* Moleka PDV — JS comum da interface.
   Regra: nenhum número inventado. Tudo que aparece vem do backend; sem resposta, fica "—" com o motivo. */

(function () {
  "use strict";

  const Moleka = {};

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

  /* Chips de status: <span class="chip" data-status="fiscal" data-rotulo="SEFAZ"><span class="dot"></span><span class="texto"></span></span> */
  Moleka.atualizarStatus = async function () {
    const chips = document.querySelectorAll("[data-status]");
    if (!chips.length) return null;
    let status = null;
    try {
      const resposta = await fetch("/api/status", { cache: "no-store" });
      if (resposta.ok) status = await resposta.json();
    } catch (erro) {
      status = null;
    }
    chips.forEach(function (chip) {
      const chave = chip.dataset.status;
      const rotulo = chip.dataset.rotulo || chave;
      const texto = chip.querySelector(".texto") || chip;
      const info = status ? status[chave] : null;
      chip.classList.remove("ok", "erro");
      if (!info) {
        texto.textContent = rotulo + ": —";
        chip.title = "sem resposta do servidor local";
        chip.classList.add("erro");
      } else if (info.ok) {
        texto.textContent = rotulo + ": " + (info.texto || "ok");
        chip.title = info.motivo || "";
        chip.classList.add("ok");
      } else {
        texto.textContent = rotulo + ": —";
        chip.title = info.motivo || "não disponível";
      }
    });
    document.querySelectorAll("[data-versao]").forEach(function (el) {
      el.textContent = status ? status.app + " v" + status.versao : "—";
    });
    return status;
  };

  Moleka.iniciar = function () {
    document.querySelectorAll("[data-hoje]").forEach(function (el) { el.textContent = Moleka.dataHojePorExtenso(); });
    Moleka.atualizarStatus();
    setInterval(Moleka.atualizarStatus, 30000);
  };

  window.Moleka = Moleka;
  document.addEventListener("DOMContentLoaded", Moleka.iniciar);
})();

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

  /* As datas e horas chegam do servidor já no horário da loja (ex.: "2026-11-11T13:17:25-03:00").
     A tela mostra os números desse texto, sem converter: assim a hora aparece certa mesmo que o
     relógio ou o fuso do Windows estejam errados. */
  function dataDoTexto(iso) {
    const p = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || "");
    return p ? new Date(Number(p[1]), Number(p[2]) - 1, Number(p[3])) : new Date();
  }

  Moleka.dataHojePorExtenso = function (iso) {
    return dataDoTexto(iso).toLocaleDateString("pt-BR", { weekday: "long", day: "2-digit", month: "2-digit", year: "numeric" });
  };

  Moleka.mesAno = function (iso) {
    return dataDoTexto(iso).toLocaleDateString("pt-BR", { month: "long", year: "numeric" });
  };

  /* "12,50" (sem o R$), para campos de digitação e colunas de tabela. */
  Moleka.reais = function (centavos) {
    if (centavos === null || centavos === undefined) return "—";
    return Moleka.formatarCentavos(centavos).replace("R$ ", "");
  };

  /* Lê um valor digitado ("12,5", "1.234,56", "12.50") e devolve centavos, ou null se não for valor. */
  Moleka.lerReais = function (texto) {
    let t = String(texto === null || texto === undefined ? "" : texto).replace(/[R$\s]/g, "");
    if (!t) return null;
    if (t.indexOf(",") >= 0) t = t.replace(/\./g, "").replace(",", ".");
    if (!/^-?\d+(\.\d{1,2})?$/.test(t)) return null;
    return Math.round(parseFloat(t) * 100);
  };

  /* Quantidade para mostrar: "3" ou "0,350". */
  Moleka.qtd = function (valor) {
    const n = Number(valor);
    if (!isFinite(n)) return "—";
    return Number.isInteger(n) ? String(n) : n.toFixed(3).replace(".", ",");
  };

  /* Percentual de uma forma de pagamento: -500 -> "-5%"; 300 -> "+3%"; 0 -> "". */
  Moleka.pct = function (bp) {
    if (!bp) return "";
    const texto = String(Math.abs(bp) / 100).replace(".", ",");
    return (bp < 0 ? "-" : "+") + texto + "%";
  };

  /* "13:17", a partir de "2026-11-11T13:17:25-03:00". */
  Moleka.hora = function (iso) {
    const p = /T(\d{2}:\d{2})/.exec(iso || "");
    return p ? p[1] : "—";
  };

  /* "11/11 13:17". */
  Moleka.dataHora = function (iso) {
    const p = /^\d{4}-(\d{2})-(\d{2})T(\d{2}:\d{2})/.exec(iso || "");
    return p ? p[2] + "/" + p[1] + " " + p[3] : "—";
  };

  /* Cria um elemento. Texto entra sempre como texto (nunca como HTML).
     Moleka.el("td", { class: "num", text: "12,50" }) ou Moleka.el("tr", null, td1, td2). */
  Moleka.el = function (tag, props) {
    const el = document.createElement(tag);
    Object.keys(props || {}).forEach(function (chave) {
      const valor = props[chave];
      if (valor === null || valor === undefined || valor === false) return;
      if (chave === "text") el.textContent = valor;
      else if (chave === "class") el.className = valor;
      else if (chave.indexOf("on") === 0) el.addEventListener(chave.slice(2), valor);
      else if (chave in el && chave !== "list") el[chave] = valor;
      else el.setAttribute(chave, valor === true ? "" : valor);
    });
    for (let i = 2; i < arguments.length; i++) {
      const filho = arguments[i];
      if (filho === null || filho === undefined || filho === false) continue;
      el.appendChild(typeof filho === "string" ? document.createTextNode(filho) : filho);
    }
    return el;
  };

  /* Troca todo o conteúdo de um elemento pelos filhos dados. */
  Moleka.trocar = function (el) {
    el.replaceChildren.apply(el, Array.prototype.slice.call(arguments, 1).filter(Boolean));
  };

  // ------------------------------------------------------------------ caixas de pergunta
  /* Pergunta de sim ou não. Devolve uma promessa com { ok, motivo }.
     opcoes: { titulo, texto, sim: "Cancelar a venda", perigo: true, motivo: "obrigatorio" | "opcional" } */
  Moleka.confirmar = function (opcoes) {
    const dialogo = document.getElementById("dlg-confirmar");
    return new Promise(function (resolver) {
      if (!dialogo) { resolver({ ok: false, motivo: "" }); return; }
      const form = dialogo.querySelector("form");
      const campo = form.motivo;
      dialogo.querySelector("h2").textContent = opcoes.titulo || "Confirmar";
      dialogo.querySelector("[data-texto]").textContent = opcoes.texto || "";
      dialogo.querySelector("[data-motivo]").hidden = !opcoes.motivo;
      dialogo.querySelector("[data-motivo] label").textContent = opcoes.motivo === "opcional" ? "Motivo (opcional)" : "Motivo";
      campo.value = "";
      const sim = form.querySelector('button[type="submit"]');
      sim.textContent = opcoes.sim || "Confirmar";
      sim.className = "btn3d " + (opcoes.perigo ? "vermelho" : "verde");
      Moleka.mensagem(form, "");
      function fechar(ok) {
        form.removeEventListener("submit", aoEnviar);
        dialogo.removeEventListener("close", aoFechar);
        if (dialogo.open) dialogo.close();
        resolver({ ok: ok, motivo: campo.value.trim() });
      }
      function aoEnviar(evento) {
        evento.preventDefault();
        if (opcoes.motivo === "obrigatorio" && !campo.value.trim()) { Moleka.mensagem(form, "Escreva o motivo."); campo.focus(); return; }
        fechar(true);
      }
      function aoFechar() { fechar(false); }
      form.addEventListener("submit", aoEnviar);
      dialogo.addEventListener("close", aoFechar);
      dialogo.showModal();
      (opcoes.motivo ? campo : sim).focus();
    });
  };

  /* Pede um valor digitado. Devolve uma promessa com o texto, ou null se a pessoa desistiu.
     opcoes: { titulo, texto, rotulo, valor: "12,50", confirmar: "Lançar" } */
  Moleka.perguntarValor = function (opcoes) {
    const dialogo = document.getElementById("dlg-valor");
    return new Promise(function (resolver) {
      if (!dialogo) { resolver(null); return; }
      const form = dialogo.querySelector("form");
      const campo = form.valor;
      dialogo.querySelector("h2").textContent = opcoes.titulo || "Valor";
      dialogo.querySelector("[data-texto]").textContent = opcoes.texto || "";
      dialogo.querySelector("[data-rotulo]").textContent = opcoes.rotulo || "Valor (R$)";
      form.querySelector('button[type="submit"]').textContent = opcoes.confirmar || "Confirmar (Enter)";
      campo.value = opcoes.valor || "";
      let resposta = null;
      function aoEnviar(evento) { evento.preventDefault(); resposta = campo.value.trim(); dialogo.close(); }
      function aoFechar() {
        form.removeEventListener("submit", aoEnviar);
        dialogo.removeEventListener("close", aoFechar);
        resolver(resposta);
      }
      form.addEventListener("submit", aoEnviar);
      dialogo.addEventListener("close", aoFechar);
      dialogo.showModal();
      campo.focus();
      campo.select();
    });
  };

  // ------------------------------------------------------------------ saldo de vendas do dia
  /* Preenche os elementos [data-resumo="total|quantidade|ticket"] com os números de hoje,
     vindos de /api/vendas/resumo-hoje. Sem venda, fica "—" e o motivo vai na dica. */
  Moleka.atualizarResumoDoDia = async function () {
    const alvos = document.querySelectorAll("[data-resumo]");
    if (!alvos.length) return null;
    const r = await Moleka.api("GET", "/api/vendas/resumo-hoje");
    const d = r.ok ? r.dados : null;
    const motivo = d ? d.motivo : "sem resposta do servidor local";
    const valores = {
      total: d && d.total_centavos !== null ? Moleka.formatarCentavos(d.total_centavos) : "—",
      quantidade: d ? String(d.quantidade) : "—", // zero vendas é um número de verdade
      ticket: d && d.ticket_medio_centavos !== null ? Moleka.formatarCentavos(d.ticket_medio_centavos) : "—",
    };
    alvos.forEach(function (el) {
      el.textContent = valores[el.dataset.resumo] || "—";
      el.title = motivo;
    });
    document.querySelectorAll("[data-resumo-palavra]").forEach(function (el) {
      el.textContent = d && d.quantidade === 1 ? "venda" : "vendas";
    });
    document.querySelectorAll("[data-resumo-motivo]").forEach(function (el) {
      el.textContent = motivo ? "Sem dados: " + motivo + "." : "";
      el.hidden = !motivo;
    });
    return d;
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

  // ------------------------------------------------------------------ pedidos à API
  /* Devolve { ok, status, dados, erro }. O "erro" já vem em português, pronto para mostrar.
     Se a sessão acabou (401) numa tela interna, volta para a capa. */
  Moleka.api = async function (metodo, caminho, corpo) {
    let resposta;
    try {
      resposta = await fetch(caminho, {
        method: metodo,
        cache: "no-store",
        headers: corpo === undefined ? {} : { "Content-Type": "application/json" },
        body: corpo === undefined ? undefined : JSON.stringify(corpo),
      });
    } catch (falha) {
      return { ok: false, status: 0, dados: null, erro: "Sem resposta do sistema. Feche o Moleka PDV e abra de novo." };
    }
    let dados = null;
    try {
      if (resposta.status === 204) await resposta.text(); // espera a resposta terminar antes de seguir
      else dados = await resposta.json();
    } catch (falha) {
      dados = null;
    }
    if (resposta.ok) return { ok: true, status: resposta.status, dados: dados, erro: "" };
    if (resposta.status === 401 && document.body.dataset.tela !== "capa") window.location.href = "/";
    let erro = dados && typeof dados.detail === "string" ? dados.detail : "";
    if (!erro) erro = resposta.status === 422 ? "Confira os campos e tente de novo." : "Não deu certo (erro " + resposta.status + ").";
    return { ok: false, status: resposta.status, dados: dados, erro: erro };
  };

  /* Linha de mensagem dos formulários: <p class="msg-form" role="alert" hidden>.
     tipo: "erro" (padrão), "ok" ou "dica". Texto vazio esconde a linha. */
  Moleka.mensagem = function (form, texto, tipo) {
    const linha = form.querySelector(".msg-form");
    if (!linha) return;
    linha.textContent = texto || "";
    linha.hidden = !texto;
    linha.dataset.tipo = texto ? (tipo || "erro") : "";
  };

  /* Nos campos de senha: avisa quando o Caps Lock está ligado (causa comum de "senha errada")
     e apaga a mensagem de erro quando a pessoa volta a digitar. */
  Moleka.cuidarDasSenhas = function (form) {
    const linha = form.querySelector(".msg-form");
    if (!linha) return;
    form.addEventListener("input", function () {
      if (linha.dataset.tipo === "erro") Moleka.mensagem(form, "");
    });
    form.querySelectorAll('input[type="password"]').forEach(function (campo) {
      campo.addEventListener("keyup", function (evento) {
        if (!evento.getModifierState) return;
        const ligado = evento.getModifierState("CapsLock");
        if (ligado && (linha.hidden || linha.dataset.tipo === "dica")) Moleka.mensagem(form, "A tecla Caps Lock está ligada.", "dica");
        else if (!ligado && linha.dataset.tipo === "dica") Moleka.mensagem(form, "");
      });
    });
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
        // "estado" vem quando o sistema sabe o que há (ex.: caixa fechado); sem ele, fica "—".
        texto.textContent = rotulo + ": " + (info.estado || "—");
        el.title = info.motivo || "não disponível";
      }
    });
    // Só o valor, sem o rótulo: <b data-status-valor="caixa">—</b>
    document.querySelectorAll("[data-status-valor]").forEach(function (el) {
      const info = status ? status[el.dataset.statusValor] : null;
      el.textContent = info ? (info.ok ? info.texto || "ok" : info.estado || "—") : "—";
      el.title = info ? info.motivo || "" : "sem resposta do servidor local";
    });
    document.querySelectorAll("[data-versao]").forEach(function (el) {
      el.textContent = status ? status.app + " v" + status.versao : "—";
    });
    if (status && status.agora) { // a data do topo é a da loja, dita pelo servidor
      document.querySelectorAll("[data-hoje]").forEach(function (el) { el.textContent = Moleka.dataHojePorExtenso(status.agora); });
      document.querySelectorAll("[data-mes-ano]").forEach(function (el) { el.textContent = Moleka.mesAno(status.agora); });
    }
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
    "trocar-operador": async function () {
      await Moleka.api("POST", "/api/sair");
      window.location.href = "/";
    },
    "minha-senha": function () {
      const dialogo = document.getElementById("minha-senha");
      if (!dialogo || dialogo.open) return;
      const form = dialogo.querySelector("form");
      form.reset();
      Moleka.mensagem(form, "");
      dialogo.showModal();
      form.senha_atual.focus();
    },
  };

  // ------------------------------------------------------------------ caixa "Minha senha"
  function iniciarMinhaSenha() {
    const form = document.getElementById("form-minha-senha");
    if (!form) return;
    Moleka.cuidarDasSenhas(form);
    form.addEventListener("submit", async function (evento) {
      evento.preventDefault();
      const atual = form.senha_atual.value;
      const nova = form.senha_nova.value;
      if (!atual || !nova) { Moleka.mensagem(form, "Preencha a senha atual e a senha nova."); return; }
      if (nova !== form.senha_nova2.value) { Moleka.mensagem(form, "A senha nova e a repetição estão diferentes."); return; }
      const r = await Moleka.api("POST", "/api/minha-senha", { senha_atual: atual, senha_nova: nova });
      if (!r.ok) { Moleka.mensagem(form, r.erro); return; }
      form.closest("dialog").close();
      Moleka.avisar("Senha trocada.");
    });
  }

  /* Avisos que chegam pelo endereço da página (ex.: /inicio?aviso=gerente). */
  function avisoDoEndereco() {
    const aviso = new URLSearchParams(window.location.search).get("aviso");
    if (!aviso) return;
    if (aviso === "gerente") Moleka.avisar("Essa tela é só para o gerente.");
    window.history.replaceState(null, "", window.location.pathname);
  }

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
      const fechar = evento.target.closest("[data-fechar-dialogo]");
      if (fechar) {
        evento.preventDefault();
        const dialogo = fechar.closest("dialog");
        if (dialogo) dialogo.close();
        return;
      }
      const comAviso = evento.target.closest("[data-aviso]");
      if (comAviso) { // ex.: tela trancada para o operador comum
        evento.preventDefault();
        fecharMenus(null);
        Moleka.avisar(comAviso.dataset.aviso);
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
  /* Qualquer elemento visível com data-atalho="F2" (ou "Enter", "Escape"...) é "clicado" pela
     tecla. Se a tela não usa a tecla, valem as teclas dos menus do topo (F2 Venda, F5 Produtos,
     F11 Controle de caixa). */
  function visivel(el) { return el.getClientRects().length > 0; }

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
      // Na capa, Esc fecha o programa. Com um campo em uso, o primeiro Esc só limpa e solta
      // o campo, para ninguém fechar o sistema sem querer no meio da senha.
      const foco = document.activeElement;
      if (evento.key === "Escape" && document.body.dataset.tela === "capa" && foco && foco.matches("input, select")) {
        if (foco.matches("input")) foco.value = "";
        foco.blur();
        evento.preventDefault();
        return;
      }
      // Fora da capa, o primeiro Esc num campo preenchido só limpa o campo (não sai da tela).
      if (evento.key === "Escape" && foco && foco.value && foco.matches('input:not([type="checkbox"]):not([type="radio"]), textarea')) {
        foco.value = "";
        foco.dispatchEvent(new Event("input", { bubbles: true }));
        evento.preventDefault();
        return;
      }
      const seletor = '[data-atalho="' + evento.key + '"]';
      const alvo = Array.prototype.find.call(document.querySelectorAll(seletor), visivel);
      if (!alvo) {
        const doMenu = document.querySelector('a[data-atalho-menu="' + evento.key + '"]');
        if (doMenu) { evento.preventDefault(); window.location.href = doMenu.getAttribute("href"); }
        return;
      }
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
    iniciarMinhaSenha();
    avisoDoEndereco();
    Moleka.atualizarStatus();
    Moleka.atualizarResumoDoDia();
    setInterval(Moleka.atualizarStatus, 30000);
  };

  window.Moleka = Moleka;
  document.addEventListener("DOMContentLoaded", Moleka.iniciar);
})();

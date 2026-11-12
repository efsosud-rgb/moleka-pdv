/* Configurações (só o gerente): dados da loja, impressora de cupom e cópia de segurança.
   Tudo o que aparece vem de /api/configuracoes; nada é preenchido com valor de exemplo.
   A aba Fiscal (NFC-e) tem o próprio arquivo: fiscal.js. */
(function () {
  "use strict";
  const M = window.Moleka;
  const raiz = document.getElementById("configuracoes");
  if (!raiz) return;

  const ABAS = ["loja", "impressao", "backup", "fiscal"];
  const formLoja = document.getElementById("form-loja");
  const formImpressao = document.getElementById("form-impressao");
  const formBackup = document.getElementById("form-backup");
  const selImpressora = document.getElementById("im-impressora");
  const motivoImpressoras = raiz.querySelector("[data-im-motivo]");
  const situacaoImpressao = raiz.querySelector("[data-im-situacao]");
  const conferir = raiz.querySelector("[data-im-conferir]");
  const enviado = raiz.querySelector("[data-im-enviado]");
  const corpoCopias = raiz.querySelector("#tabela-copias tbody");
  let aba = "loja";
  let impressao = null; // as opções gravadas (com "confirmada")
  let podeImprimir = false;

  function opcao(valor, texto) { return M.el("option", { value: String(valor), text: texto }); }

  function mostrarAba(nome, semMexerNoEndereco) {
    // "#fiscal-certificado" abre a aba Fiscal (a parte, fiscal.js escolhe).
    const base = String(nome || "").split("-")[0];
    aba = ABAS.indexOf(base) >= 0 ? base : "loja";
    raiz.querySelectorAll("[data-aba]").forEach(function (b) {
      const ativa = b.dataset.aba === aba;
      b.classList.toggle("ativa", ativa);
      b.setAttribute("aria-selected", ativa ? "true" : "false");
    });
    raiz.querySelectorAll("[data-painel]").forEach(function (p) { p.hidden = p.dataset.painel !== aba; });
    if (!semMexerNoEndereco) window.history.replaceState(null, "", "#" + aba);
    if (aba === "fiscal" && window.MolekaFiscal) window.MolekaFiscal.mostrar();
  }

  // ------------------------------------------------------------------ dados da loja
  function mascaraDoCnpj(texto) {
    const d = texto.replace(/[^0-9A-Za-z]/g, "").toUpperCase().slice(0, 14);
    if (d.length !== 14) return texto;
    return d.slice(0, 2) + "." + d.slice(2, 5) + "." + d.slice(5, 8) + "/" + d.slice(8, 12) + "-" + d.slice(12);
  }

  function mascaraDoCep(texto) {
    const d = texto.replace(/\D/g, "").slice(0, 8);
    return d.length === 8 ? d.slice(0, 5) + "-" + d.slice(5) : texto;
  }

  function preencherLoja(loja) {
    Object.keys(loja).forEach(function (campo) { if (formLoja[campo]) formLoja[campo].value = loja[campo]; });
    formLoja.cnpj.value = mascaraDoCnpj(loja.cnpj);
    formLoja.cep.value = mascaraDoCep(loja.cep);
  }

  formLoja.cnpj.addEventListener("blur", function () { formLoja.cnpj.value = mascaraDoCnpj(formLoja.cnpj.value); });
  formLoja.cep.addEventListener("blur", function () { formLoja.cep.value = mascaraDoCep(formLoja.cep.value); });

  formLoja.addEventListener("submit", async function (evento) {
    evento.preventDefault();
    const dados = {};
    ["nome_fantasia", "razao_social", "cnpj", "ie", "logradouro", "numero", "bairro", "cidade", "uf", "cep", "telefone", "rodape"]
      .forEach(function (campo) { dados[campo] = formLoja[campo].value.trim(); });
    const r = await M.api("PUT", "/api/configuracoes/loja", dados);
    if (!r.ok) { M.mensagem(formLoja, r.erro); return; }
    M.mensagem(formLoja, "");
    preencherLoja(r.dados);
    M.avisar("Dados da loja salvos.");
  });

  // ------------------------------------------------------------------ impressão
  function desenharImpressoras(lista, escolhida) {
    podeImprimir = lista.disponivel;
    const opcoes = [opcao("", "— nenhuma —")].concat(lista.impressoras.map(function (i) {
      return opcao(i.nome, i.nome + (i.padrao ? " (padrão do Windows)" : ""));
    }));
    // A impressora gravada que não está mais na lista continua aparecendo, marcada.
    const nomes = lista.impressoras.map(function (i) { return i.nome; });
    if (escolhida && nomes.indexOf(escolhida) < 0) opcoes.push(opcao(escolhida, escolhida + " (não encontrada no Windows)"));
    M.trocar.apply(null, [selImpressora].concat(opcoes));
    selImpressora.value = escolhida || "";
    selImpressora.disabled = !lista.disponivel;
    motivoImpressoras.textContent = lista.motivo;
    motivoImpressoras.hidden = !lista.motivo;
  }

  function desenharSituacao() {
    if (!impressao) return;
    let texto;
    if (!impressao.impressora) texto = "Nenhuma impressora de cupom escolhida: o sistema não imprime comprovante.";
    else if (impressao.confirmada) texto = "Impressora testada: o teste em “" + impressao.impressora + "” foi confirmado.";
    else texto = "“" + impressao.impressora + "” está escolhida, mas ainda NÃO foi testada. Clique em “Imprimir teste” e confira o papel.";
    situacaoImpressao.textContent = texto;
  }

  function preencherImpressao(dados) {
    impressao = dados;
    formImpressao.colunas.value = String(dados.colunas);
    formImpressao.acentos.value = dados.acentos;
    formImpressao.vias.value = String(dados.vias);
    formImpressao.quando.value = dados.quando;
    formImpressao.cortar.checked = dados.cortar;
    formImpressao.gaveta.checked = dados.gaveta;
    selImpressora.value = dados.impressora;
    desenharSituacao();
  }

  function opcoesDaTela() {
    return {
      impressora: selImpressora.value,
      colunas: Number(formImpressao.colunas.value),
      acentos: formImpressao.acentos.value,
      vias: Number(formImpressao.vias.value),
      quando: formImpressao.quando.value,
      cortar: formImpressao.cortar.checked,
      gaveta: formImpressao.gaveta.checked,
    };
  }

  async function salvarImpressao() {
    const r = await M.api("PUT", "/api/configuracoes/impressao", opcoesDaTela());
    if (!r.ok) { M.mensagem(formImpressao, r.erro); return false; }
    M.mensagem(formImpressao, "");
    preencherImpressao(r.dados);
    M.atualizarStatus();
    return true;
  }

  formImpressao.addEventListener("submit", async function (evento) {
    evento.preventDefault();
    if (await salvarImpressao()) { conferir.hidden = true; M.avisar("Opções de impressão salvas."); }
  });

  document.getElementById("btn-atualizar-impressoras").addEventListener("click", async function () {
    const r = await M.api("GET", "/api/impressoras");
    if (!r.ok) { M.mensagem(formImpressao, r.erro); return; }
    desenharImpressoras(r.dados, selImpressora.value);
    M.avisar(r.dados.impressoras.length === 1 ? "1 impressora encontrada no Windows." : r.dados.impressoras.length + " impressoras encontradas no Windows.");
  });

  document.getElementById("btn-teste").addEventListener("click", async function () {
    conferir.hidden = true;
    if (!selImpressora.value) { M.mensagem(formImpressao, podeImprimir ? "Escolha a impressora antes de testar." : motivoImpressoras.textContent); return; }
    // O teste usa o que está na tela: primeiro grava, depois imprime.
    if (!(await salvarImpressao())) return;
    const r = await M.api("POST", "/api/impressao/teste");
    if (!r.ok) { M.mensagem(formImpressao, r.erro); return; }
    M.trocar.apply(null, [enviado].concat(r.dados.linhas.map(function (texto) { return M.el("span", { class: "l", text: texto }); })));
    conferir.hidden = false;
    M.avisar("Teste enviado para “" + r.dados.impressora + "”. Confira o papel.");
  });

  conferir.querySelectorAll("[data-saiu]").forEach(function (botao) {
    botao.addEventListener("click", async function () {
      const saiu = botao.dataset.saiu === "sim";
      const r = await M.api("POST", "/api/impressao/teste/confirmar", { saiu: saiu });
      if (!r.ok) { M.mensagem(formImpressao, r.erro); return; }
      preencherImpressao(r.dados);
      conferir.hidden = true;
      M.atualizarStatus();
      if (saiu) M.avisar("Impressora de cupom confirmada.");
      else M.mensagem(formImpressao, "O teste não saiu certo. Confira se a impressora está ligada e com papel; se os acentos saíram trocados, mude “Letras com acento”; se a linha de números quebrou, diminua a largura. Depois teste de novo.", "dica");
    });
  });

  // ------------------------------------------------------------------ cópia de segurança
  function tamanho(bytes) {
    if (bytes < 1024 * 1024) return Math.max(1, Math.round(bytes / 1024)) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1).replace(".", ",") + " MB";
  }

  function desenharBackup(b) {
    formBackup.pasta_extra.value = b.pasta_extra;
    formBackup.manter.value = String(b.manter);
    raiz.querySelector("[data-bk-pasta]").textContent = b.pasta;
    const situacao = raiz.querySelector("[data-bk-situacao]");
    if (!b.copias.length) situacao.textContent = "Sem dados: nenhuma cópia de segurança foi feita ainda.";
    else if (!b.pasta_extra) situacao.textContent = "As cópias estão só neste computador. Escolha uma pasta extra.";
    else if (b.extra_erro) situacao.textContent = "A cópia na pasta extra FALHOU: " + b.extra_erro + ".";
    else if (b.extra_em) situacao.textContent = "A pasta extra recebeu a cópia em " + M.dataHora(b.extra_em) + ".";
    else situacao.textContent = "A pasta extra ainda não recebeu nenhuma cópia: clique em “Fazer a cópia agora”.";
    if (!b.copias.length) {
      M.trocar(corpoCopias, M.el("tr", null, M.el("td", { class: "sem-linhas", colSpan: 3, text: "Nenhuma cópia ainda." })));
      return;
    }
    M.trocar.apply(null, [corpoCopias].concat(b.copias.map(function (c) {
      return M.el("tr", null,
        M.el("td", { text: M.dataBR(c.dia) }),
        M.el("td", { text: M.hora(c.feita_em) }),
        M.el("td", { class: "num", text: tamanho(c.tamanho) }));
    })));
  }

  function opcoesDeBackup() {
    const manter = Number(formBackup.manter.value.trim());
    if (!Number.isInteger(manter)) { M.mensagem(formBackup, "Cópias guardadas: digite um número de 7 a 365."); formBackup.manter.focus(); return null; }
    return { pasta_extra: formBackup.pasta_extra.value.trim(), manter: manter };
  }

  async function salvarBackup() {
    const dados = opcoesDeBackup();
    if (!dados) return false;
    const r = await M.api("PUT", "/api/configuracoes/backup", dados);
    if (!r.ok) { M.mensagem(formBackup, r.erro); return false; }
    M.mensagem(formBackup, "");
    desenharBackup(r.dados);
    M.atualizarStatus();
    return true;
  }

  formBackup.addEventListener("submit", async function (evento) {
    evento.preventDefault();
    if (await salvarBackup()) M.avisar("Opções da cópia de segurança salvas.");
  });

  document.getElementById("btn-copiar").addEventListener("click", async function () {
    // A cópia usa a pasta que está na tela: primeiro grava as opções.
    if (!(await salvarBackup())) return;
    const r = await M.api("POST", "/api/backup");
    if (!r.ok) { M.mensagem(formBackup, r.erro); return; }
    desenharBackup(r.dados.backup);
    M.atualizarStatus();
    if (r.dados.extra_erro) M.mensagem(formBackup, "A cópia deste computador foi feita, mas a da pasta extra falhou: " + r.dados.extra_erro + ".");
    else M.avisar(r.dados.extra_pasta ? "Cópia feita neste computador e na pasta extra." : "Cópia feita neste computador.");
  });

  // "Escolher a pasta…" só existe dentro da janela do programa (no navegador, digita-se o caminho).
  const botaoPasta = document.getElementById("btn-escolher-pasta");
  function ponte() { return window.pywebview && window.pywebview.api ? window.pywebview.api : null; }
  function mostrarBotaoDaPasta() { botaoPasta.hidden = !(ponte() && ponte().escolher_pasta); }
  window.addEventListener("pywebviewready", mostrarBotaoDaPasta);
  mostrarBotaoDaPasta();
  botaoPasta.addEventListener("click", async function () {
    const api = ponte();
    if (!api || !api.escolher_pasta) return;
    let escolhida = "";
    try { escolhida = await api.escolher_pasta(); }
    catch (falha) { M.mensagem(formBackup, "Não foi possível abrir a janela de escolher pasta. Digite o caminho da pasta no campo."); return; }
    if (escolhida) { formBackup.pasta_extra.value = escolhida; M.mensagem(formBackup, "Pasta escolhida. Clique em Salvar para gravar.", "dica"); }
  });

  // ------------------------------------------------------------------ geral
  raiz.querySelectorAll("[data-aba]").forEach(function (b) {
    b.addEventListener("click", function () { mostrarAba(b.dataset.aba); });
  });
  window.addEventListener("hashchange", function () { mostrarAba(window.location.hash.slice(1), true); });
  const teclaSalvar = document.querySelector("[data-salvar]");
  if (teclaSalvar) teclaSalvar.addEventListener("click", function () {
    if (aba === "fiscal") { if (window.MolekaFiscal) window.MolekaFiscal.salvar(); return; }
    const form = { loja: formLoja, impressao: formImpressao, backup: formBackup }[aba];
    form.requestSubmit();
  });

  (async function iniciar() {
    mostrarAba(window.location.hash.slice(1), true);
    const r = await M.api("GET", "/api/configuracoes");
    if (!r.ok) { M.mensagem(formLoja, "Não foi possível carregar as configurações: " + r.erro); return; }
    const c = r.dados;
    M.trocar.apply(null, [formLoja.uf, opcao("", "—")].concat(c.ufs.map(function (uf) { return opcao(uf, uf); })));
    M.trocar.apply(null, [formImpressao.acentos].concat(c.acentos.map(function (o) { return opcao(o.valor, o.rotulo); })));
    M.trocar.apply(null, [formImpressao.quando].concat(c.quando.map(function (o) { return opcao(o.valor, o.rotulo); })));
    preencherLoja(c.loja);
    const lista = await M.api("GET", "/api/impressoras");
    desenharImpressoras(lista.ok ? lista.dados : { disponivel: false, motivo: lista.erro, impressoras: [] }, c.impressao.impressora);
    preencherImpressao(c.impressao);
    desenharBackup(c.backup);
  })();
})();

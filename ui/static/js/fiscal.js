/* Configurações → Fiscal (NFC-e). O dono deixa prontos os dados da nota: empresa, certificado
   digital A1, CSC, numeração, dados fiscais dos produtos e o contato do contador.
   Tudo o que aparece vem de /api/fiscal; nada é preenchido com valor de exemplo.
   Esta versão ainda não emite NFC-e. A senha do certificado e o código do CSC vão para o
   servidor local e nunca voltam: a tela só mostra os 4 últimos caracteres do CSC. */
(function () {
  "use strict";
  const M = window.Moleka;
  const painel = document.querySelector('[data-painel="fiscal"]');
  if (!painel) return;

  const PASSOS = ["empresa", "certificado", "csc", "numeracao", "produtos", "contador"];
  // Em que parte da tela se resolve cada item da lista "o que falta" (a "loja" é outra aba).
  const PARTE_DO_ITEM = { loja: "empresa" };
  const PESO = { ok: 0, atencao: 1, falta: 2 };
  const LIMITE_DO_ARQUIVO = 200 * 1024;
  const forms = {
    empresa: document.getElementById("form-fs-empresa"),
    certificado: document.getElementById("form-fs-certificado"),
    csc: document.getElementById("form-fs-csc"),
    numeracao: document.getElementById("form-fs-numeracao"),
    contador: document.getElementById("form-fs-contador"),
  };
  const dialogo = document.getElementById("dlg-fs-categoria");
  const formCategoria = dialogo.querySelector("form");
  let estado = null;
  let passo = "empresa";
  let opcoesProntas = false;
  let categoriaAberta = null;

  function q(seletor) { return painel.querySelector(seletor); }
  function opcao(valor, texto) { return M.el("option", { value: valor, text: texto }); }
  function icone(situacao) {
    const modelo = document.getElementById("ic-fs-" + situacao);
    return modelo ? modelo.content.firstElementChild.cloneNode(true) : M.el("span");
  }
  function documento(d) {
    if (!d) return "—";
    if (d.length === 14) return d.slice(0, 2) + "." + d.slice(2, 5) + "." + d.slice(5, 8) + "/" + d.slice(8, 12) + "-" + d.slice(12);
    if (d.length === 11) return d.slice(0, 3) + "." + d.slice(3, 6) + "." + d.slice(6, 9) + "-" + d.slice(9);
    return d;
  }
  function plural(n, um, varios) { return n + " " + (n === 1 ? um : varios); }

  // ------------------------------------------------------------------ partes da tela
  function mostrarPasso(nome, semMexerNoEndereco) {
    passo = PASSOS.indexOf(nome) >= 0 ? nome : "empresa";
    painel.querySelectorAll("[data-passo]").forEach(function (b) {
      const ativo = b.dataset.passo === passo;
      b.classList.toggle("ativo", ativo);
      if (ativo) b.setAttribute("aria-current", "step"); else b.removeAttribute("aria-current");
    });
    painel.querySelectorAll("[data-secao]").forEach(function (s) { s.hidden = s.dataset.secao !== passo; });
    if (!semMexerNoEndereco) window.history.replaceState(null, "", "#fiscal-" + passo);
  }

  function parteDoEndereco() {
    const h = window.location.hash.slice(1);
    return h.indexOf("fiscal-") === 0 ? h.slice(7) : passo;
  }

  painel.querySelectorAll("[data-passo]").forEach(function (b) {
    b.addEventListener("click", function () { mostrarPasso(b.dataset.passo); });
  });

  // ------------------------------------------------------------------ desenho
  function desenharOpcoes(f) {
    if (opcoesProntas) return;
    opcoesProntas = true;
    const crt = forms.empresa.crt;
    M.trocar.apply(null, [crt, opcao("", "— escolha —")].concat(f.crts.map(function (o) { return opcao(o.valor, o.rotulo); })));
    [forms.empresa.credenciada, forms.empresa.emite_hoje].forEach(function (sel) {
      M.trocar.apply(null, [sel, opcao("", "—")].concat(f.respostas.map(function (o) { return opcao(o.valor, o.rotulo); })));
    });
    M.trocar.apply(null, [formCategoria.origem, opcao("", "não mexer")].concat(f.origens.map(function (o) { return opcao(o.valor, o.rotulo); })));
    M.trocar.apply(null, [document.getElementById("lista-fs-cfop")].concat(f.cfops.map(function (o) { return M.el("option", { value: o.valor, label: o.rotulo }); })));
  }

  function desenharLoja(loja) {
    const endereco = [loja.logradouro, loja.numero, loja.bairro].filter(Boolean).join(", ");
    const cidade = [loja.cidade, loja.uf].filter(Boolean).join("/");
    const linha1 = [loja.razao_social || "Razão social: —", "CNPJ " + documento(loja.cnpj), "IE " + (loja.ie || "—")];
    const linha2 = [[endereco, cidade].filter(Boolean).join(", ") || "Endereço: —"];
    if (loja.cep) linha2.push("CEP " + loja.cep.slice(0, 5) + "-" + loja.cep.slice(5));
    M.trocar(q("[data-fs-loja]"), linha1.join(" · "), M.el("br"), linha2.join(" · "));
  }

  function desenharEmpresa(e) {
    Object.keys(e).forEach(function (campo) { if (forms.empresa[campo]) forms.empresa[campo].value = e[campo]; });
    if (e.cnae && e.cnae.length === 7) forms.empresa.cnae.value = e.cnae.slice(0, 4) + "-" + e.cnae.slice(4, 5) + "/" + e.cnae.slice(5);
    mostrarDetalhe();
  }

  function mostrarDetalhe() {
    q("[data-fs-detalhe]").hidden = forms.empresa.emite_hoje.value !== "sim";
  }
  forms.empresa.emite_hoje.addEventListener("change", mostrarDetalhe);

  function linhaDoCertificado(rotulo, valor) {
    return [M.el("dt", { text: rotulo }), M.el("dd", null, valor)];
  }

  function desenharCertificado(c) {
    const area = q("[data-fs-cert]");
    q("[data-fs-cert-titulo]").textContent = c ? "Trocar o certificado (renovação)" : "Instalar o certificado";
    q("[data-fs-cert-botao]").textContent = c ? "Trocar o certificado" : "Instalar o certificado";
    // Com um certificado instalado, o formulário de troca fica recolhido.
    q("[data-fs-trocar]").open = !c;
    if (!c) {
      M.trocar(area, M.el("p", { class: "vazio", text: "Nenhum certificado instalado neste computador." }));
      return;
    }
    let validade = "de " + M.dataBR(c.inicio) + " até " + M.dataBR(c.fim);
    if (c.vencido) validade += " (VENCIDO)";
    else validade += c.dias_restantes === 0 ? " (vence hoje)" : " (" + plural(c.dias_restantes, "dia", "dias") + " para vencer)";
    let cnpj = M.el("span", { text: documento(c.cnpj) });
    if (c.cnpj_confere === true) cnpj = M.el("span", null, documento(c.cnpj) + " ", M.el("span", { class: "tag ativo", text: "é o da loja" }));
    if (c.cnpj_confere === false) cnpj = M.el("span", null, documento(c.cnpj) + " ", M.el("span", { class: "tag perigo", text: "não é o CNPJ da loja" }));
    const lista = M.el("dl", { class: "dados-cert" });
    [
      linhaDoCertificado("Titular", c.titular || "—"),
      linhaDoCertificado("CNPJ", cnpj),
      linhaDoCertificado("Emitido por", c.emissor || "—"),
      linhaDoCertificado("Validade", validade),
      linhaDoCertificado("Instalado", M.dataBR(c.instalado_em) + " às " + M.hora(c.instalado_em) + ", do arquivo " + (c.arquivo || "—")),
    ].forEach(function (par) { lista.appendChild(par[0]); lista.appendChild(par[1]); });
    const avisos = [];
    if (!c.tem_arquivo) avisos.push("O arquivo do certificado sumiu deste computador: instale de novo.");
    if (!c.tem_senha) avisos.push("A senha do certificado não está guardada: instale de novo.");
    const botoes = M.el("div", { class: "botoes-lado" },
      M.el("button", { class: "btn3d mini", type: "button", "data-fs-testar": "", text: "Testar o certificado" }),
      M.el("button", { class: "btn3d mini", type: "button", "data-fs-remover": "", text: "Remover deste computador" }));
    M.trocar(area, lista, avisos.length ? M.el("p", { class: "msg-form", text: avisos.join(" ") }) : null, botoes);
  }

  function desenharCsc(lista) {
    lista.forEach(function (c) {
      const situacao = q('[data-csc-situacao="' + c.ambiente + '"]');
      situacao.textContent = c.salvo
        ? "Código guardado" + (c.final ? " (termina em " + c.final + ")" : "") + ". Para trocar, digite o novo."
        : "Nenhum código guardado.";
      q('[data-csc-apagar="' + c.ambiente + '"]').hidden = !c.salvo;
      forms.csc["id_" + c.ambiente].value = c.id;
      forms.csc["codigo_" + c.ambiente].value = "";
      forms.csc["apagar_" + c.ambiente].checked = false;
    });
  }

  function desenharNumeracao(f) {
    const corpo = document.querySelector("#tabela-fs-numeracao tbody");
    if (!f.numeracao.length) {
      M.trocar(corpo, M.el("tr", null, M.el("td", { class: "sem-linhas", colSpan: 4, text: "Nenhum caixa cadastrado." })));
    } else {
      M.trocar.apply(null, [corpo].concat(f.numeracao.map(function (n) {
        return M.el("tr", { "data-caixa": String(n.caixa_id) },
          M.el("td", { text: n.caixa }),
          M.el("td", null, M.el("input", { class: "campo num", type: "text", inputmode: "numeric", maxLength: 3, value: String(n.serie), name: "serie", "aria-label": "Série do " + n.caixa })),
          M.el("td", null, M.el("input", { class: "campo num", type: "text", inputmode: "numeric", maxLength: 9, value: String(n.proximo_numero), name: "proximo", "aria-label": "Próxima nota do " + n.caixa })),
          M.el("td", { text: n.ultima_registrada === null ? "— (nenhuma NFC-e registrada por este sistema)" : "nº " + n.ultima_registrada }));
      })));
    }
  }

  function desenharOutroSistema(e) {
    const outro = q("[data-fs-outro-sistema]");
    outro.hidden = e.emite_hoje !== "sim";
    outro.textContent = "Na parte Empresa, está anotado que a loja já emite NFC-e por outro sistema" + (e.emite_hoje_detalhe ? ": " + e.emite_hoje_detalhe + "." : ".");
  }

  function desenharCategorias(f) {
    const regime = q("[data-fs-regime]");
    const crt = f.empresa.crt;
    if (!crt) regime.textContent = "Escolha o regime tributário na parte Empresa: assim o sistema confere se cada produto está com CST ou CSOSN.";
    else if (crt === "4") regime.textContent = "Regime: MEI. Na NFC-e, o MEI usa CSOSN 102 ou 300.";
    else if (crt === "1") regime.textContent = "Regime: Simples Nacional. Use CSOSN, de 3 números (por exemplo, 102 ou 500).";
    else regime.textContent = "Regime: " + (crt === "2" ? "Simples acima do sublimite" : "normal") + ". Use CST, de 2 números (por exemplo, 00 ou 60).";
    const corpo = document.querySelector("#tabela-fs-categorias tbody");
    if (!f.categorias.length) {
      M.trocar(corpo, M.el("tr", null, M.el("td", { class: "sem-linhas", colSpan: 7, text: "Nenhum produto ativo cadastrado. Cadastre em Cadastros → Produtos." })));
      return;
    }
    M.trocar.apply(null, [corpo].concat(f.categorias.map(function (c) {
      let situacao;
      if (!c.completa) situacao = M.el("span", { class: "tag perigo", text: "falta" });
      else if (c.fora_do_regime || c.cfop_fora_da_lista) situacao = M.el("span", { class: "tag alerta", text: "confira", title: [c.fora_do_regime ? plural(c.fora_do_regime, "produto com CST/CSOSN que não combina com o regime", "produtos com CST/CSOSN que não combina com o regime") : "", c.cfop_fora_da_lista ? plural(c.cfop_fora_da_lista, "produto com CFOP fora da lista da NFC-e", "produtos com CFOP fora da lista da NFC-e") : ""].filter(Boolean).join("; ") });
      else situacao = M.el("span", { class: "tag ativo", text: "completa" });
      const numero = function (n) { return M.el("td", { class: "num" + (n ? " falta" : ""), text: String(n) }); };
      return M.el("tr", null,
        M.el("td", { text: c.nome || "(sem categoria)" }),
        M.el("td", { class: "num", text: String(c.produtos) }),
        numero(c.sem_ncm), numero(c.sem_cfop), numero(c.sem_cst_csosn),
        M.el("td", null, situacao),
        M.el("td", null, M.el("button", { class: "btn3d mini", type: "button", text: "Preencher…", onclick: function () { abrirCategoria(c); } })));
    })));
  }

  function desenharContador(c) {
    Object.keys(c).forEach(function (campo) { if (forms.contador[campo]) forms.contador[campo].value = c[campo]; });
    forms.contador.documento.value = c.documento ? documento(c.documento) : "";
  }

  function desenharPendencias(f) {
    const atencao = f.pendencias.filter(function (p) { return p.situacao === "atencao"; }).length;
    let resumo;
    if (f.faltam) resumo = plural(f.faltam, "item falta", "itens faltam") + " (em vermelho)" + (atencao ? "; " + plural(atencao, "pede", "pedem") + " atenção (em amarelo)." : ".");
    else if (atencao) resumo = "Nada falta, mas " + plural(atencao, "item pede", "itens pedem") + " atenção (em amarelo).";
    else resumo = "Os dados estão prontos. A emissão da NFC-e entra numa próxima versão.";
    q("[data-fs-resumo]").textContent = resumo;
    M.trocar.apply(null, [q("[data-fs-pendencias]")].concat(f.pendencias.map(function (p) {
      return M.el("li", { class: "pend " + p.situacao, "data-chave": p.chave },
        M.el("button", { type: "button", title: p.onde === "loja" ? "Abrir a aba Dados da loja" : "Abrir esta parte", onclick: function () {
          if (p.onde === "loja") window.location.hash = "#loja";
          else mostrarPasso(PARTE_DO_ITEM[p.onde] || p.onde);
        } },
        icone(p.situacao),
        M.el("span", { class: "t", text: p.titulo }),
        M.el("span", { class: "d", text: p.detalhe })));
    })));
    // A bolinha de cada parte: vermelha se algo falta, amarela se algo pede atenção.
    const pior = {};
    f.pendencias.forEach(function (p) {
      const parte = PARTE_DO_ITEM[p.onde] || p.onde;
      if (pior[parte] === undefined || PESO[p.situacao] > PESO[pior[parte]]) pior[parte] = p.situacao;
    });
    painel.querySelectorAll("[data-bola]").forEach(function (b) {
      const s = pior[b.dataset.bola] || "ok";
      b.className = "bola " + s;
      b.title = s === "falta" ? "falta preencher" : s === "atencao" ? "pede atenção" : "pronto";
    });
    q("[data-fs-ambiente]").textContent = f.ambiente_rotulo;
  }

  function desenhar(f, partes) {
    estado = f;
    desenharOpcoes(f);
    const todas = !partes;
    desenharLoja(f.loja);
    if (todas || partes.indexOf("empresa") >= 0) desenharEmpresa(f.empresa);
    desenharCertificado(f.certificado);
    if (todas || partes.indexOf("csc") >= 0) desenharCsc(f.csc);
    if (todas || partes.indexOf("numeracao") >= 0) desenharNumeracao(f);
    desenharOutroSistema(f.empresa);
    desenharCategorias(f);
    if (todas || partes.indexOf("contador") >= 0) desenharContador(f.contador);
    desenharPendencias(f);
  }

  // Na primeira vez, desenha tudo. Depois (voltando de outra aba, onde os dados da loja podem
  // ter mudado), só o que não é formulário: o que estiver sendo digitado aqui não se perde.
  async function carregar() {
    const vale = M.novaCarga("fiscal");
    const r = await M.api("GET", "/api/fiscal");
    if (!vale()) return;
    if (!r.ok) { q("[data-fs-resumo]").textContent = "Não foi possível carregar os dados fiscais: " + r.erro; return; }
    desenhar(r.dados, estado ? [] : undefined);
  }

  // ------------------------------------------------------------------ empresa
  forms.empresa.addEventListener("submit", async function (evento) {
    evento.preventDefault();
    const dados = {};
    ["crt", "codigo_municipio", "inscricao_municipal", "cnae", "credenciada", "emite_hoje", "emite_hoje_detalhe"].forEach(function (campo) {
      dados[campo] = forms.empresa[campo].value.trim();
    });
    if (dados.emite_hoje !== "sim") dados.emite_hoje_detalhe = "";
    const r = await M.api("PUT", "/api/fiscal/empresa", dados);
    if (!r.ok) { M.mensagem(forms.empresa, r.erro); return; }
    M.mensagem(forms.empresa, "");
    desenhar(r.dados, ["empresa"]);
    M.avisar("Dados fiscais da empresa salvos.");
  });

  // ------------------------------------------------------------------ certificado
  function lerArquivo(arquivo) {
    return new Promise(function (resolver, falhar) {
      const leitor = new FileReader();
      leitor.onload = function () { resolver(String(leitor.result).split(",")[1] || ""); };
      leitor.onerror = function () { falhar(leitor.error); };
      leitor.readAsDataURL(arquivo);
    });
  }

  forms.certificado.addEventListener("submit", async function (evento) {
    evento.preventDefault();
    const form = forms.certificado;
    const arquivo = form.arquivo.files && form.arquivo.files[0];
    if (!arquivo) { M.mensagem(form, "Escolha o arquivo do certificado (termina em .pfx ou .p12)."); q("[data-fs-escolher]").focus(); return; }
    if (!/\.(pfx|p12)$/i.test(arquivo.name)) { M.mensagem(form, "Este arquivo não parece um certificado A1: o nome dele termina em .pfx ou .p12."); return; }
    if (arquivo.size > LIMITE_DO_ARQUIVO) { M.mensagem(form, "Este arquivo é grande demais para ser um certificado A1. Confira se escolheu o arquivo certo."); return; }
    if (!form.senha.value) { M.mensagem(form, "Digite a senha do certificado (quem emitiu o certificado entregou a senha junto)."); form.senha.focus(); return; }
    if (estado && estado.certificado) {
      const pergunta = await M.confirmar({
        titulo: "Trocar o certificado?",
        texto: "Já há um certificado instalado (válido até " + M.dataBR(estado.certificado.fim) + "). O novo vai ficar no lugar dele.",
        sim: "Trocar o certificado",
      });
      if (!pergunta.ok) return;
    }
    let conteudo;
    try { conteudo = await lerArquivo(arquivo); }
    catch (falha) { M.mensagem(form, "Não deu para ler o arquivo escolhido. Escolha de novo."); return; }
    M.mensagem(form, "Abrindo o certificado…", "dica");
    const r = await M.api("POST", "/api/fiscal/certificado", { nome_arquivo: arquivo.name, conteudo_base64: conteudo, senha: form.senha.value });
    form.senha.value = ""; // a senha não fica na tela, deu certo ou não
    if (!r.ok) { M.mensagem(form, r.erro); form.senha.focus(); return; }
    form.arquivo.value = "";
    nomeDoArquivo.textContent = "Nenhum arquivo escolhido";
    M.mensagem(form, "");
    mensagemDoCertificado("");
    desenhar(r.dados, []);
    M.atualizarStatus();
    M.avisar("Certificado instalado: " + r.dados.certificado.titular + ", válido até " + M.dataBR(r.dados.certificado.fim) + ".");
  });
  M.cuidarDasSenhas(forms.certificado);

  // O botão do Windows para escolher arquivo vem na língua do Windows; este é sempre igual.
  const nomeDoArquivo = q("[data-fs-nome-arquivo]");
  q("[data-fs-escolher]").addEventListener("click", function () { forms.certificado.arquivo.click(); });
  forms.certificado.arquivo.addEventListener("change", function () {
    const arquivo = forms.certificado.arquivo.files && forms.certificado.arquivo.files[0];
    nomeDoArquivo.textContent = arquivo ? arquivo.name : "Nenhum arquivo escolhido";
    if (arquivo) { M.mensagem(forms.certificado, ""); forms.certificado.senha.focus(); }
  });

  function mensagemDoCertificado(texto, tipo) {
    const linha = q("[data-fs-cert-msg]");
    linha.textContent = texto || "";
    linha.hidden = !texto;
    linha.dataset.tipo = texto ? (tipo || "erro") : "";
  }

  q("[data-fs-cert]").addEventListener("click", async function (evento) {
    const testar = evento.target.closest("[data-fs-testar]");
    const remover = evento.target.closest("[data-fs-remover]");
    if (testar) {
      testar.disabled = true;
      const r = await M.api("POST", "/api/fiscal/certificado/conferir");
      testar.disabled = false;
      mensagemDoCertificado(r.ok ? r.dados.mensagem : r.erro, r.ok ? "ok" : "erro");
      return;
    }
    if (remover) {
      const pergunta = await M.confirmar({
        titulo: "Remover o certificado?",
        texto: "A cópia do certificado e a senha guardadas neste computador serão apagadas. Para emitir NFC-e, será preciso instalar de novo (guarde o arquivo original).",
        sim: "Remover",
        perigo: true,
      });
      if (!pergunta.ok) return;
      const r = await M.api("POST", "/api/fiscal/certificado/remover", { confirmo: true });
      if (!r.ok) { mensagemDoCertificado(r.erro, "erro"); return; }
      mensagemDoCertificado("");
      desenhar(r.dados, []);
      M.atualizarStatus();
      M.avisar("Certificado removido deste computador.");
    }
  });

  // ------------------------------------------------------------------ CSC
  forms.csc.mostrar.addEventListener("change", function () {
    const tipo = forms.csc.mostrar.checked ? "text" : "password";
    forms.csc.codigo_homologacao.type = tipo;
    forms.csc.codigo_producao.type = tipo;
  });

  forms.csc.addEventListener("submit", async function (evento) {
    evento.preventDefault();
    const f = forms.csc;
    const dados = {
      id_homologacao: f.id_homologacao.value.trim(), codigo_homologacao: f.codigo_homologacao.value.trim(), apagar_homologacao: f.apagar_homologacao.checked,
      id_producao: f.id_producao.value.trim(), codigo_producao: f.codigo_producao.value.trim(), apagar_producao: f.apagar_producao.checked,
    };
    const r = await M.api("PUT", "/api/fiscal/csc", dados);
    if (!r.ok) { M.mensagem(f, r.erro); return; }
    M.mensagem(f, "");
    desenhar(r.dados, ["csc"]);
    M.avisar("CSC salvo.");
  });

  // ------------------------------------------------------------------ numeração
  forms.numeracao.addEventListener("submit", async function (evento) {
    evento.preventDefault();
    const linhas = Array.prototype.slice.call(document.querySelectorAll("#tabela-fs-numeracao tbody tr[data-caixa]"));
    let ultimo = null;
    for (const linha of linhas) {
      const serie = linha.querySelector('[name="serie"]').value.trim();
      const proximo = linha.querySelector('[name="proximo"]').value.trim().replace(/\./g, "");
      if (!/^\d+$/.test(serie) || !/^\d+$/.test(proximo)) { M.mensagem(forms.numeracao, "Série e próximo número: só números."); return; }
      const r = await M.api("PUT", "/api/fiscal/numeracao", { caixa_id: Number(linha.dataset.caixa), serie: Number(serie), proximo_numero: Number(proximo) });
      if (!r.ok) { M.mensagem(forms.numeracao, r.erro); return; }
      ultimo = r.dados;
    }
    if (!ultimo) return;
    M.mensagem(forms.numeracao, "");
    desenhar(ultimo, ["numeracao"]);
    M.avisar("Numeração da NFC-e salva.");
  });

  // ------------------------------------------------------------------ contador
  forms.contador.addEventListener("submit", async function (evento) {
    evento.preventDefault();
    const dados = {};
    ["nome", "crc", "telefone", "email", "documento", "observacoes"].forEach(function (campo) { dados[campo] = forms.contador[campo].value.trim(); });
    const r = await M.api("PUT", "/api/fiscal/contador", dados);
    if (!r.ok) { M.mensagem(forms.contador, r.erro); return; }
    M.mensagem(forms.contador, "");
    desenhar(r.dados, ["contador"]);
    M.avisar("Contato do contador salvo.");
  });

  // ------------------------------------------------------------------ produtos por categoria
  function abrirCategoria(c) {
    categoriaAberta = c;
    formCategoria.reset();
    M.mensagem(formCategoria, "");
    dialogo.querySelector("h2").textContent = "Preencher: " + (c.nome || "produtos sem categoria");
    const faltam = [c.sem_ncm ? c.sem_ncm + " sem NCM" : "", c.sem_cfop ? c.sem_cfop + " sem CFOP" : "", c.sem_cst_csosn ? c.sem_cst_csosn + " sem CST/CSOSN" : ""].filter(Boolean);
    dialogo.querySelector("[data-texto]").textContent = plural(c.produtos, "produto ativo", "produtos ativos") + (faltam.length ? " (" + faltam.join(", ") + ")." : ", todos com NCM, CFOP e CST/CSOSN.");
    dialogo.showModal();
    formCategoria.ncm.focus();
  }

  formCategoria.addEventListener("submit", async function (evento) {
    evento.preventDefault();
    const c = categoriaAberta;
    if (!c) return;
    const campo = function (nome) { return formCategoria[nome].value.trim() || null; };
    const dados = {
      categoria: c.nome || "", ncm: campo("ncm"), cest: campo("cest"), cfop: campo("cfop"), cst_csosn: campo("cst_csosn"),
      origem: formCategoria.origem.value || null, sobrescrever: formCategoria.sobrescrever.checked,
    };
    if (!dados.ncm && !dados.cest && !dados.cfop && !dados.cst_csosn && !dados.origem) { M.mensagem(formCategoria, "Preencha pelo menos um dos campos."); return; }
    if (dados.sobrescrever) {
      dialogo.close();
      const pergunta = await M.confirmar({
        titulo: "Trocar os dados fiscais?",
        texto: "Os " + plural(c.produtos, "produto ativo", "produtos ativos") + " de “" + (c.nome || "sem categoria") + "” vão ficar com o que você digitou, mesmo os que já tinham outros valores. A troca fica registrada no registro do sistema.",
        sim: "Trocar em todos",
        perigo: true,
      });
      if (!pergunta.ok) { dialogo.showModal(); return; }
    }
    const r = await M.api("POST", "/api/fiscal/produtos/categoria", dados);
    if (!r.ok) {
      if (!dialogo.open) dialogo.showModal();
      M.mensagem(formCategoria, r.erro);
      return;
    }
    if (dialogo.open) dialogo.close();
    desenhar(r.dados.fiscal, []);
    const n = r.dados.alterados;
    M.avisar(n === 0 ? "Nenhum produto mudou: os campos já estavam preenchidos." : plural(n, "produto atualizado", "produtos atualizados") + ".");
  });

  // ------------------------------------------------------------------ geral
  window.MolekaFiscal = {
    mostrar: function () { mostrarPasso(parteDoEndereco()); if (estado) carregar(); },
    salvar: function () {
      const form = forms[passo];
      if (form) form.requestSubmit();
      else M.avisar("Nesta parte, use o botão “Preencher…” de cada categoria.");
    },
  };
  if (!painel.hidden) window.MolekaFiscal.mostrar();
  carregar();
})();

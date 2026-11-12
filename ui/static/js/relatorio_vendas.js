/* Moleka PDV — Relatórios → Vendas por período (só o gerente).
   Todos os números vêm de /api/relatorios/vendas e /api/relatorios/vendas/lista; a tela não faz
   conta de dinheiro nenhuma. O gráfico só decide a altura das barras e o tom dos quadrados do
   mapa. Sem dado, mostra "—" e o motivo que o servidor manda. */

(function () {
  "use strict";

  const M = window.Moleka;
  const raiz = document.getElementById("relatorio-vendas");
  if (!raiz) return;

  const ABAS = ["resumo", "produtos", "horarios", "operadores", "vendas"];
  const SEMANA = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]; // 0 = segunda, como na API
  const SEMANA_CURTA = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"];
  const MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];
  const MAXIMO_DE_DIAS = 62; // acima disto, o gráfico mostra uma barra por mês
  const TONS = 5; // tons do mapa de horários (ver o CSS)
  const SVG = "http://www.w3.org/2000/svg";

  const periodo = document.getElementById("periodo");
  const pdInicio = document.getElementById("pd-inicio");
  const pdFim = document.getElementById("pd-fim");
  const operador = document.getElementById("operador");
  const vdSituacao = document.getElementById("vd-situacao");
  const areaGraf = raiz.querySelector("[data-area-graf]");
  const dicaGraf = raiz.querySelector("[data-dica-graf]");
  const mapa = raiz.querySelector("[data-mapa]");
  const dicaMapa = raiz.querySelector("[data-dica-mapa]");
  const contagemDaLista = raiz.querySelector("[data-vd-contagem]");

  let hoje = ""; // a data da loja, dita pelo servidor (AAAA-MM-DD)
  let aba = "resumo";
  let dados = null; // o relatório que está na tela
  let faixaDosDados = null; // [início, fim] do relatório que está na tela
  let listaEmDia = false; // a lista de vendas é do mesmo período e operador do relatório
  let fatias = []; // as barras do gráfico (ver montarFatias)
  let geometria = null; // onde as barras ficaram no desenho
  let focada = -1; // barra com a dica aberta
  let medida = "faturamento"; // do mapa de horários: "faturamento" ou "vendas"

  // ------------------------------------------------------------------ datas e período
  function partes(texto) {
    const p = /^(\d{4})-(\d{2})-(\d{2})/.exec(texto || "");
    return p ? { a: Number(p[1]), m: Number(p[2]), d: Number(p[3]) } : null;
  }

  function iso(a, m, d) {
    return a + "-" + String(m).padStart(2, "0") + "-" + String(d).padStart(2, "0");
  }

  function ultimoDia(a, m) { return new Date(a, m, 0).getDate(); }

  function somarDias(texto, n) {
    const p = partes(texto);
    const dia = new Date(p.a, p.m - 1, p.d + n);
    return iso(dia.getFullYear(), dia.getMonth() + 1, dia.getDate());
  }

  function diasEntre(inicio, fim) {
    const a = partes(inicio);
    const b = partes(fim);
    return Math.round((Date.UTC(b.a, b.m - 1, b.d) - Date.UTC(a.a, a.m - 1, a.d)) / 86400000);
  }

  /* 0 = segunda ... 6 = domingo, como na API. */
  function diaDaSemana(texto) {
    const p = partes(texto);
    return (new Date(p.a, p.m - 1, p.d).getDay() + 6) % 7;
  }

  /* "03/12/2026" */
  function data(texto) {
    const p = partes(texto);
    return p ? String(p.d).padStart(2, "0") + "/" + String(p.m).padStart(2, "0") + "/" + p.a : "—";
  }

  function textoDoPeriodo(inicio, fim) {
    return inicio === fim ? data(inicio) : data(inicio) + " a " + data(fim);
  }

  /* [início, fim] do período escolhido, ou null se as datas digitadas não servem. Os períodos
     prontos param em hoje: dia que ainda não chegou não tem venda para mostrar. */
  function intervalo() {
    const h = partes(hoje);
    if (!h) return null;
    switch (periodo.value) {
      case "hoje": return [hoje, hoje];
      case "ontem": { const ontem = somarDias(hoje, -1); return [ontem, ontem]; }
      case "7": return [somarDias(hoje, -6), hoje];
      case "30": return [somarDias(hoje, -29), hoje];
      case "mes-passado": {
        const m = h.m === 1 ? 12 : h.m - 1;
        const a = h.m === 1 ? h.a - 1 : h.a;
        return [iso(a, m, 1), iso(a, m, ultimoDia(a, m))];
      }
      case "ano": return [iso(h.a, 1, 1), hoje];
      case "datas": {
        const inicio = M.lerData(pdInicio.value);
        const fim = M.lerData(pdFim.value);
        return inicio && fim ? [inicio, fim] : null;
      }
      default: return [iso(h.a, h.m, 1), hoje]; // este mês, até hoje
    }
  }

  function consulta(faixa, extras) {
    const q = new URLSearchParams({ inicio: faixa[0], fim: faixa[1] });
    if (operador.value) q.set("operador_id", operador.value);
    Object.keys(extras || {}).forEach(function (chave) { if (extras[chave]) q.set(chave, extras[chave]); });
    return q.toString();
  }

  function nomeDoOperador() {
    return operador.value ? operador.selectedOptions[0].textContent : "todos";
  }

  // ------------------------------------------------------------------ ajudantes da tela
  function reais(centavos) {
    return centavos === null || centavos === undefined ? "—" : M.formatarCentavos(centavos);
  }

  function plural(n, um, varios) { return n + " " + (n === 1 ? um : varios); }

  function linhaUnica(corpo, colunas, texto) {
    M.trocar(corpo, M.el("tr", null, M.el("td", { class: "sem-linhas", colSpan: colunas, text: texto })));
  }

  function preencher(atributo, valores, dicas) {
    raiz.querySelectorAll("[data-" + atributo + "]").forEach(function (el) {
      const chave = el.dataset[atributo];
      el.textContent = valores[chave] === undefined || valores[chave] === null ? "—" : valores[chave];
      el.title = (dicas && dicas[chave]) || "";
    });
  }

  function semDados(texto) {
    return M.el("div", { class: "sem-grafico" }, M.el("b", { text: "—" }), M.el("span", { text: texto }));
  }

  function celula(texto, classe, titulo) {
    return M.el("td", { class: classe || null, text: texto, title: titulo || null });
  }

  /* Botão Gráfico/Tabela (ou Mapa/Tabela, Faturamento/Nº de vendas). */
  function marcar(grupo, ativo) {
    grupo.forEach(function (b) {
      const sim = b === ativo;
      b.classList.toggle("ativo", sim);
      b.setAttribute("aria-pressed", sim ? "true" : "false");
    });
  }

  // ------------------------------------------------------------------ carga do relatório
  /* Sem relatório (período inválido, erro do servidor): tudo vira "—" com o motivo. */
  function semRelatorio(texto) {
    dados = null;
    fatias = [];
    geometria = null;
    esconderDica();
    esconderDicaDoMapa();
    preencher("k", {}, {});
    raiz.querySelectorAll("[data-k$='_m']").forEach(function (el) { el.textContent = texto; });
    preencher("c", {}, {});
    raiz.querySelectorAll("[data-c$='_m']").forEach(function (el) { el.textContent = texto; });
    M.trocar(areaGraf, semDados(texto));
    linhaUnica(raiz.querySelector("#tabela-graf tbody"), 5, texto);
    linhaUnica(raiz.querySelector("#tabela-formas tbody"), 3, texto);
    linhaUnica(raiz.querySelector("#tabela-produtos tbody"), 9, texto);
    linhaUnica(raiz.querySelector("#tabela-operadores tbody"), 9, texto);
    linhaUnica(raiz.querySelector("#tabela-horarios tbody"), 1, texto);
    linhaUnica(raiz.querySelector("#tabela-lista tbody"), 9, texto);
    M.trocar(mapa, semDados(texto));
    mapa.style.gridTemplateColumns = "";
    M.trocar(raiz.querySelector("[data-legenda]"));
    raiz.querySelector("[data-pico]").textContent = "—";
    contagemDaLista.textContent = "—";
  }

  function mostrarFaixa(faixa) {
    const escolher = periodo.value === "datas";
    const texto = raiz.querySelector("[data-faixa]");
    texto.hidden = escolher;
    texto.textContent = faixa ? textoDoPeriodo(faixa[0], faixa[1]) : "—";
  }

  async function carregar() {
    const vale = M.novaCarga("relatorio");
    M.novaCarga("lista"); // uma lista que ainda estava chegando é do filtro antigo
    const faixa = intervalo();
    mostrarFaixa(faixa);
    listaEmDia = false;
    if (!faixa) { raiz.classList.remove("carregando"); semRelatorio("Digite a data inicial e a data final do período, assim: 01/11/2026."); return; }
    raiz.classList.add("carregando"); // a tela antiga fica, mais clara, até a nova chegar
    const r = await M.api("GET", "/api/relatorios/vendas?" + consulta(faixa));
    if (!vale()) return;
    raiz.classList.remove("carregando");
    if (!r.ok) { semRelatorio("Não foi possível carregar: " + r.erro); return; }
    dados = r.dados;
    faixaDosDados = faixa;
    desenharResumo();
    desenharProdutos();
    desenharHorarios();
    desenharOperadores();
    if (aba === "vendas") carregarLista();
  }

  // ------------------------------------------------------------------ resumo
  function desenharResumo() {
    const d = dados;
    const vendeu = d.vendas > 0;
    const sem = "Sem dados: " + d.motivo + ".";
    const descontos = ["gerente " + reais(d.desconto_gerente_centavos), "formas " + reais(d.descontos_formas_centavos)];
    if (d.acrescimos_formas_centavos) descontos.push("acréscimos " + reais(d.acrescimos_formas_centavos));
    const canceladas = [];
    if (d.canceladas_antes) canceladas.push(d.canceladas_antes + " antes de finalizar (" + reais(d.canceladas_antes_centavos) + ")");
    if (d.canceladas_depois) canceladas.push(d.canceladas_depois + " depois (" + reais(d.canceladas_depois_centavos) + ")");
    let semNfce = vendeu ? reais(d.sem_documento_fiscal_centavos) + " · o sistema ainda não emite NFC-e" : sem;
    if (d.marcadas_para_nfce) semNfce += " · o caixa pediu em " + plural(d.marcadas_para_nfce, "venda", "vendas");
    preencher("k", {
      faturamento: reais(d.faturamento_centavos),
      faturamento_m: vendeu ? plural(d.vendas, "venda finalizada", "vendas finalizadas") : sem,
      ticket: reais(d.ticket_medio_centavos),
      ticket_m: vendeu ? "por venda (faturamento ÷ vendas)" : sem,
      descontos: reais(d.descontos_centavos),
      descontos_m: vendeu ? descontos.join(" · ") : sem,
      canceladas: String(d.canceladas),
      canceladas_m: d.canceladas ? canceladas.join(" · ") : "nenhum cancelamento no período",
      sem_nfce: String(d.sem_documento_fiscal),
      sem_nfce_m: semNfce,
    }, {
      descontos: "Desconto do gerente e descontos das formas de pagamento (Pix, por exemplo), somados",
      sem_nfce: d.motivo_fiscal,
      sem_nfce_m: d.motivo_fiscal,
      canceladas: "Vendas canceladas no período (não entram no faturamento)",
    });
    desenharGrafico();
    desenharFormas();
  }

  function desenharFormas() {
    const corpo = raiz.querySelector("#tabela-formas tbody");
    const d = dados;
    const linhas = d.formas.map(function (f) {
      const ajuste = f.ajuste_centavos
        ? M.el("span", { class: "sub", text: (f.ajuste_centavos < 0 ? "desconto " : "acréscimo ") + M.reais(Math.abs(f.ajuste_centavos)) })
        : null;
      return M.el("tr", { class: f.vendas ? null : "inativa" },
        M.el("td", null, f.rotulo, M.el("span", { class: "sub", text: f.vendas ? plural(f.vendas, "venda", "vendas") : "nenhuma venda" })),
        M.el("td", { class: "num", title: f.motivo || null }, M.reais(f.recebido_centavos), ajuste),
        celula(f.participacao || "—", "num", f.motivo));
    });
    linhas.push(M.el("tr", { class: "forte" }, celula("Total"), celula(M.reais(d.faturamento_centavos), "num", d.motivo ? "Sem dados: " + d.motivo : ""), celula("")));
    M.trocar.apply(null, [corpo].concat(linhas));
  }

  // ---- o gráfico de barras
  /* As barras do período: por hora (um dia só), por dia (até 62 dias) ou por mês. Dias e
     meses sem venda entram, sem barra: a loja pode ter ficado fechada. */
  function montarFatias() {
    const d = dados;
    const lista = [];
    if (d.inicio === d.fim) {
      const horas = d.por_hora;
      const porHora = {};
      horas.forEach(function (h) { porHora[h.hora] = h; });
      if (horas.length) {
        for (let h = horas[0].hora; h <= horas[horas.length - 1].hora; h++) {
          const x = porHora[h];
          lista.push({ rotulo: h + "h", titulo: h + "h às " + (h + 1) + "h", valor: x ? x.faturamento_centavos : null, vendas: x ? x.vendas : 0, ticket: x ? x.ticket_medio_centavos : null, canceladas: null });
        }
      }
      return { modo: "horas", titulo: "Vendas por hora", sub: "faturamento de cada hora, " + data(d.inicio), coluna: "Hora", fatias: lista };
    }
    const fim = d.fim > hoje ? hoje : d.fim; // dia que ainda não chegou fica de fora
    const futuro = d.fim > hoje ? " (até hoje)" : "";
    if (fim < d.inicio) return { modo: "dias", titulo: "Vendas por dia", sub: "o período ainda não chegou", coluna: "Dia", fatias: lista };
    if (diasEntre(d.inicio, fim) + 1 <= MAXIMO_DE_DIAS) {
      const porDia = {};
      d.dias.forEach(function (x) { porDia[x.dia] = x; });
      for (let dia = d.inicio; dia <= fim; dia = somarDias(dia, 1)) {
        const x = porDia[dia];
        lista.push({ rotulo: dia.slice(8, 10), titulo: SEMANA_CURTA[diaDaSemana(dia)] + ", " + data(dia), valor: x ? x.faturamento_centavos : null, vendas: x ? x.vendas : 0, ticket: x ? x.ticket_medio_centavos : null, canceladas: x ? x.canceladas : 0 });
      }
      return { modo: "dias", titulo: "Vendas por dia", sub: "faturamento de cada dia" + futuro, coluna: "Dia", fatias: lista };
    }
    const porMes = {};
    d.meses.forEach(function (x) { porMes[x.mes.slice(0, 7)] = x; });
    const a0 = partes(d.inicio);
    const af = partes(fim);
    const variosAnos = a0.a !== af.a;
    for (let a = a0.a, m = a0.m; a < af.a || (a === af.a && m <= af.m); m === 12 ? (m = 1, a++) : m++) {
      const x = porMes[iso(a, m, 1).slice(0, 7)];
      lista.push({ rotulo: MESES[m - 1].slice(0, 3) + (variosAnos ? "/" + String(a).slice(2) : ""), titulo: MESES[m - 1] + " de " + a, valor: x ? x.faturamento_centavos : null, vendas: x ? x.vendas : 0, ticket: x ? x.ticket_medio_centavos : null, canceladas: x ? x.canceladas : 0 });
    }
    return { modo: "meses", titulo: "Vendas por mês", sub: "faturamento de cada mês" + futuro, coluna: "Mês", fatias: lista };
  }

  function desenharGrafico() {
    esconderDica();
    const montado = montarFatias();
    fatias = montado.fatias;
    raiz.querySelector("[data-graf-titulo]").textContent = montado.titulo;
    raiz.querySelector("[data-graf-sub]").textContent = montado.sub;
    desenharTabelaDoGrafico(montado);
    if (!fatias.some(function (f) { return f.valor; })) {
      geometria = null;
      M.trocar(areaGraf, semDados(dados.motivo ? "Sem dados: " + dados.motivo + "." : "Nenhuma venda para mostrar."));
      return;
    }
    renderizarBarras();
  }

  function desenharTabelaDoGrafico(montado) {
    const tabela = raiz.querySelector("#tabela-graf");
    const comCanceladas = montado.modo !== "horas";
    const titulos = [montado.coluna, "Vendas", "Faturamento (R$)", "Ticket médio (R$)"].concat(comCanceladas ? ["Canceladas"] : []);
    M.trocar(tabela.tHead, M.el.apply(null, ["tr", null].concat(titulos.map(function (t, i) { return M.el("th", { class: i ? "num" : null, text: t }); }))));
    const corpo = tabela.tBodies[0];
    if (!montado.fatias.length) { linhaUnica(corpo, titulos.length, dados.motivo ? "Sem dados: " + dados.motivo + "." : "Nenhuma venda para mostrar."); return; }
    const linhas = montado.fatias.map(function (f) {
      const tds = [celula(f.titulo), celula(String(f.vendas), "num"), celula(M.reais(f.valor), "num", f.valor ? "" : "sem vendas"), celula(M.reais(f.ticket), "num")];
      if (comCanceladas) tds.push(celula(String(f.canceladas), "num"));
      return M.el.apply(null, ["tr", { class: f.valor ? null : "inativa" }].concat(tds));
    });
    const total = [celula("Total"), celula(String(dados.vendas), "num"), celula(M.reais(dados.faturamento_centavos), "num"), celula(M.reais(dados.ticket_medio_centavos), "num")];
    if (comCanceladas) total.push(celula(String(dados.canceladas), "num"));
    linhas.push(M.el.apply(null, ["tr", { class: "forte" }].concat(total)));
    M.trocar.apply(null, [corpo].concat(linhas));
  }

  /* Marcas do eixo dos valores, em centavos: 0, passo, 2 x passo... até passar do maior valor.
     O passo é 1, 2, 2,5 ou 5 vezes uma potência de 10 (em reais), para ler fácil. */
  function escala(maior) {
    const bruto = Math.max(maior / 100 / 4, 0.01);
    const potencia = Math.pow(10, Math.floor(Math.log10(bruto)));
    const passo = [1, 2, 2.5, 5, 10].map(function (m) { return m * potencia; }).find(function (p) { return p >= bruto - 1e-9; });
    const passoC = Math.max(1, Math.round(passo * 100));
    const topo = Math.ceil(maior / passoC) * passoC;
    const marcas = [];
    for (let v = 0; v <= topo; v += passoC) marcas.push(v);
    return { topo: topo, marcas: marcas };
  }

  function rotuloDoEixo(centavos) {
    return centavos % 100 === 0 ? "R$ " + (centavos / 100).toLocaleString("pt-BR") : M.formatarCentavos(centavos);
  }

  function svg(tag, atributos, texto) {
    const el = document.createElementNS(SVG, tag);
    Object.keys(atributos).forEach(function (chave) { el.setAttribute(chave, atributos[chave]); });
    if (texto !== undefined) el.textContent = texto;
    return el;
  }

  function renderizarBarras() {
    const largura = areaGraf.clientWidth;
    const altura = areaGraf.clientHeight;
    if (!fatias.some(function (f) { return f.valor; })) return;
    if (largura < 120 || altura < 90) return; // aba escondida: desenha quando aparecer
    const maior = Math.max.apply(null, fatias.map(function (f) { return f.valor || 0; }));
    const e = escala(maior);
    const esq = Math.max.apply(null, e.marcas.map(function (v) { return rotuloDoEixo(v).length; })) * 6.6 + 14;
    const dir = 8;
    const topo = 22;
    const base = 22;
    const w = largura - esq - dir;
    const h = altura - topo - base;
    const passo = w / fatias.length;
    const barra = Math.max(1, Math.min(24, passo - 2, passo * 0.72)); // sempre um vão de 2px ou mais
    const yDe = function (v) { return topo + h - (v / e.topo) * h; };
    const chao = topo + h;
    const desenho = svg("svg", { width: largura, height: altura, viewBox: "0 0 " + largura + " " + altura, "aria-hidden": "true", focusable: "false" });
    fatias.forEach(function (f, i) {
      desenho.appendChild(svg("rect", { class: "graf-faixa", "data-i": i, x: esq + i * passo, y: topo, width: passo, height: h }));
    });
    e.marcas.forEach(function (v) {
      const y = Math.round(yDe(v)) + 0.5;
      if (v > 0) desenho.appendChild(svg("line", { class: "graf-grade", x1: esq, x2: esq + w, y1: y, y2: y }));
      desenho.appendChild(svg("text", { class: "graf-eixo", x: esq - 8, y: y + 4, "text-anchor": "end" }, rotuloDoEixo(v)));
    });
    let maiorI = -1;
    fatias.forEach(function (f, i) {
      if (!f.valor) return;
      if (maiorI < 0 || f.valor > fatias[maiorI].valor) maiorI = i;
      const x = esq + i * passo + (passo - barra) / 2;
      const yt = Math.min(yDe(f.valor), chao - 2); // valor pequeno ainda aparece
      const r = Math.min(4, barra / 2, chao - yt);
      const d = "M" + x + "," + chao + "V" + (yt + r) + "Q" + x + "," + yt + " " + (x + r) + "," + yt + "H" + (x + barra - r) + "Q" + (x + barra) + "," + yt + " " + (x + barra) + "," + (yt + r) + "V" + chao + "Z";
      desenho.appendChild(svg("path", { class: "graf-barra", "data-b": i, d: d }));
    });
    desenho.appendChild(svg("line", { class: "graf-base", x1: esq, x2: esq + w, y1: chao + 0.5, y2: chao + 0.5 }));
    // Rótulos de baixo: um a cada tantos, para não encavalar.
    const larguraDoRotulo = Math.max.apply(null, fatias.map(function (f) { return f.rotulo.length; })) * 7 + 6;
    const cada = Math.max(1, Math.ceil(larguraDoRotulo / passo));
    fatias.forEach(function (f, i) {
      if (i % cada) return;
      desenho.appendChild(svg("text", { class: "graf-eixo", x: esq + i * passo + passo / 2, y: chao + 16, "text-anchor": "middle" }, f.rotulo));
    });
    // O maior valor vai escrito em cima da barra; o resto fica na dica e na tabela.
    if (maiorI >= 0) {
      const texto = M.formatarCentavos(fatias[maiorI].valor);
      const meio = esq + maiorI * passo + passo / 2;
      const meia = texto.length * 3.6;
      let x = meio;
      let ancora = "middle";
      if (meio - meia < esq) { x = esq; ancora = "start"; } else if (meio + meia > largura - 2) { x = largura - 2; ancora = "end"; }
      desenho.appendChild(svg("text", { class: "graf-rotulo", x: x, y: Math.max(12, yDe(fatias[maiorI].valor) - 7), "text-anchor": ancora }, texto));
    }
    geometria = { esq: esq, passo: passo, barra: barra, yDe: yDe, chao: chao, maior: maiorI };
    M.trocar(areaGraf, desenho);
    if (focada >= 0 && focada < fatias.length && !dicaGraf.hidden) focar(focada);
  }

  function esconderDica() {
    focada = -1;
    dicaGraf.hidden = true;
    areaGraf.querySelectorAll(".foco").forEach(function (el) { el.classList.remove("foco"); });
  }

  function focar(i) {
    if (!geometria) return;
    focada = i;
    areaGraf.querySelectorAll(".foco").forEach(function (el) { el.classList.remove("foco"); });
    const faixa = areaGraf.querySelector('[data-i="' + i + '"]');
    const barra = areaGraf.querySelector('[data-b="' + i + '"]');
    if (faixa) faixa.classList.add("foco");
    if (barra) barra.classList.add("foco");
    const f = fatias[i];
    const linhas = [];
    if (f.vendas) linhas.push(plural(f.vendas, "venda", "vendas") + (f.ticket !== null ? " · ticket " + M.formatarCentavos(f.ticket) : ""));
    if (f.canceladas) linhas.push(plural(f.canceladas, "cancelamento", "cancelamentos"));
    M.trocar.apply(null, [dicaGraf, M.el("span", { class: "t", text: f.titulo }), M.el("b", { text: f.valor ? M.formatarCentavos(f.valor) : "sem vendas" })]
      .concat(linhas.map(function (texto) { return M.el("span", { text: texto }); })));
    dicaGraf.hidden = false;
    // Em cima da barra (ou do chão, sem barra), sem sair do cartão.
    const cartao = dicaGraf.offsetParent || areaGraf;
    const centro = areaGraf.offsetLeft + geometria.esq + i * geometria.passo + geometria.passo / 2;
    const alto = areaGraf.offsetTop + (f.valor ? Math.min(geometria.yDe(f.valor), geometria.chao - 2) : geometria.chao);
    let x = centro - dicaGraf.offsetWidth / 2;
    x = Math.max(6, Math.min(x, cartao.clientWidth - dicaGraf.offsetWidth - 6));
    let y = alto - dicaGraf.offsetHeight - 10;
    if (y < areaGraf.offsetTop) y = areaGraf.offsetTop + 4;
    dicaGraf.style.left = Math.round(x) + "px";
    dicaGraf.style.top = Math.round(y) + "px";
  }

  areaGraf.addEventListener("mousemove", function (evento) {
    if (!geometria) return;
    const caixa = areaGraf.getBoundingClientRect();
    const i = Math.floor((evento.clientX - caixa.left - geometria.esq) / geometria.passo);
    if (i < 0 || i >= fatias.length) { esconderDica(); return; }
    if (i !== focada || dicaGraf.hidden) focar(i);
  });
  areaGraf.addEventListener("mouseleave", function () { if (document.activeElement !== areaGraf) esconderDica(); });
  areaGraf.addEventListener("focus", function () { if (geometria && focada < 0) focar(geometria.maior); });
  areaGraf.addEventListener("blur", esconderDica);
  areaGraf.addEventListener("keydown", function (evento) {
    if (!geometria) return;
    let i = focada < 0 ? geometria.maior : focada;
    if (evento.key === "ArrowRight") i = Math.min(fatias.length - 1, i + 1);
    else if (evento.key === "ArrowLeft") i = Math.max(0, i - 1);
    else if (evento.key === "Home") i = 0;
    else if (evento.key === "End") i = fatias.length - 1;
    else return;
    evento.preventDefault();
    evento.stopPropagation();
    focar(i);
  });

  let desenhoPendente = false;
  if (window.ResizeObserver) {
    new ResizeObserver(function () {
      if (desenhoPendente) return;
      desenhoPendente = true;
      requestAnimationFrame(function () {
        desenhoPendente = false;
        if (dados && !areaGraf.hidden && fatias.some(function (f) { return f.valor; })) renderizarBarras();
      });
    }).observe(areaGraf);
  }

  const botoesDoGrafico = Array.prototype.slice.call(raiz.querySelectorAll("[data-ver]"));
  botoesDoGrafico.forEach(function (b) {
    b.addEventListener("click", function () {
      marcar(botoesDoGrafico, b);
      const tabela = b.dataset.ver === "tabela";
      esconderDica();
      areaGraf.hidden = tabela;
      raiz.querySelector("[data-tabela-graf]").hidden = !tabela;
      if (!tabela && dados) renderizarBarras();
    });
  });

  // ------------------------------------------------------------------ produtos (curva ABC)
  function desenharProdutos() {
    const d = dados;
    const vendeu = d.vendas > 0;
    const sem = "Sem dados: " + d.motivo + ".";
    const valores = {};
    ["A", "B", "C"].forEach(function (letra) {
      const c = d.classes.find(function (x) { return x.classe === letra; });
      valores[letra] = c ? plural(c.produtos, "produto", "produtos") : "—";
      valores[letra + "_m"] = c ? c.participacao + " do faturamento · " + M.formatarCentavos(c.faturamento_centavos) : (vendeu ? "nenhum produto nesta classe" : sem);
    });
    preencher("c", valores);
    const corpo = raiz.querySelector("#tabela-produtos tbody");
    if (!d.produtos.length) { linhaUnica(corpo, 9, sem); return; }
    const linhas = d.produtos.map(function (p, i) {
      return M.el("tr", null,
        celula(String(i + 1), "num"),
        celula(p.codigo || "—"),
        celula(p.descricao),
        celula(M.qtd(p.quantidade) + " " + p.unidade, "num"),
        celula(String(p.vendas), "num"),
        celula(M.reais(p.faturamento_centavos), "num"),
        celula(p.participacao || "—", "num"),
        celula(p.acumulado || "—", "num"),
        M.el("td", null, p.classe ? M.el("span", { class: "tag abc-" + p.classe.toLowerCase(), text: p.classe }) : "—"));
    });
    linhas.push(M.el("tr", { class: "forte" }, celula(""), celula(""), celula("Total"), celula(""), celula(""), celula(M.reais(d.faturamento_centavos), "num"), celula(""), celula(""), celula("")));
    M.trocar.apply(null, [corpo].concat(linhas));
  }

  // ------------------------------------------------------------------ horários (mapa de calor)
  function valorDaMedida(x) {
    return medida === "faturamento" ? x.faturamento_centavos : x.vendas;
  }

  function textoDaMedida(v) {
    if (v === null || v === undefined || v === 0) return "—";
    return medida === "faturamento" ? M.formatarCentavos(v) : String(v);
  }

  function esconderDicaDoMapa() {
    dicaMapa.hidden = true;
    mapa.querySelectorAll(".cel.foco").forEach(function (el) { el.classList.remove("foco"); });
  }

  function desenharHorarios() {
    const d = dados;
    const legenda = raiz.querySelector("[data-legenda]");
    const pico = raiz.querySelector("[data-pico]");
    esconderDicaDoMapa();
    desenharTabelaDosHorarios();
    if (!d.por_hora.length) {
      mapa.style.gridTemplateColumns = "";
      M.trocar(mapa, semDados("Sem dados: " + d.motivo + "."));
      M.trocar(legenda);
      pico.textContent = "—";
      return;
    }
    const horas = [];
    for (let h = d.por_hora[0].hora; h <= d.por_hora[d.por_hora.length - 1].hora; h++) horas.push(h);
    const porCelula = {};
    d.horarios.forEach(function (c) { porCelula[c.dia_semana + "-" + c.hora] = c; });
    let maior = d.horarios[0];
    d.horarios.forEach(function (c) { if (valorDaMedida(c) > valorDaMedida(maior)) maior = c; });
    const topo = valorDaMedida(maior);
    mapa.style.gridTemplateColumns = "minmax(92px,auto) repeat(" + horas.length + ",minmax(18px,1fr)) minmax(86px,auto)";
    const filhos = [M.el("span", { class: "cab" })];
    horas.forEach(function (h) { filhos.push(M.el("span", { class: "cab", text: h + "h" })); });
    filhos.push(M.el("span", { class: "cab tot", text: "Total" }));
    for (let dia = 0; dia < 7; dia++) {
      const semana = d.por_dia_da_semana[dia];
      filhos.push(M.el("span", { class: "dia" }, semana.rotulo, M.el("small", { text: "(" + semana.dias_no_periodo + ")" })));
      horas.forEach(function (h) {
        const c = porCelula[dia + "-" + h];
        const tom = c && valorDaMedida(c) > 0 ? Math.max(1, Math.min(TONS, Math.ceil(valorDaMedida(c) / topo * TONS))) : 0;
        filhos.push(M.el("span", { class: "cel n" + tom, "data-dia": dia, "data-hora": h }));
      });
      filhos.push(M.el("span", { class: "tot", text: textoDaMedida(valorDaMedida(semana)) }));
    }
    M.trocar.apply(null, [mapa].concat(filhos));
    const tons = [M.el("span", { class: "q n0" }), M.el("span", { text: "sem vendas" }), M.el("span", { class: "sep" }), M.el("span", { text: "menos" })];
    for (let n = 1; n <= TONS; n++) tons.push(M.el("span", { class: "q n" + n }));
    tons.push(M.el("span", { text: "mais (o mais escuro chega a " + textoDaMedida(topo) + ")" }));
    M.trocar.apply(null, [legenda].concat(tons));
    pico.textContent = "Maior movimento: " + SEMANA[maior.dia_semana] + ", " + maior.hora + "h — " + M.formatarCentavos(maior.faturamento_centavos) + " em " + plural(maior.vendas, "venda", "vendas");
  }

  function desenharTabelaDosHorarios() {
    const d = dados;
    const tabela = raiz.querySelector("#tabela-horarios");
    const horas = d.por_hora.map(function (h) { return h.hora; });
    M.trocar(tabela.tHead, M.el.apply(null, ["tr", null, M.el("th", { text: "Dia da semana" })]
      .concat(horas.map(function (h) { return M.el("th", { class: "num", text: h + "h" }); }))
      .concat([M.el("th", { class: "num", text: "Total" })])));
    const corpo = tabela.tBodies[0];
    if (!horas.length) { linhaUnica(corpo, 1, "Sem dados: " + d.motivo + "."); return; }
    const porCelula = {};
    d.horarios.forEach(function (c) { porCelula[c.dia_semana + "-" + c.hora] = c; });
    const linhas = d.por_dia_da_semana.map(function (s) {
      return M.el.apply(null, ["tr", null, celula(s.rotulo + " (" + s.dias_no_periodo + ")")]
        .concat(horas.map(function (h) { const c = porCelula[s.dia_semana + "-" + h]; return celula(c ? textoDaMedida(valorDaMedida(c)) : "", "num"); }))
        .concat([celula(textoDaMedida(valorDaMedida(s)), "num")]));
    });
    linhas.push(M.el.apply(null, ["tr", { class: "forte" }, celula("Total")]
      .concat(d.por_hora.map(function (h) { return celula(textoDaMedida(valorDaMedida(h)), "num"); }))
      .concat([celula(textoDaMedida(medida === "faturamento" ? d.faturamento_centavos : d.vendas), "num")])));
    M.trocar.apply(null, [corpo].concat(linhas));
  }

  mapa.addEventListener("mouseover", function (evento) {
    const cel = evento.target.closest(".cel");
    if (!cel || !dados) { esconderDicaDoMapa(); return; }
    const dia = Number(cel.dataset.dia);
    const hora = Number(cel.dataset.hora);
    const c = dados.horarios.find(function (x) { return x.dia_semana === dia && x.hora === hora; });
    esconderDicaDoMapa();
    cel.classList.add("foco");
    M.trocar(dicaMapa,
      M.el("span", { class: "t", text: SEMANA[dia] + ", " + hora + "h às " + (hora + 1) + "h" }),
      M.el("b", { text: c ? (medida === "faturamento" ? M.formatarCentavos(c.faturamento_centavos) : plural(c.vendas, "venda", "vendas")) : "sem vendas" }),
      c ? M.el("span", { text: medida === "faturamento" ? plural(c.vendas, "venda", "vendas") : M.formatarCentavos(c.faturamento_centavos) }) : null,
      M.el("span", { text: "soma de " + plural(dados.por_dia_da_semana[dia].dias_no_periodo, SEMANA[dia], SEMANA[dia] + "s") + " do período" }));
    dicaMapa.hidden = false;
    const cartao = dicaMapa.offsetParent || mapa;
    const caixaCartao = cartao.getBoundingClientRect();
    const caixa = cel.getBoundingClientRect();
    let x = caixa.left - caixaCartao.left + caixa.width / 2 - dicaMapa.offsetWidth / 2;
    x = Math.max(6, Math.min(x, cartao.clientWidth - dicaMapa.offsetWidth - 6));
    let y = caixa.top - caixaCartao.top - dicaMapa.offsetHeight - 8;
    if (y < 4) y = caixa.bottom - caixaCartao.top + 8;
    dicaMapa.style.left = Math.round(x) + "px";
    dicaMapa.style.top = Math.round(y) + "px";
  });
  mapa.addEventListener("mouseleave", esconderDicaDoMapa);

  const botoesDaMedida = Array.prototype.slice.call(raiz.querySelectorAll("[data-medida]"));
  botoesDaMedida.forEach(function (b) {
    b.addEventListener("click", function () {
      marcar(botoesDaMedida, b);
      medida = b.dataset.medida;
      if (dados) desenharHorarios();
    });
  });
  const botoesDoMapa = Array.prototype.slice.call(raiz.querySelectorAll("[data-ver-mapa]"));
  botoesDoMapa.forEach(function (b) {
    b.addEventListener("click", function () {
      marcar(botoesDoMapa, b);
      const tabela = b.dataset.verMapa === "tabela";
      esconderDicaDoMapa();
      raiz.querySelector("[data-mapa-area]").hidden = tabela;
      raiz.querySelector("[data-tabela-mapa]").hidden = !tabela;
    });
  });

  // ------------------------------------------------------------------ operadores
  function desenharOperadores() {
    const d = dados;
    const corpo = raiz.querySelector("#tabela-operadores tbody");
    if (!d.operadores.length) { linhaUnica(corpo, 9, "Sem dados: " + d.motivo + "."); return; }
    M.trocar.apply(null, [corpo].concat(d.operadores.map(function (o) {
      const semVenda = o.vendas ? "" : "nenhuma venda finalizada no período";
      return M.el("tr", null,
        celula(o.nome),
        celula(String(o.vendas), "num"),
        celula(M.reais(o.faturamento_centavos), "num", semVenda),
        celula(M.reais(o.ticket_medio_centavos), "num", semVenda),
        celula(o.participacao || "—", "num", semVenda),
        celula(M.reais(o.desconto_gerente_centavos), "num"),
        celula(String(o.canceladas_antes), "num"),
        celula(String(o.canceladas_depois), "num"),
        celula(M.reais(o.valor_cancelado_centavos), "num"));
    })));
  }

  // ------------------------------------------------------------------ lista de vendas
  function linhaDaVenda(v) {
    let situacao;
    if (v.situacao === "finalizada") {
      situacao = M.el("td", null, M.el("span", { class: "tag ativo", text: "Finalizada" }));
    } else {
      const detalhes = [v.situacao === "cancelada_antes" ? "antes de finalizar" : "depois de finalizada, em " + M.dataBR(v.cancelada_em) + " " + M.hora(v.cancelada_em)];
      if (v.cancelada_por) detalhes.push("por " + v.cancelada_por);
      if (v.motivo_cancelamento) detalhes.push("“" + v.motivo_cancelamento + "”");
      situacao = M.el("td", null, M.el("span", { class: "tag perigo", text: "Cancelada" }), M.el("span", { class: "sub", text: detalhes.join(" · ") }));
    }
    const rotulo = "Comprovante da venda nº " + v.numero;
    const desenho = document.getElementById("ic-impressora").content.firstElementChild.cloneNode(true);
    const botao = M.el("button", {
      type: "button", class: "btn3d mini so-icone", title: "Ver o comprovante (e imprimir)", "aria-label": rotulo,
      onclick: function () { M.verCupom({ titulo: rotulo, ver: "/api/vendas/" + v.id + "/comprovante", imprimir: "/api/vendas/" + v.id + "/imprimir" }); },
    }, desenho);
    return M.el("tr", { class: v.situacao === "finalizada" ? null : "inativa" },
      celula(String(v.numero), "num"),
      celula(M.dataBR(v.momento) + " " + M.hora(v.momento)),
      situacao,
      celula(v.operador || "—"),
      celula(v.cliente || "—", null, v.cliente ? "" : "venda sem cliente identificado"),
      celula(v.formas.length ? v.formas.join(" + ") : "—", null, v.formas.length ? "" : "nenhum pagamento registrado"),
      celula(M.reais(v.total_centavos), "num"),
      celula(v.quer_nfce === null ? "" : (v.quer_nfce ? "pedida" : "não"), null, v.quer_nfce === null ? "a venda foi cancelada antes da escolha" : ""),
      M.el("td", { class: "acoes-linha" }, botao));
  }

  async function carregarLista() {
    const vale = M.novaCarga("lista");
    const corpo = raiz.querySelector("#tabela-lista tbody");
    const faixa = faixaDosDados && dados ? faixaDosDados : intervalo();
    if (!faixa) { contagemDaLista.textContent = "—"; linhaUnica(corpo, 9, "Digite a data inicial e a data final do período, assim: 01/11/2026."); return; }
    const r = await M.api("GET", "/api/relatorios/vendas/lista?" + consulta(faixa, { situacao: vdSituacao.value }));
    if (!vale()) return;
    if (!r.ok) { contagemDaLista.textContent = "—"; linhaUnica(corpo, 9, r.erro); return; }
    listaEmDia = true;
    const l = r.dados;
    const partesDaConta = [];
    if (l.situacao !== "canceladas") partesDaConta.push(plural(l.finalizadas, "finalizada", "finalizadas") + (l.finalizadas ? ", " + M.formatarCentavos(l.finalizadas_centavos) : ""));
    if (l.situacao !== "finalizadas") partesDaConta.push(plural(l.canceladas, "cancelada", "canceladas"));
    contagemDaLista.textContent = partesDaConta.join(" · ") + " · " + textoDoPeriodo(l.inicio, l.fim);
    if (!l.vendas.length) { linhaUnica(corpo, 9, "Sem dados: " + l.motivo + "."); return; }
    M.trocar.apply(null, [corpo].concat(l.vendas.map(linhaDaVenda)));
  }

  // ------------------------------------------------------------------ abas, filtros, impressão
  function mostrarAba(nome, semMexerNoEndereco) {
    aba = ABAS.indexOf(nome) >= 0 ? nome : "resumo";
    esconderDica();
    esconderDicaDoMapa();
    raiz.querySelectorAll("[data-aba]").forEach(function (b) {
      const ativa = b.dataset.aba === aba;
      b.classList.toggle("ativa", ativa);
      b.setAttribute("aria-selected", ativa ? "true" : "false");
    });
    raiz.querySelectorAll("[data-painel]").forEach(function (p) { p.hidden = p.dataset.painel !== aba; });
    if (!semMexerNoEndereco) window.history.replaceState(null, "", "#" + aba);
    if (aba === "resumo" && dados) renderizarBarras(); // escondido, o gráfico não tinha tamanho
    if (aba === "vendas" && dados && !listaEmDia) carregarLista();
  }

  raiz.querySelectorAll("[data-aba]").forEach(function (b) {
    b.addEventListener("click", function () { mostrarAba(b.dataset.aba); });
  });
  window.addEventListener("hashchange", function () { mostrarAba(window.location.hash.slice(1), true); });
  periodo.addEventListener("change", function () {
    const escolher = periodo.value === "datas";
    raiz.querySelector("[data-datas]").hidden = !escolher;
    if (escolher && !pdInicio.value) { // começa do dia 1 do mês até hoje
      pdInicio.value = M.dataBR(hoje.slice(0, 8) + "01");
      pdFim.value = M.dataBR(hoje);
    }
    if (escolher) { pdInicio.focus(); pdInicio.select(); }
    carregar();
  });
  pdInicio.addEventListener("change", carregar);
  pdFim.addEventListener("change", carregar);
  operador.addEventListener("change", carregar);
  vdSituacao.addEventListener("change", carregarLista);

  const TITULOS = {
    resumo: "Vendas por período: resumo",
    produtos: "Vendas por produto (curva ABC)",
    horarios: "Vendas por dia da semana e hora",
    operadores: "Vendas por operador",
    vendas: "Lista de vendas e cancelamentos",
  };

  /* Imprime a aba que está na tela, com o período e o operador no alto da folha. */
  function imprimir() {
    const painel = raiz.querySelector('[data-painel="' + aba + '"]');
    const faixa = dados ? faixaDosDados : intervalo();
    const detalhes = ["Período: " + (faixa ? textoDoPeriodo(faixa[0], faixa[1]) : "—"), "Operador: " + nomeDoOperador()];
    if (aba === "horarios") detalhes.push("Valores: " + (medida === "faturamento" ? "faturamento (R$)" : "número de vendas"));
    if (aba === "vendas") detalhes.push("Lista: " + vdSituacao.selectedOptions[0].textContent + " · " + contagemDaLista.textContent);
    M.imprimirRelatorio({
      titulo: TITULOS[aba],
      detalhes: detalhes,
      resumo: M.cartoesParaOPapel(painel),
      tabelas: painel.querySelectorAll("table.tabela"),
      notas: Array.prototype.map.call(painel.querySelectorAll(".nota"), function (p) { return p.textContent; }),
    });
  }

  document.getElementById("btn-imprimir").addEventListener("click", imprimir);
  document.getElementById("btn-excel").addEventListener("click", function () {
    const faixa = intervalo();
    if (!faixa) { M.avisar("Digite a data inicial e a data final do período, assim: 01/11/2026."); return; }
    M.baixarPlanilha("/api/planilhas/vendas?" + consulta(faixa));
  });

  async function carregarOperadores() {
    const r = await M.api("GET", "/api/operadores");
    if (!r.ok) return; // fica só "Todos"
    r.dados.slice().sort(function (a, b) { return a.nome.localeCompare(b.nome, "pt-BR"); }).forEach(function (o) {
      operador.appendChild(M.el("option", { value: String(o.id), text: o.nome + (o.ativo ? "" : " (inativo)") }));
    });
  }

  (async function iniciar() {
    const status = await M.api("GET", "/api/status");
    hoje = status.ok && status.dados.agora ? status.dados.agora.slice(0, 10) : "";
    await carregarOperadores();
    mostrarAba(window.location.hash.slice(1), true);
    if (!hoje) { semRelatorio("Sem resposta do sistema: não foi possível saber a data de hoje."); return; }
    carregar();
  })();
})();

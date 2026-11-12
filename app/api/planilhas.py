"""Planilhas do Excel dos relatórios. Só o gerente.

Cada planilha chama a mesma função que alimenta a tela, com os mesmos filtros, e só troca o
formato: os números da planilha são os da tela. As abas são montadas por app/excel.py.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app import acesso, config, configuracoes, db, dinheiro, documentos, excel, relatorios, tempo
from app.api import estoque as api_estoque
from app.api import financeiro as api_financeiro
from app.api import relatorios as api_relatorios
from app.models import Operador, TipoLancamento
from app.operadores import RegraError

router = APIRouter(tags=["planilhas"], dependencies=[Depends(acesso.exigir_gerente)])

C = excel.Coluna
SITUACOES_DOS_LANCAMENTOS = {
    "": "Em aberto e pagas",
    "aberto": "Só em aberto",
    "todas_em_aberto": "Em aberto (qualquer data)",
    "pago": "Só pagas e recebidas",
    "vencido": "Vencidas (qualquer data)",
    "cancelado": "Canceladas",
}
TIPOS_DOS_LANCAMENTOS = {
    "": "Despesas e receitas",
    "despesa": "Só despesas",
    "receita": "Só receitas",
}
SITUACOES_DO_ESTOQUE = {
    "": "Todos os produtos",
    "com_saldo": "Com saldo",
    "abaixo": "Abaixo do mínimo",
    "negativo": "Saldo negativo",
}
ESTADOS_DO_ESTOQUE = {"ok": "Em dia", "abaixo": "Baixo", "zerado": "Zerado", "negativo": "Negativo"}
MESES = (
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
)
NOTA_DO_FLUXO = (
    "Venda entra no dia em que foi feita, inclusive no cartão (o prazo e a taxa da maquininha "
    "ainda não são considerados). Sangria e suprimento são da gaveta e ficam no Controle de Caixa."
)


def cabecalho(sessao: Session, operador: Operador) -> excel.Cabecalho:
    loja = configuracoes.ler_loja(sessao)
    return excel.Cabecalho(
        loja=loja.nome_fantasia or loja.razao_social,
        cnpj=documentos.formatar(loja.cnpj),
        operador=operador.nome,
        versao=config.VERSAO,
        agora=tempo.na_loja(tempo.agora()),
    )


def resposta(conteudo: bytes, nome: str) -> Response:
    """O arquivo, com o nome sugerido (o navegador e a janela do programa usam este nome)."""
    simples = nome.encode("ascii", "replace").decode("ascii").replace("?", "_")
    return Response(
        content=conteudo,
        media_type=excel.TIPO_DO_ARQUIVO,
        headers={
            "Content-Disposition": f'attachment; filename="{simples}"; '
            f"filename*=UTF-8''{quote(nome)}",
            "Cache-Control": "no-store",
        },
    )


def texto_do_periodo(inicio: date, fim: date) -> str:
    if inicio == fim:
        return f"Período: {inicio:%d/%m/%Y}"
    return f"Período: {inicio:%d/%m/%Y} a {fim:%d/%m/%Y}"


def meses_incompletos(inicio: date, fim: date) -> list[str]:
    """Avisos para o primeiro e o último mês, quando o período não os pega inteiros."""
    avisos = []
    if inicio.day != 1:
        avisos.append(f"{MESES[inicio.month - 1]}/{inicio.year}: só a partir de {inicio:%d/%m/%Y}.")
    if (fim + timedelta(days=1)).day != 1:
        avisos.append(f"{MESES[fim.month - 1]}/{fim.year}: só até {fim:%d/%m/%Y}.")
    return avisos


def porcento(texto: str | None) -> Decimal | None:
    """ "12,5%" (o texto da tela) -> Decimal("12.5"). É o mesmo número, sem perder casa."""
    if not texto:
        return None
    return Decimal(texto.rstrip("%").replace(".", "").replace(",", "."))


# ---------------------------------------------------------------- relatório de vendas


def abas_de_vendas(
    sessao: Session, inicio: date, fim: date, operador_id: int | None
) -> list[excel.Aba]:
    r = api_relatorios.montar(sessao, inicio, fim, operador_id)
    detalhes = [
        texto_do_periodo(inicio, fim),
        f"Operador: {r.operador_nome}" if r.operador_nome else "Operador: todos",
    ]
    notas = [r.motivo and f"Sem número: {r.motivo}.", f"Documento fiscal: {r.motivo_fiscal}."]
    vendeu = r.vendas > 0

    def menos(valor: int | None) -> int | None:
        return -valor if valor else valor

    resumo = excel.Aba(
        nome="Resumo",
        titulo="Vendas por período: resumo",
        detalhes=detalhes,
        colunas=[
            C("Indicador", largura=42),
            C("Valor", "dinheiro", 16),
            C("Vendas", "inteiro", 10),
        ],
        linhas=[
            ["Valor dos itens (antes dos descontos)", r.itens_centavos, ""],
            ["Desconto do gerente", menos(r.desconto_gerente_centavos), ""],
            ["Descontos das formas de pagamento", menos(r.descontos_formas_centavos), ""],
            ["Acréscimos das formas de pagamento", r.acrescimos_formas_centavos, ""],
            ["Faturamento", r.faturamento_centavos, r.vendas],
            ["Ticket médio (faturamento ÷ vendas)", r.ticket_medio_centavos, ""],
            ["Canceladas antes de finalizar", r.canceladas_antes_centavos, r.canceladas_antes],
            ["Canceladas depois de finalizadas", r.canceladas_depois_centavos, r.canceladas_depois],
            [
                "Vendas sem documento fiscal",
                r.sem_documento_fiscal_centavos,
                r.sem_documento_fiscal,
            ],
            ["Vendas em que o caixa pediu NFC-e", "", r.marcadas_para_nfce],
        ],
        notas=[
            "Faturamento = valor dos itens - desconto do gerente - descontos das formas + "
            "acréscimos das formas. Vendas canceladas não entram.",
            *notas,
        ],
    )
    por_dia = excel.Aba(
        nome="Por dia",
        titulo="Vendas por dia",
        detalhes=detalhes,
        colunas=[
            C("Dia", "data", 12),
            C("Dia da semana", largura=14),
            C("Vendas", "inteiro", 10),
            C("Faturamento", "dinheiro", 16),
            C("Ticket médio", "dinheiro", 14),
            C("Canceladas", "inteiro", 12),
        ],
        linhas=[
            [
                d.dia,
                api_relatorios.DIAS_DA_SEMANA[d.dia.weekday()],
                d.vendas,
                d.faturamento_centavos,
                d.ticket_medio_centavos,
                d.canceladas,
            ]
            for d in r.dias
        ],
        total=[
            "",
            "Total",
            r.vendas,
            r.faturamento_centavos,
            r.ticket_medio_centavos,
            r.canceladas_antes + r.canceladas_depois,
        ]
        if r.dias
        else None,
        vazia=r.motivo,
        notas=["Canceladas: cancelamentos feitos no dia (a venda não soma no faturamento)."],
    )
    por_mes = excel.Aba(
        nome="Por mês",
        titulo="Vendas por mês",
        detalhes=detalhes,
        colunas=[
            C("Mês", largura=16),
            C("Vendas", "inteiro", 10),
            C("Faturamento", "dinheiro", 16),
            C("Ticket médio", "dinheiro", 14),
            C("Canceladas", "inteiro", 12),
        ],
        linhas=[
            [
                f"{MESES[m.mes.month - 1]}/{m.mes.year}",
                m.vendas,
                m.faturamento_centavos,
                m.ticket_medio_centavos,
                m.canceladas,
            ]
            for m in r.meses
        ],
        total=[
            "Total",
            r.vendas,
            r.faturamento_centavos,
            r.ticket_medio_centavos,
            r.canceladas_antes + r.canceladas_depois,
        ]
        if r.meses
        else None,
        vazia=r.motivo,
        notas=["Meses sem venda nem cancelamento não aparecem.", *meses_incompletos(inicio, fim)],
    )
    formas = excel.Aba(
        nome="Formas de pagamento",
        titulo="Vendas por forma de pagamento",
        detalhes=detalhes,
        colunas=[
            C("Forma", largura=14),
            C("Vendas", "inteiro", 10),
            C("Recebido", "dinheiro", 16),
            C("Desconto (-) ou acréscimo (+) da forma", "dinheiro", 20),
            C("% do faturamento", "porcento", 12),
            C("Observação", largura=30),
        ],
        linhas=[
            [
                f.rotulo,
                f.vendas,
                f.recebido_centavos,
                f.ajuste_centavos,
                porcento(f.participacao),
                f.motivo,
            ]
            for f in r.formas
        ],
        total=["Total", "", r.faturamento_centavos, "", "", ""] if vendeu else None,
        notas=[
            "Recebido = o que entrou na forma, sem o troco. Uma venda paga em duas formas conta "
            "nas duas na coluna Vendas."
        ],
    )
    operadores = excel.Aba(
        nome="Operadores",
        titulo="Vendas por operador",
        detalhes=detalhes,
        colunas=[
            C("Operador", largura=24),
            C("Vendas", "inteiro", 10),
            C("Faturamento", "dinheiro", 16),
            C("Ticket médio", "dinheiro", 14),
            C("% do faturamento", "porcento", 12),
            C("Desconto do gerente", "dinheiro", 14),
            C("Canceladas antes de finalizar", "inteiro", 14),
            C("Canceladas depois de finalizadas", "inteiro", 14),
            C("Valor cancelado", "dinheiro", 14),
        ],
        linhas=[
            [
                o.nome,
                o.vendas,
                o.faturamento_centavos,
                o.ticket_medio_centavos,
                porcento(o.participacao),
                o.desconto_gerente_centavos,
                o.canceladas_antes,
                o.canceladas_depois,
                o.valor_cancelado_centavos,
            ]
            for o in r.operadores
        ],
        vazia=r.motivo,
    )
    produtos = excel.Aba(
        nome="Produtos",
        titulo="Vendas por produto (curva ABC)",
        detalhes=detalhes,
        colunas=[
            C("Código", largura=10),
            C("Produto", largura=36),
            C("Unidade", largura=8),
            C("Quantidade", "quantidade", 12),
            C("Vendas", "inteiro", 9),
            C("Faturamento", "dinheiro", 16),
            C("% do faturamento", "porcento", 15),
            C("% acumulado", "porcento", 13),
            C("Classe", largura=9),
        ],
        linhas=[
            [
                p.codigo,
                p.descricao,
                p.unidade,
                p.quantidade,
                p.vendas,
                p.faturamento_centavos,
                porcento(p.participacao),
                porcento(p.acumulado),
                p.classe,
            ]
            for p in r.produtos
        ],
        total=["", "Total", "", "", "", r.faturamento_centavos, "", "", ""] if r.produtos else None,
        vazia=r.motivo,
        notas=[
            "O faturamento de cada venda é dividido entre os itens na proporção do valor de cada "
            "um (descontos e acréscimos incluídos), sem perder nem criar centavos.",
            f"Curva ABC: do produto que mais faturou para o que menos, A são os que somam até "
            f"{relatorios.LIMITE_A}% do faturamento (o que passa dos {relatorios.LIMITE_A}% "
            f"ainda é A), B os seguintes até {relatorios.LIMITE_B}%, e C o resto.",
            "Vendas = em quantas vendas o produto apareceu.",
        ],
    )
    horas = [h.hora for h in r.por_hora]
    grade_valor: dict[tuple[int, int], int] = {}
    grade_vendas: dict[tuple[int, int], int] = {}
    for h in r.horarios:
        grade_valor[(h.dia_semana, h.hora)] = h.faturamento_centavos
        grade_vendas[(h.dia_semana, h.hora)] = h.vendas

    def grade(nome: str, titulo: str, tipo: str, valores: dict[tuple[int, int], int]) -> excel.Aba:
        def medida(soma: api_relatorios.DiaDaSemanaOut | api_relatorios.HoraOut) -> int | None:
            return soma.faturamento_centavos if tipo == "dinheiro" else soma.vendas

        linhas = []
        for dia, rotulo in enumerate(api_relatorios.DIAS_DA_SEMANA):
            semana = r.por_dia_da_semana[dia]
            linha: list[object] = [f"{rotulo} ({semana.dias_no_periodo})"]
            linha += [valores.get((dia, hora), "") for hora in horas]
            linha.append(medida(semana) or "")
            linhas.append(linha)
        total: list[object] = ["Total"]
        total += [medida(h) for h in r.por_hora]
        total.append(r.faturamento_centavos if tipo == "dinheiro" else r.vendas)
        return excel.Aba(
            nome=nome,
            titulo=titulo,
            detalhes=detalhes,
            colunas=[
                C("Dia da semana", largura=14),
                *[C(f"{hora}h", tipo, 11 if tipo == "dinheiro" else 7) for hora in horas],
                C("Total", tipo, 14 if tipo == "dinheiro" else 9),
            ],
            linhas=linhas if horas else [],
            total=total if horas else None,
            vazia=r.motivo,
            notas=[
                "Hora em que a venda foi finalizada, no horário da loja. Célula vazia: nenhuma "
                "venda naquele dia da semana e hora, no período.",
                "Cada linha soma todos os dias daquela semana no período; entre parênteses, "
                "quantos o período tem (um mês pode ter 4 segundas e 5 sábados, por exemplo).",
            ],
        )

    varios_meses = (inicio.year, inicio.month) != (fim.year, fim.month)
    abas = [
        resumo,
        por_dia,
        *([por_mes] if varios_meses else []),
        formas,
        operadores,
        produtos,
        grade("Horários (R$)", "Faturamento por dia da semana e hora", "dinheiro", grade_valor),
        grade(
            "Horários (vendas)",
            "Número de vendas por dia da semana e hora",
            "inteiro",
            grade_vendas,
        ),
    ]
    try:
        lista = api_relatorios.montar_lista(sessao, inicio, fim, operador_id, "")
        linhas = [
            [
                v.numero,
                datetime.fromisoformat(v.momento) if v.momento else None,
                v.situacao_rotulo,
                v.operador,
                v.cliente,
                " + ".join(v.formas),
                v.total_centavos,
                "" if v.quer_nfce is None else ("Sim" if v.quer_nfce else "Não"),
                v.motivo_cancelamento,
                v.cancelada_por,
            ]
            for v in lista.vendas
        ]
        vazia = lista.motivo
    except RegraError as erro:  # período com vendas demais para a lista: a aba diz o motivo
        linhas, vazia = [], str(erro)
    abas.append(
        excel.Aba(
            nome="Lista de vendas",
            titulo="Vendas e cancelamentos do período",
            detalhes=detalhes,
            colunas=[
                C("Nº", "inteiro", 8),
                C("Data e hora", "data_hora", 17),
                C("Situação", largura=28),
                C("Operador", largura=20),
                C("Cliente", largura=24),
                C("Formas", largura=18),
                C("Total", "dinheiro", 14),
                C("NFC-e pedida", largura=8),
                C("Motivo do cancelamento", largura=30),
                C("Cancelada por", largura=20),
            ],
            linhas=linhas,
            vazia=vazia,
            notas=[
                "Data e hora: a da finalização; na venda cancelada antes de finalizar, a do "
                "cancelamento. Horário da loja."
            ],
        )
    )
    return abas


@router.get("/planilhas/vendas")
def planilha_de_vendas(
    inicio: date | None = None,
    fim: date | None = None,
    operador_id: int | None = None,
    sessao: Session = Depends(db.sessao),
    gerente: Operador = Depends(acesso.exigir_gerente),
) -> Response:
    inicio, fim = api_relatorios.periodo(inicio, fim)
    abas = abas_de_vendas(sessao, inicio, fim, operador_id)
    conteudo = excel.montar(cabecalho(sessao, gerente), abas)
    nome = api_relatorios.nome_do_operador(sessao, operador_id)
    titulo = f"Vendas ({nome})" if nome else "Vendas"  # a planilha de um operador não cobre a geral
    return resposta(conteudo, excel.nome_do_arquivo(titulo, inicio, fim))


# ---------------------------------------------------------------- financeiro


def _datas_do_financeiro(inicio: date | None, fim: date | None) -> tuple[date, date]:
    return api_financeiro._periodo(inicio, fim)


@router.get("/planilhas/contas")
def planilha_de_contas(
    inicio: date | None = None,
    fim: date | None = None,
    tipo: TipoLancamento | None = None,
    situacao: str = "",
    sessao: Session = Depends(db.sessao),
    gerente: Operador = Depends(acesso.exigir_gerente),
) -> Response:
    inicio, fim = _datas_do_financeiro(inicio, fim)
    dados = api_financeiro.listar_lancamentos(inicio, fim, tipo, situacao, sessao)
    t = dados.totais
    de_qualquer_data = situacao in ("vencido", "todas_em_aberto")
    detalhes = [
        "Período: qualquer data" if de_qualquer_data else texto_do_periodo(inicio, fim),
        f"Lista: {TIPOS_DOS_LANCAMENTOS[tipo.value if tipo else '']} · "
        f"{SITUACOES_DOS_LANCAMENTOS[situacao or '']}",
    ]
    notas = []
    if dados.em_aberto_fora_do_periodo:
        notas.append(
            f"Há {dados.em_aberto_fora_do_periodo} conta(s) em aberto com vencimento fora do "
            "período, que não estão nesta lista."
        )

    def situacao_de(item: api_financeiro.LancamentoOut) -> str:
        if item.situacao == "pago":
            return "Pago" if item.tipo == TipoLancamento.DESPESA else "Recebido"
        return {"vencido": "Vencido", "cancelado": "Cancelado"}.get(item.situacao, "Em aberto")

    contas = excel.Aba(
        nome="Contas",
        titulo="Contas a pagar e a receber",
        detalhes=detalhes,
        colunas=[
            C("Vencimento", "data", 12),
            C("Descrição", largura=34),
            C("Categoria", largura=28),
            C("Tipo", largura=10),
            C("Valor", "dinheiro", 14),
            C("Situação", largura=12),
            C("Pago ou recebido em", "data", 14),
            C("Forma", largura=10),
            C("Competência", "data", 12),
        ],
        linhas=[
            [
                i.vencimento,
                i.descricao,
                i.categoria,
                "Despesa" if i.tipo == TipoLancamento.DESPESA else "Receita",
                i.valor_centavos,
                situacao_de(i),
                i.pago_em or "",
                i.forma_rotulo or "",
                i.competencia,
            ]
            for i in dados.itens
        ],
        vazia=dados.motivo,
        notas=notas,
    )
    totais = excel.Aba(
        nome="Totais",
        titulo="Contas a pagar e a receber: totais da lista",
        detalhes=detalhes,
        colunas=[C("Indicador", largura=30), C("Valor", "dinheiro", 16)],
        linhas=[
            ["A pagar (em aberto, com as vencidas)", t.a_pagar],
            ["A receber (em aberto, com as vencidas)", t.a_receber],
            ["Pago", t.pago],
            ["Recebido", t.recebido],
            ["Vencido a pagar", t.vencido_a_pagar],
            ["Vencido a receber", t.vencido_a_receber],
        ],
        notas=notas,
    )
    conteudo = excel.montar(cabecalho(sessao, gerente), [contas, totais])
    return resposta(conteudo, excel.nome_do_arquivo("Contas", inicio, fim))


@router.get("/planilhas/fluxo")
def planilha_do_fluxo(
    inicio: date | None = None,
    fim: date | None = None,
    sessao: Session = Depends(db.sessao),
    gerente: Operador = Depends(acesso.exigir_gerente),
) -> Response:
    inicio, fim = _datas_do_financeiro(inicio, fim)
    d = api_financeiro.fluxo(inicio, fim, sessao)
    aba = excel.Aba(
        nome="Fluxo de caixa",
        titulo="Fluxo de caixa",
        detalhes=[texto_do_periodo(inicio, fim)],
        colunas=[
            C("Dia", "data", 12),
            C("Vendas", "dinheiro", 15),
            C("Outros recebimentos", "dinheiro", 15),
            C("Pagamentos", "dinheiro", 15),
            C("Saldo do dia", "dinheiro", 15),
            C("Acumulado", "dinheiro", 15),
            C("A receber", "dinheiro", 15),
            C("A pagar", "dinheiro", 15),
        ],
        linhas=[
            [
                dia.dia,
                dia.vendas_centavos,
                dia.recebimentos_centavos,
                dia.pagamentos_centavos,
                dia.saldo_centavos,
                dia.acumulado_centavos,
                dia.a_receber_centavos,
                dia.a_pagar_centavos,
            ]
            for dia in d.dias
        ],
        total=[
            "",
            d.vendas_centavos,
            d.recebimentos_centavos,
            d.pagamentos_centavos,
            d.saldo_centavos,
            "",
            d.a_receber_centavos,
            d.a_pagar_centavos,
        ]
        if d.dias
        else None,
        vazia=d.motivo,
        notas=[
            d.motivo and f"Sem número: {d.motivo}.",
            f"Vencido, de qualquer data: a pagar {_reais(d.vencidos_a_pagar_centavos)}, "
            f"a receber {_reais(d.vencidos_a_receber_centavos)}.",
            NOTA_DO_FLUXO,
        ],
    )
    conteudo = excel.montar(cabecalho(sessao, gerente), [aba])
    return resposta(conteudo, excel.nome_do_arquivo("Fluxo de caixa", inicio, fim))


def _reais(centavos: int) -> str:
    return dinheiro.formatar(centavos)


@router.get("/planilhas/dre")
def planilha_do_dre(
    inicio: date | None = None,
    fim: date | None = None,
    sessao: Session = Depends(db.sessao),
    gerente: Operador = Depends(acesso.exigir_gerente),
) -> Response:
    inicio, fim = _datas_do_financeiro(inicio, fim)
    d = api_financeiro.dre(inicio, fim, sessao)
    recuo = {"total": "", "linha": "   ", "detalhe": "      "}
    aba = excel.Aba(
        nome="DRE",
        titulo="Demonstração do resultado (DRE)",
        detalhes=[texto_do_periodo(inicio, fim), f"Vendas no período: {d.vendas_quantidade}"],
        colunas=[
            C("Conta", largura=46),
            C("Valor", "dinheiro", 16),
            C("% da receita líquida", "porcento", 14),
            C("Observação", largura=50),
        ],
        linhas=[
            [
                recuo.get(linha.nivel, "") + linha.rotulo,
                linha.valor_centavos,
                porcento(linha.percentual),
                linha.motivo,
            ]
            for linha in d.linhas
        ],
        vazia=d.motivo,
        notas=[d.motivo and f"Sem número: {d.motivo}.", *d.avisos],
    )
    conteudo = excel.montar(cabecalho(sessao, gerente), [aba])
    return resposta(conteudo, excel.nome_do_arquivo("DRE", inicio, fim))


@router.get("/planilhas/rentabilidade")
def planilha_da_rentabilidade(
    inicio: date | None = None,
    fim: date | None = None,
    sessao: Session = Depends(db.sessao),
    gerente: Operador = Depends(acesso.exigir_gerente),
) -> Response:
    inicio, fim = _datas_do_financeiro(inicio, fim)
    d = api_financeiro.rentabilidade(inicio, fim, sessao)
    aba = excel.Aba(
        nome="Rentabilidade",
        titulo="Rentabilidade por produto",
        detalhes=[texto_do_periodo(inicio, fim)],
        colunas=[
            C("Código", largura=10),
            C("Produto", largura=36),
            C("Unidade", largura=8),
            C("Quantidade", "quantidade", 12),
            C("Receita", "dinheiro", 15),
            C("Custo", "dinheiro", 15),
            C("Margem", "dinheiro", 15),
            C("Margem %", "porcento", 10),
            C("Observação", largura=36),
        ],
        linhas=[
            [
                linha.codigo,
                linha.descricao,
                linha.unidade,
                linha.quantidade,
                linha.receita_centavos,
                linha.custo_centavos,
                linha.margem_centavos,
                porcento(linha.margem_percentual),
                linha.motivo,
            ]
            for linha in d.linhas
        ],
        total=[
            "",
            "Total",
            "",
            "",
            d.receita_centavos,
            d.custo_centavos,
            d.margem_centavos,
            porcento(d.margem_percentual),
            "",
        ]
        if d.linhas
        else None,
        vazia=d.motivo,
        notas=[
            d.motivo and f"Observação: {d.motivo}.",
            "O custo é o gravado em cada venda, quando ela foi finalizada.",
        ],
    )
    conteudo = excel.montar(cabecalho(sessao, gerente), [aba])
    return resposta(conteudo, excel.nome_do_arquivo("Rentabilidade", inicio, fim))


# ---------------------------------------------------------------- estoque


@router.get("/planilhas/estoque")
def planilha_do_estoque(
    busca: str | None = None,
    situacao: str | None = None,
    inativos: bool = False,
    sessao: Session = Depends(db.sessao),
    gerente: Operador = Depends(acesso.exigir_gerente),
) -> Response:
    d = api_estoque.ver_estoque(busca, situacao, inativos, sessao)
    r = d.resumo
    filtro = SITUACOES_DO_ESTOQUE.get(situacao or "", "Todos os produtos")
    if busca and busca.strip():
        filtro += f" · pesquisa “{busca.strip()}”"
    if inativos:
        filtro += " · com os inativos"
    hoje = tempo.hoje()
    aba = excel.Aba(
        nome="Estoque",
        titulo="Posição do estoque",
        detalhes=[f"Posição em {hoje:%d/%m/%Y}", f"Lista: {filtro} · {len(d.itens)} produto(s)"],
        colunas=[
            C("Código", largura=10),
            C("Produto", largura=36),
            C("Categoria", largura=16),
            C("Unidade", largura=8),
            C("Saldo", "quantidade", 12),
            C("Estoque mínimo", "quantidade", 12),
            C("Situação", largura=10),
            C("Custo médio", "dinheiro", 13),
            C("Último custo", "dinheiro", 13),
            C("Valor em estoque", "dinheiro", 15),
            C("Ativo", largura=7),
        ],
        linhas=[
            [
                i.codigo,
                i.descricao,
                i.categoria or "",
                i.unidade,
                i.saldo,
                i.estoque_minimo,
                ESTADOS_DO_ESTOQUE.get(i.situacao, i.situacao),
                i.custo_centavos,
                i.ultimo_custo_centavos,
                i.valor_centavos,
                "Sim" if i.ativo else "Não",
            ]
            for i in d.itens
        ],
        vazia="nenhum produto com este filtro",
        notas=[
            f"Na loja toda: {r.produtos} produto(s) ativo(s), {r.com_saldo} com saldo, "
            f"{r.abaixo_do_minimo} abaixo do mínimo, {r.negativos} com saldo negativo.",
            "Valor em estoque de toda a loja: "
            + (_reais(r.valor_centavos) if r.valor_centavos is not None else "—")
            + (f" ({r.motivo_do_valor})" if r.motivo_do_valor else "")
            + ".",
            "Valor em estoque = saldo × custo médio. Sem custo ou sem saldo positivo, fica “—”.",
        ],
    )
    conteudo = excel.montar(cabecalho(sessao, gerente), [aba])
    return resposta(conteudo, excel.nome_do_arquivo("Estoque", hoje))

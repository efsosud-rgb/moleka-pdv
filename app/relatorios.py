"""Relatório de vendas por período: só números do banco, nada estimado.

Regras (ESPECIFICACAO §16):
- Venda do período = venda **finalizada** com a hora de finalização dentro do período, no horário
  da loja. Venda cancelada não soma em nada (nem quando foi cancelada depois, em outro dia).
- Faturamento = soma dos totais das vendas (o que o cliente pagou, já com o desconto do gerente
  e o desconto ou acréscimo das formas de pagamento). É o mesmo número da receita de vendas do
  DRE e da rentabilidade no mesmo período.
- Cancelamentos contam no dia em que foram feitos (hora do cancelamento), separados em "antes de
  finalizar" (a venda nem chegou a ser paga) e "depois de finalizar" (estorno; só o gerente faz).
- Por produto, o faturamento de cada venda é dividido entre os itens na proporção do valor de
  cada um, sem perder nem criar centavos (a mesma divisão da rentabilidade).
- Curva ABC: do produto que mais faturou para o que menos, A são os que, somados, chegam a 80% do
  faturamento (o produto que passa dos 80% ainda é A); B, os seguintes até 95%; C, o resto.
- Dia, dia da semana e hora são os da loja (horário de Brasília), não os do banco (UTC).

As contas são feitas em Python com poucas consultas (vendas, itens e pagamentos do período, uma
consulta de cada), para o relatório de um ano inteiro não pesar no computador do caixa.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session

from app import dinheiro, financeiro, tempo
from app.models import (
    Cliente,
    FormaPagamento,
    Operador,
    Pagamento,
    Produto,
    SessaoCaixa,
    StatusVenda,
    Venda,
    VendaItem,
)
from app.operadores import RegraError

# A lista de vendas nunca vem cortada: passando disto, a tela pede um período menor.
LIMITE_DA_LISTA = 2000
LIMITE_A = 80  # por cento do faturamento
LIMITE_B = 95
SITUACOES_DA_LISTA = ("", "finalizadas", "canceladas")
ORDEM_DAS_FORMAS = (
    FormaPagamento.DINHEIRO,
    FormaPagamento.PIX,
    FormaPagamento.DEBITO,
    FormaPagamento.CREDITO,
)

# Quem vendeu: as vendas da versão 0.2 não guardavam o operador; nelas vale quem abriu o caixa.
_OPERADOR_DA_VENDA = func.coalesce(Venda.operador_id, SessaoCaixa.operador_id)


@dataclass
class Soma:
    vendas: int = 0
    faturamento: int = 0  # centavos

    def somar(self, total: int) -> None:
        self.vendas += 1
        self.faturamento += total

    @property
    def ticket_medio(self) -> int | None:
        return dinheiro.media(self.faturamento, self.vendas)


@dataclass
class DiaDeVendas:
    dia: date
    soma: Soma = field(default_factory=Soma)
    canceladas: int = 0  # cancelamentos feitos neste dia


@dataclass
class MesDeVendas:
    mes: date  # o dia 1 do mês
    soma: Soma = field(default_factory=Soma)
    canceladas: int = 0


@dataclass
class FormaDeVenda:
    forma: FormaPagamento
    recebido: int = 0  # o que entrou nesta forma, sem o troco e já com o desconto ou acréscimo
    vendas: int = 0  # vendas pagas (também) nesta forma: uma venda em duas formas conta nas duas
    ajuste: int = 0  # desconto (negativo) ou acréscimo (positivo) desta forma de pagamento


@dataclass
class OperadorDeVenda:
    operador_id: int
    nome: str
    soma: Soma = field(default_factory=Soma)
    desconto_gerente: int = 0  # desconto dado nas vendas deste operador
    canceladas_antes: int = 0  # vendas dele canceladas antes de finalizar
    canceladas_depois: int = 0  # vendas dele canceladas depois de finalizadas
    valor_cancelado: int = 0


@dataclass
class ProdutoVendido:
    produto_id: int
    codigo: str
    descricao: str
    unidade: str
    quantidade: Decimal = Decimal(0)
    vendas: int = 0  # em quantas vendas o produto apareceu
    faturamento: int = 0
    classe: str = ""  # A, B ou C ("" quando o período não faturou nada)


@dataclass
class Cancelamentos:
    antes: int = 0  # canceladas antes de finalizar (o cliente desistiu, ou erro na venda)
    valor_antes: int = 0  # o total que a venda tinha quando foi cancelada
    depois: int = 0  # canceladas depois de finalizadas (estorno)
    valor_depois: int = 0


@dataclass
class RelatorioDeVendas:
    inicio: date
    fim: date
    operador_id: int | None
    total: Soma
    itens: int  # soma do valor dos itens, antes de qualquer desconto
    desconto_gerente: int
    descontos_formas: int  # soma dos descontos das formas de pagamento (número positivo)
    acrescimos_formas: int
    marcadas_para_nfce: int  # vendas em que o caixa pediu NFC-e ao finalizar
    por_dia: list[DiaDeVendas]  # só os dias com venda ou cancelamento
    por_mes: list[MesDeVendas]  # só os meses com venda ou cancelamento
    por_forma: list[FormaDeVenda]
    por_operador: list[OperadorDeVenda]
    por_horario: dict[tuple[int, int], Soma]  # (dia da semana, 0 = segunda; hora) na loja
    produtos: list[ProdutoVendido]
    cancelamentos: Cancelamentos


def _filtros(operador_id: int | None) -> list[Any]:
    return [] if operador_id is None else [_OPERADOR_DA_VENDA == operador_id]


def _finalizadas(de: datetime, ate: datetime, operador_id: int | None) -> list[Any]:
    return [
        Venda.status == StatusVenda.FINALIZADA,
        Venda.finalizada_em >= de,
        Venda.finalizada_em < ate,
        *_filtros(operador_id),
    ]


def _com_o_caixa[*Colunas](consulta: Select[*Colunas]) -> Select[*Colunas]:
    """Junta o caixa à consulta: é dele que vem o operador das vendas antigas."""
    return consulta.join(SessaoCaixa, SessaoCaixa.id == Venda.sessao_id)


def _nomes_dos_operadores(sessao: Session) -> dict[int, str]:
    return {i: nome for i, nome in sessao.execute(select(Operador.id, Operador.nome))}


def somar_por_mes(dias: list[DiaDeVendas]) -> list[MesDeVendas]:
    """Os dias somados mês a mês, para o gráfico e a planilha de um período longo."""
    meses: dict[date, MesDeVendas] = {}
    for d in dias:
        chave = d.dia.replace(day=1)
        mes = meses.setdefault(chave, MesDeVendas(chave))
        mes.soma.vendas += d.soma.vendas
        mes.soma.faturamento += d.soma.faturamento
        mes.canceladas += d.canceladas
    return [meses[chave] for chave in sorted(meses)]


def dias_da_semana_no_periodo(inicio: date, fim: date) -> list[int]:
    """Quantas segundas, terças... e domingos o período tem (posição 0 = segunda).

    A grade de horários soma todas as segundas do período, todas as terças etc.; um mês pode ter
    quatro de um dia da semana e cinco de outro, e a tela mostra isso ao lado de cada linha.
    """
    if fim < inicio:
        return [0] * 7
    semanas, resto = divmod((fim - inicio).days + 1, 7)
    contagem = [semanas] * 7
    for k in range(resto):
        contagem[(inicio.weekday() + k) % 7] += 1
    return contagem


def classificar_abc(produtos: list[ProdutoVendido]) -> None:
    """Põe a classe A, B ou C em produtos já ordenados do maior faturamento para o menor."""
    total = sum(p.faturamento for p in produtos)
    acumulado_antes = 0
    for produto in produtos:
        if total <= 0:
            produto.classe = ""
        elif acumulado_antes * 100 < LIMITE_A * total:
            produto.classe = "A"
        elif acumulado_antes * 100 < LIMITE_B * total:
            produto.classe = "B"
        else:
            produto.classe = "C"
        acumulado_antes += produto.faturamento


def vendas_do_periodo(
    sessao: Session, inicio: date, fim: date, operador_id: int | None = None
) -> RelatorioDeVendas:
    financeiro.conferir_periodo(inicio, fim)
    de, ate = tempo.limites_do_periodo(inicio, fim)
    filtro = _finalizadas(de, ate, operador_id)
    nomes = _nomes_dos_operadores(sessao)

    # ---- as vendas finalizadas
    vendas = sessao.execute(
        _com_o_caixa(
            select(
                Venda.id,
                Venda.finalizada_em,
                Venda.subtotal_centavos,
                Venda.desconto_centavos,
                Venda.total_centavos,
                Venda.quer_nfce,
                _OPERADOR_DA_VENDA,
            )
        )
        .where(*filtro)
        .order_by(Venda.finalizada_em, Venda.id)
    ).all()

    total = Soma()
    itens = desconto_gerente = marcadas = 0
    dias: dict[date, DiaDeVendas] = {}
    horarios: dict[tuple[int, int], Soma] = defaultdict(Soma)
    operadores: dict[int, OperadorDeVenda] = {}
    totais: dict[int, int] = {}

    def do_operador(operador: int) -> OperadorDeVenda:
        if operador not in operadores:
            operadores[operador] = OperadorDeVenda(operador, nomes.get(operador, "—"))
        return operadores[operador]

    def do_dia(dia: date) -> DiaDeVendas:
        if dia not in dias:
            dias[dia] = DiaDeVendas(dia)
        return dias[dia]

    for venda_id, finalizada_em, subtotal, desconto, valor, quer_nfce, quem in vendas:
        assert finalizada_em is not None  # o filtro do período já deixa de fora a hora vazia
        na_loja = tempo.na_loja(finalizada_em)
        totais[venda_id] = valor
        total.somar(valor)
        itens += subtotal
        desconto_gerente += desconto
        marcadas += 1 if quer_nfce else 0
        do_dia(na_loja.date()).soma.somar(valor)
        horarios[(na_loja.weekday(), na_loja.hour)].somar(valor)
        operador = do_operador(quem)
        operador.soma.somar(valor)
        operador.desconto_gerente += desconto

    # ---- os pagamentos das mesmas vendas
    formas = {forma: FormaDeVenda(forma) for forma in ORDEM_DAS_FORMAS}
    pagamentos = sessao.execute(
        _com_o_caixa(
            select(
                Pagamento.venda_id,
                Pagamento.forma,
                Pagamento.valor_centavos,
                Pagamento.ajuste_centavos,
            ).join(Venda, Venda.id == Pagamento.venda_id)
        )
        .where(*filtro)
        .order_by(Pagamento.venda_id, Pagamento.id)
    ).all()
    formas_de_cada_venda: dict[int, set[FormaPagamento]] = defaultdict(set)
    descontos_formas = acrescimos_formas = 0
    for venda_id, forma, valor, ajuste in pagamentos:
        linha = formas[forma]
        linha.recebido += valor
        linha.ajuste += ajuste
        formas_de_cada_venda[venda_id].add(forma)
        if ajuste < 0:
            descontos_formas += -ajuste
        else:
            acrescimos_formas += ajuste
    for usadas in formas_de_cada_venda.values():
        for forma in usadas:
            formas[forma].vendas += 1

    # ---- os itens das mesmas vendas, com o faturamento de cada venda dividido entre eles
    linhas = sessao.execute(
        _com_o_caixa(
            select(
                VendaItem.venda_id,
                VendaItem.produto_id,
                VendaItem.quantidade,
                VendaItem.total_centavos,
            ).join(Venda, Venda.id == VendaItem.venda_id)
        )
        .where(*filtro)
        .order_by(VendaItem.venda_id, VendaItem.id)
    ).all()
    itens_de_cada_venda: dict[int, list[tuple[int, Decimal, int]]] = defaultdict(list)
    for venda_id, produto_id, quantidade, valor_do_item in linhas:
        itens_de_cada_venda[venda_id].append((produto_id, Decimal(quantidade), valor_do_item))
    cadastro = {
        i: (codigo, descricao, unidade)
        for i, codigo, descricao, unidade in sessao.execute(
            select(Produto.id, Produto.codigo, Produto.descricao, Produto.unidade)
        )
    }
    produtos: dict[int, ProdutoVendido] = {}
    for venda_id, itens_da_venda in itens_de_cada_venda.items():
        partes = dinheiro.rateio(totais[venda_id], [valor for _p, _q, valor in itens_da_venda])
        nesta_venda: set[int] = set()
        for (produto_id, quantidade, _valor), parte in zip(itens_da_venda, partes, strict=True):
            produto = produtos.get(produto_id)
            if produto is None:
                codigo, descricao, unidade = cadastro.get(produto_id, ("", "—", ""))
                produto = produtos[produto_id] = ProdutoVendido(
                    produto_id, codigo, descricao, unidade
                )
            produto.quantidade += quantidade
            produto.faturamento += parte
            nesta_venda.add(produto_id)
        for produto_id in nesta_venda:
            produtos[produto_id].vendas += 1
    ordenados = sorted(produtos.values(), key=lambda p: (-p.faturamento, p.descricao, p.codigo))
    classificar_abc(ordenados)

    # ---- os cancelamentos feitos no período
    cancelamentos = Cancelamentos()
    canceladas = sessao.execute(
        _com_o_caixa(
            select(
                Venda.cancelada_em, Venda.finalizada_em, Venda.total_centavos, _OPERADOR_DA_VENDA
            )
        ).where(
            Venda.status == StatusVenda.CANCELADA,
            Venda.cancelada_em >= de,
            Venda.cancelada_em < ate,
            *_filtros(operador_id),
        )
    ).all()
    for cancelada_em, finalizada_em, valor, quem in canceladas:
        assert cancelada_em is not None  # o filtro do período já deixa de fora a hora vazia
        do_dia(tempo.na_loja(cancelada_em).date()).canceladas += 1
        operador = do_operador(quem)
        operador.valor_cancelado += valor
        if finalizada_em is None:
            cancelamentos.antes += 1
            cancelamentos.valor_antes += valor
            operador.canceladas_antes += 1
        else:
            cancelamentos.depois += 1
            cancelamentos.valor_depois += valor
            operador.canceladas_depois += 1

    por_dia = [dias[dia] for dia in sorted(dias)]
    return RelatorioDeVendas(
        inicio=inicio,
        fim=fim,
        operador_id=operador_id,
        total=total,
        itens=itens,
        desconto_gerente=desconto_gerente,
        descontos_formas=descontos_formas,
        acrescimos_formas=acrescimos_formas,
        marcadas_para_nfce=marcadas,
        por_dia=por_dia,
        por_mes=somar_por_mes(por_dia),
        por_forma=[formas[forma] for forma in ORDEM_DAS_FORMAS],
        por_operador=sorted(
            operadores.values(), key=lambda o: (-o.soma.faturamento, o.nome, o.operador_id)
        ),
        por_horario=dict(horarios),
        produtos=ordenados,
        cancelamentos=cancelamentos,
    )


# ---------------------------------------------------------------- a lista das vendas


@dataclass
class VendaDaLista:
    id: int
    numero: int
    situacao: str  # "finalizada", "cancelada_depois" (estorno) ou "cancelada_antes"
    momento: datetime  # finalização, ou cancelamento de venda que não chegou a ser finalizada (UTC)
    finalizada_em: datetime | None
    cancelada_em: datetime | None
    operador: str
    cliente: str
    formas: list[FormaPagamento]
    total: int
    quer_nfce: bool | None
    motivo_cancelamento: str
    cancelada_por: str


def lista_de_vendas(
    sessao: Session,
    inicio: date,
    fim: date,
    operador_id: int | None = None,
    situacao: str = "",
) -> list[VendaDaLista]:
    """As vendas finalizadas ou canceladas no período, da mais recente para a mais antiga.

    Uma venda finalizada no período e cancelada depois aparece como cancelada. Passando de
    LIMITE_DA_LISTA vendas, nada vem cortado: o erro pede um período menor.
    """
    financeiro.conferir_periodo(inicio, fim)
    if situacao not in SITUACOES_DA_LISTA:
        raise RegraError("Situação desconhecida.")
    de, ate = tempo.limites_do_periodo(inicio, fim)
    finalizada_no_periodo = and_(Venda.finalizada_em >= de, Venda.finalizada_em < ate)
    cancelada_no_periodo = and_(Venda.cancelada_em >= de, Venda.cancelada_em < ate)
    finalizadas = and_(Venda.status == StatusVenda.FINALIZADA, finalizada_no_periodo)
    canceladas = and_(
        Venda.status == StatusVenda.CANCELADA, or_(finalizada_no_periodo, cancelada_no_periodo)
    )
    escolha = {"": or_(finalizadas, canceladas), "finalizadas": finalizadas}.get(
        situacao, canceladas
    )
    condicoes = [escolha, *_filtros(operador_id)]
    quantas = sessao.scalar(_com_o_caixa(select(func.count(Venda.id))).where(*condicoes))
    if (quantas or 0) > LIMITE_DA_LISTA:
        raise RegraError(
            f"O período tem {quantas} vendas, mais do que as {LIMITE_DA_LISTA} que a lista "
            "mostra de uma vez. Escolha um período menor para ver a lista; os números das "
            "outras abas não mudam."
        )
    nomes = _nomes_dos_operadores(sessao)
    vendas = sessao.execute(
        _com_o_caixa(select(Venda, _OPERADOR_DA_VENDA, Cliente.nome))
        .outerjoin(Cliente, Cliente.id == Venda.cliente_id)
        .where(*condicoes)
    ).all()
    formas: dict[int, list[FormaPagamento]] = defaultdict(list)
    for venda_id, forma in sessao.execute(
        _com_o_caixa(
            select(Pagamento.venda_id, Pagamento.forma).join(Venda, Venda.id == Pagamento.venda_id)
        )
        .where(*condicoes)
        .order_by(Pagamento.venda_id, Pagamento.id)
    ):
        if forma not in formas[venda_id]:
            formas[venda_id].append(forma)
    lista = []
    for venda, quem, cliente in vendas:
        momento = venda.finalizada_em if venda.finalizada_em is not None else venda.cancelada_em
        if momento is None:  # venda aberta: não entra (as condições já a deixam de fora)
            continue
        if venda.status == StatusVenda.FINALIZADA:
            estado = "finalizada"
        else:
            estado = "cancelada_antes" if venda.finalizada_em is None else "cancelada_depois"
        quem_cancelou = venda.cancelada_por_id
        lista.append(
            VendaDaLista(
                id=venda.id,
                numero=venda.numero,
                situacao=estado,
                momento=momento,
                finalizada_em=venda.finalizada_em,
                cancelada_em=venda.cancelada_em,
                operador=nomes.get(quem, "—"),
                cliente=cliente or "",
                formas=formas.get(venda.id, []),
                total=venda.total_centavos,
                quer_nfce=venda.quer_nfce,
                motivo_cancelamento=venda.motivo_cancelamento or "",
                cancelada_por=nomes.get(quem_cancelou, "") if quem_cancelou else "",
            )
        )
    return sorted(lista, key=lambda v: (v.momento, v.id), reverse=True)

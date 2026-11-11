"""Financeiro: categorias, lançamentos (contas a pagar e a receber), fluxo de caixa, DRE e
rentabilidade por produto. Tudo em centavos inteiros, e só com o que está no banco.

De onde vêm os números:
- vendas: as finalizadas no período (canceladas ficam de fora), pela hora em que foram
  finalizadas, no horário de Brasília;
- custo das mercadorias vendidas (CMV): o custo médio que cada item tinha quando a venda foi
  finalizada (gravado na venda). Item vendido sem custo cadastrado NÃO entra no CMV, e o
  relatório avisa quantos são: o lucro não é inventado;
- despesas e receitas: os lançamentos, pela data de competência (DRE) ou pelo dia em que foram
  pagos (fluxo de caixa). Lançamento cancelado não entra em nada.

DRE:
    receita bruta      = soma dos itens vendidos + acréscimos das formas de pagamento
                         + receitas lançadas no grupo "receita de vendas"
    (-) descontos      = descontos do gerente + descontos das formas de pagamento
    (-) deduções       = despesas do grupo "deduções" (impostos sobre a venda, taxas de cartão)
    = receita líquida
    (-) CMV            = custo dos itens vendidos + despesas do grupo "custo"
    = lucro bruto
    (-) despesas operacionais, (+) outras receitas, (-) outras despesas
    = resultado

O grupo "fora do resultado" (compra de mercadoria para revenda, retirada dos sócios) entra no
fluxo de caixa e fica fora do DRE: o custo da mercadoria comprada aparece no CMV quando ela é
vendida, e contar a compra de novo seria contar duas vezes.

Fluxo de caixa: venda entra no dia em que foi feita, inclusive no cartão (prazos e taxas da
maquininha ainda não são considerados). Sangria e suprimento são da gaveta e não entram aqui.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from app import dinheiro, tempo
from app.models import (
    CategoriaFinanceira,
    FormaPagamento,
    GrupoDRE,
    Lancamento,
    Operador,
    OrigemLancamento,
    Pagamento,
    Produto,
    StatusVenda,
    TipoLancamento,
    Venda,
    VendaItem,
)
from app.operadores import RegraError
from app.pesquisa import sem_acento

log = logging.getLogger("moleka.financeiro")

ROTULOS_DOS_GRUPOS: dict[GrupoDRE, str] = {
    GrupoDRE.RECEITA_BRUTA: "Receita de vendas",
    GrupoDRE.DEDUCAO: "Deduções (impostos sobre a venda e taxas)",
    GrupoDRE.CMV: "Custo das mercadorias (CMV)",
    GrupoDRE.DESPESA_OPERACIONAL: "Despesas operacionais",
    GrupoDRE.OUTRAS_RECEITAS: "Outras receitas",
    GrupoDRE.OUTRAS_DESPESAS: "Outras despesas",
    GrupoDRE.FORA_DO_DRE: "Fora do resultado (só fluxo de caixa)",
}
GRUPOS_DE_RECEITA = frozenset(
    {GrupoDRE.RECEITA_BRUTA, GrupoDRE.OUTRAS_RECEITAS, GrupoDRE.FORA_DO_DRE}
)
GRUPOS_DE_DESPESA = frozenset(
    {
        GrupoDRE.DEDUCAO,
        GrupoDRE.CMV,
        GrupoDRE.DESPESA_OPERACIONAL,
        GrupoDRE.OUTRAS_DESPESAS,
        GrupoDRE.FORA_DO_DRE,
    }
)

CATEGORIA_DE_COMPRAS = "Compra de mercadorias para revenda"
# Plano de contas inicial, para a loja não começar do zero. São só nomes de categorias (não são
# lançamentos nem valores); o gerente renomeia, inativa e cria outras.
CATEGORIAS_INICIAIS: tuple[tuple[str, GrupoDRE], ...] = (
    (CATEGORIA_DE_COMPRAS, GrupoDRE.FORA_DO_DRE),
    ("Impostos sobre a venda (DAS)", GrupoDRE.DEDUCAO),
    ("Taxas de cartão e Pix", GrupoDRE.DEDUCAO),
    ("Matéria-prima e insumos", GrupoDRE.CMV),
    ("Embalagens e descartáveis", GrupoDRE.CMV),
    ("Aluguel", GrupoDRE.DESPESA_OPERACIONAL),
    ("Energia elétrica", GrupoDRE.DESPESA_OPERACIONAL),
    ("Água", GrupoDRE.DESPESA_OPERACIONAL),
    ("Internet e telefone", GrupoDRE.DESPESA_OPERACIONAL),
    ("Salários e encargos", GrupoDRE.DESPESA_OPERACIONAL),
    ("Manutenção e limpeza", GrupoDRE.DESPESA_OPERACIONAL),
    ("Contador e sistemas", GrupoDRE.DESPESA_OPERACIONAL),
    ("Outras despesas", GrupoDRE.OUTRAS_DESPESAS),
    ("Outras vendas (fora do caixa)", GrupoDRE.RECEITA_BRUTA),
    ("Outras receitas", GrupoDRE.OUTRAS_RECEITAS),
    ("Retirada dos sócios", GrupoDRE.FORA_DO_DRE),
)
PERIODO_MAXIMO_DIAS = 366


# ---------------------------------------------------------------- categorias


def semear_categorias(sessao: Session) -> None:
    """Cria o plano de contas inicial, só se ainda não houver categoria nenhuma."""
    if sessao.scalar(select(CategoriaFinanceira).limit(1)) is None:
        sessao.add_all(CategoriaFinanceira(nome=n, grupo_dre=g) for n, g in CATEGORIAS_INICIAIS)


def categoria_de_compras(sessao: Session) -> CategoriaFinanceira:
    """A categoria das contas a pagar que nascem da entrada de nota (cria, se não existir)."""
    categoria = sessao.scalar(
        select(CategoriaFinanceira).where(CategoriaFinanceira.nome == CATEGORIA_DE_COMPRAS)
    )
    if categoria is None:
        categoria = CategoriaFinanceira(nome=CATEGORIA_DE_COMPRAS, grupo_dre=GrupoDRE.FORA_DO_DRE)
        sessao.add(categoria)
        sessao.flush()
    return categoria


def gravar_categoria(
    sessao: Session, categoria: CategoriaFinanceira, nome: str, grupo: GrupoDRE, ativo: bool
) -> None:
    nome = " ".join(nome.split())
    if not nome:
        raise RegraError("Digite o nome da categoria.")
    if len(nome) > 60:
        raise RegraError("Nome da categoria: no máximo 60 caracteres.")
    repetida = sessao.scalar(
        select(CategoriaFinanceira).where(
            func.sem_acento(CategoriaFinanceira.nome) == sem_acento(nome)
        )
    )
    if repetida is not None and repetida.id != categoria.id:
        raise RegraError(f"Já existe a categoria “{repetida.nome}”.", status=409)
    if categoria.id is not None and grupo != categoria.grupo_dre:
        usada = sessao.scalar(
            select(func.count(Lancamento.id)).where(Lancamento.categoria_id == categoria.id)
        )
        if usada:
            raise RegraError(
                "Esta categoria já tem lançamentos: o grupo não pode mudar (os relatórios "
                "antigos mudariam). Crie outra categoria e inative esta.",
                status=409,
            )
    categoria.nome = nome
    categoria.grupo_dre = grupo
    categoria.ativo = ativo


# ---------------------------------------------------------------- lançamentos


def _conferir_lancamento(
    sessao: Session, tipo: TipoLancamento, categoria_id: int, descricao: str, valor_centavos: int
) -> tuple[CategoriaFinanceira, str]:
    categoria = sessao.get(CategoriaFinanceira, categoria_id)
    if categoria is None:
        raise RegraError("Escolha a categoria.")
    permitidos = GRUPOS_DE_RECEITA if tipo == TipoLancamento.RECEITA else GRUPOS_DE_DESPESA
    if categoria.grupo_dre not in permitidos:
        qual = "receita" if tipo == TipoLancamento.RECEITA else "despesa"
        raise RegraError(f"A categoria “{categoria.nome}” não serve para {qual}.")
    descricao = " ".join(descricao.split())
    if not descricao:
        raise RegraError("Escreva a descrição (por exemplo: conta de luz de novembro).")
    if len(descricao) > 160:
        raise RegraError("Descrição: no máximo 160 caracteres.")
    if valor_centavos <= 0:
        raise RegraError("O valor precisa ser maior que zero.")
    if valor_centavos > 100_000_000_00:
        raise RegraError("Valor grande demais. Confira o que foi digitado.")
    return categoria, descricao


def criar_lancamento(
    sessao: Session,
    operador: Operador | None,
    *,
    tipo: TipoLancamento,
    categoria_id: int,
    descricao: str,
    valor_centavos: int,
    vencimento: date,
    competencia: date | None = None,
    pago_em: date | None = None,
    forma: FormaPagamento | None = None,
    origem: OrigemLancamento = OrigemLancamento.MANUAL,
    referencia: str | None = None,
) -> Lancamento:
    categoria, descricao = _conferir_lancamento(
        sessao, tipo, categoria_id, descricao, valor_centavos
    )
    if not categoria.ativo and origem == OrigemLancamento.MANUAL:
        raise RegraError(f"A categoria “{categoria.nome}” está inativa.")
    if pago_em is not None and pago_em > tempo.hoje():
        raise RegraError("A data do pagamento não pode ser no futuro.")
    lancamento = Lancamento(
        tipo=tipo,
        categoria_id=categoria.id,
        descricao=descricao,
        valor_centavos=valor_centavos,
        competencia=tempo.meio_dia(competencia or vencimento),
        vencimento=tempo.meio_dia(vencimento),
        pago_em=tempo.meio_dia(pago_em) if pago_em else None,
        forma=forma if pago_em else None,
        origem=origem,
        referencia=referencia,
        criado_por_id=operador.id if operador else None,
    )
    sessao.add(lancamento)
    return lancamento


def _exigir_vivo(lancamento: Lancamento) -> None:
    if lancamento.cancelado_em is not None:
        raise RegraError("Este lançamento foi cancelado.", status=409)


def alterar_lancamento(
    sessao: Session,
    lancamento: Lancamento,
    *,
    categoria_id: int,
    descricao: str,
    valor_centavos: int,
    vencimento: date,
    competencia: date | None,
) -> None:
    _exigir_vivo(lancamento)
    if lancamento.pago_em is not None:
        raise RegraError(
            "Este lançamento está baixado. Desfaça a baixa antes de alterar.", status=409
        )
    categoria, descricao = _conferir_lancamento(
        sessao, lancamento.tipo, categoria_id, descricao, valor_centavos
    )
    lancamento.categoria_id = categoria.id
    lancamento.descricao = descricao
    lancamento.valor_centavos = valor_centavos
    lancamento.vencimento = tempo.meio_dia(vencimento)
    lancamento.competencia = tempo.meio_dia(competencia or vencimento)


def dar_baixa(lancamento: Lancamento, dia: date, forma: FormaPagamento | None) -> None:
    """Marca como pago (despesa) ou recebido (receita) no dia informado."""
    _exigir_vivo(lancamento)
    if lancamento.pago_em is not None:
        raise RegraError("Este lançamento já está baixado.", status=409)
    if dia > tempo.hoje():
        raise RegraError("A data do pagamento não pode ser no futuro.")
    lancamento.pago_em = tempo.meio_dia(dia)
    lancamento.forma = forma


def desfazer_baixa(lancamento: Lancamento) -> None:
    _exigir_vivo(lancamento)
    if lancamento.pago_em is None:
        raise RegraError("Este lançamento não está baixado.", status=409)
    lancamento.pago_em = None
    lancamento.forma = None


def cancelar_lancamento(lancamento: Lancamento, operador: Operador) -> None:
    """Lançamento não é apagado: fica cancelado, com data e autor, e sai de todos os relatórios."""
    _exigir_vivo(lancamento)
    if lancamento.pago_em is not None:
        raise RegraError(
            "Este lançamento está baixado. Desfaça a baixa antes de cancelar.", status=409
        )
    lancamento.cancelado_em = tempo.agora()
    lancamento.cancelado_por_id = operador.id
    log.warning(
        "lançamento %s cancelado por %s: %s, %s centavos",
        lancamento.id,
        operador.login,
        lancamento.descricao,
        lancamento.valor_centavos,
    )


def situacao(lancamento: Lancamento, hoje: date | None = None) -> str:
    """cancelado, pago, vencido ou aberto."""
    if lancamento.cancelado_em is not None:
        return "cancelado"
    if lancamento.pago_em is not None:
        return "pago"
    return "vencido" if lancamento.vencimento.date() < (hoje or tempo.hoje()) else "aberto"


# ---------------------------------------------------------------- período


def conferir_periodo(inicio: date, fim: date) -> None:
    if fim < inicio:
        raise RegraError("A data final é anterior à data inicial.")
    if (fim - inicio).days > PERIODO_MAXIMO_DIAS:
        raise RegraError("Escolha um período de até um ano.")


def _vendas_do_periodo(sessao: Session, inicio: date, fim: date) -> list[Venda]:
    de, ate = tempo.limites_do_periodo(inicio, fim)
    return list(
        sessao.scalars(
            select(Venda)
            .where(
                Venda.status == StatusVenda.FINALIZADA,
                Venda.finalizada_em >= de,
                Venda.finalizada_em < ate,
            )
            .order_by(Venda.finalizada_em)
        )
    )


def _lancamentos_vivos(sessao: Session, *filtros: ColumnElement[bool]) -> list[Lancamento]:
    """Os lançamentos não cancelados que passam nos filtros."""
    consulta = select(Lancamento).where(Lancamento.cancelado_em.is_(None), *filtros)
    return list(sessao.scalars(consulta))


def _entre(coluna: Any, inicio: date, fim: date) -> ColumnElement[bool]:
    """Filtro de uma data "sem hora" (guardada ao meio-dia) dentro do período, inclusive."""
    de = tempo.meio_dia(inicio) - timedelta(hours=12)
    ate = tempo.meio_dia(fim) + timedelta(hours=12)
    filtro: ColumnElement[bool] = (coluna >= de) & (coluna < ate)
    return filtro


# ---------------------------------------------------------------- fluxo de caixa


@dataclass
class DiaDoFluxo:
    dia: date
    vendas: int = 0
    recebimentos: int = 0  # receitas lançadas e baixadas no dia
    pagamentos: int = 0  # despesas baixadas no dia
    a_receber: int = 0  # em aberto, com vencimento no dia
    a_pagar: int = 0

    @property
    def saldo(self) -> int:
        return self.vendas + self.recebimentos - self.pagamentos


@dataclass
class Fluxo:
    inicio: date
    fim: date
    dias: list[DiaDoFluxo] = field(default_factory=list)
    vencidos_a_pagar: int = 0  # em aberto, vencidos antes de hoje (em qualquer data)
    vencidos_a_receber: int = 0

    def total(self, campo: str) -> int:
        return sum(getattr(d, campo) for d in self.dias)


def fluxo_de_caixa(sessao: Session, inicio: date, fim: date) -> Fluxo:
    conferir_periodo(inicio, fim)
    dias: dict[date, DiaDoFluxo] = {}

    def dia(d: date) -> DiaDoFluxo:
        return dias.setdefault(d, DiaDoFluxo(d))

    for venda in _vendas_do_periodo(sessao, inicio, fim):
        assert venda.finalizada_em is not None
        dia(tempo.na_loja(venda.finalizada_em).date()).vendas += venda.total_centavos

    for lancamento in _lancamentos_vivos(sessao, _entre(Lancamento.pago_em, inicio, fim)):
        assert lancamento.pago_em is not None
        linha = dia(lancamento.pago_em.date())
        if lancamento.tipo == TipoLancamento.RECEITA:
            linha.recebimentos += lancamento.valor_centavos
        else:
            linha.pagamentos += lancamento.valor_centavos

    em_aberto = Lancamento.pago_em.is_(None)
    no_periodo = _entre(Lancamento.vencimento, inicio, fim)
    for lancamento in _lancamentos_vivos(sessao, em_aberto, no_periodo):
        linha = dia(lancamento.vencimento.date())
        if lancamento.tipo == TipoLancamento.RECEITA:
            linha.a_receber += lancamento.valor_centavos
        else:
            linha.a_pagar += lancamento.valor_centavos

    resultado = Fluxo(inicio, fim, sorted(dias.values(), key=lambda d: d.dia))
    hoje = tempo.hoje()
    antes_de_hoje = Lancamento.vencimento < tempo.meio_dia(hoje) - timedelta(hours=12)
    for lancamento in _lancamentos_vivos(sessao, em_aberto, antes_de_hoje):
        if lancamento.tipo == TipoLancamento.RECEITA:
            resultado.vencidos_a_receber += lancamento.valor_centavos
        else:
            resultado.vencidos_a_pagar += lancamento.valor_centavos
    return resultado


# ---------------------------------------------------------------- DRE


@dataclass
class Dre:
    inicio: date
    fim: date
    vendas_quantidade: int = 0
    itens_vendidos: int = 0  # soma dos itens ao preço da tabela (subtotal)
    acrescimos_de_forma: int = 0
    outras_vendas: int = 0  # receitas lançadas no grupo "receita de vendas"
    descontos_do_gerente: int = 0
    descontos_de_forma: int = 0
    cmv_das_vendas: int = 0
    itens_sem_custo: int = 0  # quantos itens vendidos estavam sem custo
    venda_sem_custo: int = 0  # quanto esses itens somam em venda (centavos)
    itens_com_custo: int = 0
    # Lançamentos por grupo: {grupo: {categoria: centavos}}
    por_grupo: dict[GrupoDRE, dict[str, int]] = field(default_factory=dict)
    lancamentos_quantidade: int = 0

    def grupo(self, grupo: GrupoDRE) -> int:
        return sum(self.por_grupo.get(grupo, {}).values())

    @property
    def receita_bruta(self) -> int:
        return self.itens_vendidos + self.acrescimos_de_forma + self.grupo(GrupoDRE.RECEITA_BRUTA)

    @property
    def descontos(self) -> int:
        return self.descontos_do_gerente + self.descontos_de_forma

    @property
    def receita_liquida(self) -> int:
        return self.receita_bruta - self.descontos - self.grupo(GrupoDRE.DEDUCAO)

    @property
    def cmv(self) -> int:
        return self.cmv_das_vendas + self.grupo(GrupoDRE.CMV)

    @property
    def lucro_bruto(self) -> int:
        return self.receita_liquida - self.cmv

    @property
    def resultado(self) -> int:
        return (
            self.lucro_bruto
            - self.grupo(GrupoDRE.DESPESA_OPERACIONAL)
            + self.grupo(GrupoDRE.OUTRAS_RECEITAS)
            - self.grupo(GrupoDRE.OUTRAS_DESPESAS)
        )

    @property
    def tem_dados(self) -> bool:
        return self.vendas_quantidade > 0 or self.lancamentos_quantidade > 0

    @property
    def custo_conhecido(self) -> bool:
        """Falso quando houve venda e não há custo nenhum: nem gravado nos itens vendidos, nem
        lançado como despesa do grupo "custo" (quem fabrica lança a matéria-prima ali). Sem
        isso o lucro não pode ser dito."""
        return (
            self.vendas_quantidade == 0 or self.itens_com_custo > 0 or self.grupo(GrupoDRE.CMV) > 0
        )


def dre(sessao: Session, inicio: date, fim: date) -> Dre:
    conferir_periodo(inicio, fim)
    resultado = Dre(inicio, fim)
    for venda in _vendas_do_periodo(sessao, inicio, fim):
        resultado.vendas_quantidade += 1
        resultado.itens_vendidos += venda.subtotal_centavos
        resultado.descontos_do_gerente += venda.desconto_centavos
        for pagamento in venda.pagamentos:
            if pagamento.ajuste_centavos > 0:
                resultado.acrescimos_de_forma += pagamento.ajuste_centavos
            else:
                resultado.descontos_de_forma -= pagamento.ajuste_centavos
        for item in venda.itens:
            if item.custo_unitario_centavos is None:
                resultado.itens_sem_custo += 1
                resultado.venda_sem_custo += item.total_centavos
            else:
                resultado.itens_com_custo += 1
                resultado.cmv_das_vendas += dinheiro.multiplicar(
                    item.custo_unitario_centavos, Decimal(item.quantidade)
                )
    for lancamento in _lancamentos_vivos(sessao, _entre(Lancamento.competencia, inicio, fim)):
        grupo = lancamento.categoria.grupo_dre
        if grupo == GrupoDRE.FORA_DO_DRE:
            continue
        resultado.lancamentos_quantidade += 1
        categorias = resultado.por_grupo.setdefault(grupo, {})
        nome = lancamento.categoria.nome
        categorias[nome] = categorias.get(nome, 0) + lancamento.valor_centavos
    return resultado


# ---------------------------------------------------------------- rentabilidade por produto


@dataclass
class LinhaDeRentabilidade:
    produto_id: int
    codigo: str
    descricao: str
    unidade: str
    quantidade: Decimal = Decimal(0)
    receita: int = 0  # o que o cliente pagou por este produto (desconto e forma rateados)
    custo: int = 0  # só dos itens que tinham custo
    quantidade_sem_custo: Decimal = Decimal(0)

    @property
    def custo_completo(self) -> bool:
        return self.quantidade_sem_custo == 0

    @property
    def margem(self) -> int | None:
        return self.receita - self.custo if self.custo_completo else None


def rentabilidade(sessao: Session, inicio: date, fim: date) -> list[LinhaDeRentabilidade]:
    """Receita, custo e margem de cada produto vendido no período, da maior receita para a menor.

    O desconto da venda e o desconto ou acréscimo da forma de pagamento são divididos entre os
    itens na proporção do valor de cada um, sem perder nem criar centavos: a soma das receitas
    dos produtos é igual ao total das vendas.
    """
    conferir_periodo(inicio, fim)
    linhas: dict[int, LinhaDeRentabilidade] = {}
    for venda in _vendas_do_periodo(sessao, inicio, fim):
        partes = dinheiro.rateio(venda.total_centavos, [i.total_centavos for i in venda.itens])
        for item, parte in zip(venda.itens, partes, strict=True):
            linha = linhas.get(item.produto_id)
            if linha is None:
                produto: Produto = item.produto
                linha = linhas[item.produto_id] = LinhaDeRentabilidade(
                    produto.id, produto.codigo, produto.descricao, produto.unidade
                )
            quantidade = Decimal(item.quantidade)
            linha.quantidade += quantidade
            linha.receita += parte
            if item.custo_unitario_centavos is None:
                linha.quantidade_sem_custo += quantidade
            else:
                linha.custo += dinheiro.multiplicar(item.custo_unitario_centavos, quantidade)
    return sorted(linhas.values(), key=lambda linha: (-linha.receita, linha.descricao))


def recebido_por_forma(sessao: Session, inicio: date, fim: date) -> dict[FormaPagamento, int]:
    """Quanto entrou em cada forma de pagamento nas vendas do período."""
    de, ate = tempo.limites_do_periodo(inicio, fim)
    linhas = sessao.execute(
        select(Pagamento.forma, func.sum(Pagamento.valor_centavos))
        .join(Venda, Venda.id == Pagamento.venda_id)
        .where(
            Venda.status == StatusVenda.FINALIZADA,
            Venda.finalizada_em >= de,
            Venda.finalizada_em < ate,
        )
        .group_by(Pagamento.forma)
    )
    return {forma: int(valor) for forma, valor in linhas}


def itens_sem_custo_por_produto(sessao: Session, inicio: date, fim: date) -> list[tuple[str, str]]:
    """(código, descrição) dos produtos vendidos sem custo no período, para o gerente corrigir."""
    de, ate = tempo.limites_do_periodo(inicio, fim)
    linhas = sessao.execute(
        select(Produto.codigo, Produto.descricao)
        .join(VendaItem, VendaItem.produto_id == Produto.id)
        .join(Venda, Venda.id == VendaItem.venda_id)
        .where(
            Venda.status == StatusVenda.FINALIZADA,
            Venda.finalizada_em >= de,
            Venda.finalizada_em < ate,
            VendaItem.custo_unitario_centavos.is_(None),
        )
        .distinct()
        .order_by(func.sem_acento(Produto.descricao))
    )
    return [(codigo, descricao) for codigo, descricao in linhas]

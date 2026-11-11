"""Financeiro pela API: categorias, lançamentos, fluxo de caixa, DRE e rentabilidade. Só o gerente.

Sem dado, a resposta traz `None` no valor e o motivo em texto: a tela mostra "—" e o motivo.
"""

from __future__ import annotations

import calendar
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import acesso, db, dinheiro, financeiro, tempo
from app.caixa import ROTULOS as ROTULOS_DAS_FORMAS
from app.models import (
    CategoriaFinanceira,
    FormaPagamento,
    GrupoDRE,
    Lancamento,
    Operador,
    OrigemLancamento,
    TipoLancamento,
)
from app.operadores import RegraError

router = APIRouter(tags=["financeiro"], dependencies=[Depends(acesso.exigir_gerente)])

# A lista de lançamentos nunca vem cortada: passando disto, a tela pede um período menor.
LIMITE_DA_LISTA = 2000
SITUACOES_DA_LISTA = ("", "aberto", "pago", "cancelado", "vencido", "todas_em_aberto")


# ---------------------------------------------------------------- período


def _periodo(inicio: date | None, fim: date | None) -> tuple[date, date]:
    """Sem datas, vale o mês corrente inteiro (do dia 1 ao último dia)."""
    hoje = tempo.hoje()
    inicio = inicio or hoje.replace(day=1)
    fim = fim or inicio.replace(day=calendar.monthrange(inicio.year, inicio.month)[1])
    financeiro.conferir_periodo(inicio, fim)
    return inicio, fim


def _percentual(parte: int, todo: int) -> str | None:
    """ "12,5%" — quanto `parte` representa de `todo`. None quando não há sobre o que calcular."""
    if todo <= 0:
        return None
    pct = (Decimal(parte) * 100 / Decimal(todo)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return f"{pct}%".replace(".", ",")


# ---------------------------------------------------------------- categorias


class CategoriaOut(BaseModel):
    id: int
    nome: str
    grupo: GrupoDRE
    grupo_rotulo: str
    serve_para: list[TipoLancamento]
    ativo: bool


class CategoriaIn(BaseModel):
    nome: str
    grupo: GrupoDRE
    ativo: bool = True


class GrupoOut(BaseModel):
    grupo: GrupoDRE
    rotulo: str
    serve_para: list[TipoLancamento]


def _serve_para(grupo: GrupoDRE) -> list[TipoLancamento]:
    tipos = []
    if grupo in financeiro.GRUPOS_DE_RECEITA:
        tipos.append(TipoLancamento.RECEITA)
    if grupo in financeiro.GRUPOS_DE_DESPESA:
        tipos.append(TipoLancamento.DESPESA)
    return tipos


def categoria_out(categoria: CategoriaFinanceira) -> CategoriaOut:
    return CategoriaOut(
        id=categoria.id,
        nome=categoria.nome,
        grupo=categoria.grupo_dre,
        grupo_rotulo=financeiro.ROTULOS_DOS_GRUPOS[categoria.grupo_dre],
        serve_para=_serve_para(categoria.grupo_dre),
        ativo=categoria.ativo,
    )


@router.get("/financeiro/grupos", response_model=list[GrupoOut])
def listar_grupos() -> list[GrupoOut]:
    return [
        GrupoOut(grupo=g, rotulo=rotulo, serve_para=_serve_para(g))
        for g, rotulo in financeiro.ROTULOS_DOS_GRUPOS.items()
    ]


@router.get("/financeiro/categorias", response_model=list[CategoriaOut])
def listar_categorias(
    todas: bool = False, sessao: Session = Depends(db.sessao)
) -> list[CategoriaOut]:
    consulta = select(CategoriaFinanceira).order_by(func.sem_acento(CategoriaFinanceira.nome))
    if not todas:
        consulta = consulta.where(CategoriaFinanceira.ativo.is_(True))
    return [categoria_out(c) for c in sessao.scalars(consulta)]


@router.post("/financeiro/categorias", response_model=CategoriaOut, status_code=201)
def criar_categoria(dados: CategoriaIn, sessao: Session = Depends(db.sessao)) -> CategoriaOut:
    categoria = CategoriaFinanceira()
    financeiro.gravar_categoria(sessao, categoria, dados.nome, dados.grupo, True)
    sessao.add(categoria)
    sessao.commit()
    return categoria_out(categoria)


@router.put("/financeiro/categorias/{categoria_id}", response_model=CategoriaOut)
def alterar_categoria(
    categoria_id: int, dados: CategoriaIn, sessao: Session = Depends(db.sessao)
) -> CategoriaOut:
    categoria = sessao.get(CategoriaFinanceira, categoria_id)
    if categoria is None:
        raise HTTPException(404, "Categoria não encontrada.")
    financeiro.gravar_categoria(sessao, categoria, dados.nome, dados.grupo, dados.ativo)
    sessao.commit()
    return categoria_out(categoria)


# ---------------------------------------------------------------- lançamentos


class LancamentoOut(BaseModel):
    id: int
    tipo: TipoLancamento
    categoria_id: int
    categoria: str
    grupo: GrupoDRE
    descricao: str
    valor_centavos: int
    vencimento: date
    competencia: date
    pago_em: date | None
    forma: FormaPagamento | None
    forma_rotulo: str | None
    origem: OrigemLancamento
    situacao: str  # aberto, vencido, pago ou cancelado


class LancamentoIn(BaseModel):
    tipo: TipoLancamento
    categoria_id: int
    descricao: str
    valor_centavos: int
    vencimento: date
    competencia: date | None = None
    pago_em: date | None = None  # preenchido = já entra baixado
    forma: FormaPagamento | None = None


class LancamentoAlteracao(BaseModel):
    categoria_id: int
    descricao: str
    valor_centavos: int
    vencimento: date
    competencia: date | None = None


class BaixaIn(BaseModel):
    data: date
    forma: FormaPagamento | None = None


class TotaisDeLancamentos(BaseModel):
    a_pagar: int  # despesas em aberto (inclui as vencidas)
    a_receber: int
    pago: int
    recebido: int
    vencido_a_pagar: int
    vencido_a_receber: int


class LancamentosOut(BaseModel):
    inicio: date
    fim: date
    itens: list[LancamentoOut]
    totais: TotaisDeLancamentos
    # Contas em aberto (do tipo pedido) com vencimento FORA do período: a lista não as mostra,
    # e a tela avisa que existem. Zero quando o filtro já é "de qualquer data".
    em_aberto_fora_do_periodo: int
    motivo: str  # por que a lista está vazia, quando está


def lancamento_out(lancamento: Lancamento, hoje: date | None = None) -> LancamentoOut:
    return LancamentoOut(
        id=lancamento.id,
        tipo=lancamento.tipo,
        categoria_id=lancamento.categoria_id,
        categoria=lancamento.categoria.nome,
        grupo=lancamento.categoria.grupo_dre,
        descricao=lancamento.descricao,
        valor_centavos=lancamento.valor_centavos,
        vencimento=lancamento.vencimento.date(),
        competencia=lancamento.competencia.date(),
        pago_em=lancamento.pago_em.date() if lancamento.pago_em else None,
        forma=lancamento.forma,
        forma_rotulo=ROTULOS_DAS_FORMAS[lancamento.forma] if lancamento.forma else None,
        origem=lancamento.origem,
        situacao=financeiro.situacao(lancamento, hoje),
    )


@router.get("/financeiro/lancamentos", response_model=LancamentosOut)
def listar_lancamentos(
    inicio: date | None = None,
    fim: date | None = None,
    tipo: TipoLancamento | None = None,
    # aberto (inclui vencido), pago, cancelado: com vencimento no período;
    # vencido, todas_em_aberto: de qualquer data.
    situacao: str = "",
    sessao: Session = Depends(db.sessao),
) -> LancamentosOut:
    """Lançamentos com vencimento no período. "vencido" traz os atrasados e "todas_em_aberto"
    traz tudo o que falta pagar ou receber, os dois de qualquer data."""
    inicio, fim = _periodo(inicio, fim)
    situacao = situacao or ""
    if situacao not in SITUACOES_DA_LISTA:
        raise RegraError("Filtro de situação desconhecido.")
    hoje = tempo.hoje()
    no_periodo = financeiro._entre(Lancamento.vencimento, inicio, fim)
    em_aberto = (Lancamento.pago_em.is_(None), Lancamento.cancelado_em.is_(None))
    de_qualquer_data = situacao in ("vencido", "todas_em_aberto")
    consulta = select(Lancamento).order_by(Lancamento.vencimento, Lancamento.id)
    consulta = consulta.where(*em_aberto) if de_qualquer_data else consulta.where(no_periodo)
    if tipo is not None:
        consulta = consulta.where(Lancamento.tipo == tipo)
    encontrados = list(sessao.scalars(consulta.limit(LIMITE_DA_LISTA + 1)))
    if len(encontrados) > LIMITE_DA_LISTA:
        # Mostrar só uma parte daria totais errados sem ninguém perceber.
        raise RegraError(
            f"São mais de {LIMITE_DA_LISTA} lançamentos nesta lista. Escolha um período menor."
        )
    itens = []
    for lancamento in encontrados:
        atual = financeiro.situacao(lancamento, hoje)
        if atual == "cancelado" and situacao != "cancelado":
            continue
        if situacao == "aberto" and atual not in ("aberto", "vencido"):
            continue
        if situacao in ("vencido", "pago", "cancelado") and atual != situacao:
            continue
        itens.append(lancamento_out(lancamento, hoje))

    fora = 0
    if situacao in ("", "aberto"):
        contagem = select(func.count(Lancamento.id)).where(*em_aberto, ~no_periodo)
        if tipo is not None:
            contagem = contagem.where(Lancamento.tipo == tipo)
        fora = sessao.scalar(contagem) or 0

    def soma(tipo_: TipoLancamento, *situacoes: str) -> int:
        return sum(i.valor_centavos for i in itens if i.tipo == tipo_ and i.situacao in situacoes)

    return LancamentosOut(
        inicio=inicio,
        fim=fim,
        itens=itens,
        em_aberto_fora_do_periodo=fora,
        totais=TotaisDeLancamentos(
            a_pagar=soma(TipoLancamento.DESPESA, "aberto", "vencido"),
            a_receber=soma(TipoLancamento.RECEITA, "aberto", "vencido"),
            pago=soma(TipoLancamento.DESPESA, "pago"),
            recebido=soma(TipoLancamento.RECEITA, "pago"),
            vencido_a_pagar=soma(TipoLancamento.DESPESA, "vencido"),
            vencido_a_receber=soma(TipoLancamento.RECEITA, "vencido"),
        ),
        motivo="" if itens else "nenhum lançamento com este filtro",
    )


def _lancamento(sessao: Session, lancamento_id: int) -> Lancamento:
    lancamento = sessao.get(Lancamento, lancamento_id)
    if lancamento is None:
        raise HTTPException(404, "Lançamento não encontrado.")
    return lancamento


@router.post("/financeiro/lancamentos", response_model=LancamentoOut, status_code=201)
def criar_lancamento(
    dados: LancamentoIn,
    sessao: Session = Depends(db.sessao),
    gerente: Operador = Depends(acesso.exigir_gerente),
) -> LancamentoOut:
    lancamento = financeiro.criar_lancamento(
        sessao,
        gerente,
        tipo=dados.tipo,
        categoria_id=dados.categoria_id,
        descricao=dados.descricao,
        valor_centavos=dados.valor_centavos,
        vencimento=dados.vencimento,
        competencia=dados.competencia,
        pago_em=dados.pago_em,
        forma=dados.forma,
    )
    sessao.commit()
    return lancamento_out(lancamento)


@router.put("/financeiro/lancamentos/{lancamento_id}", response_model=LancamentoOut)
def alterar_lancamento(
    lancamento_id: int, dados: LancamentoAlteracao, sessao: Session = Depends(db.sessao)
) -> LancamentoOut:
    lancamento = _lancamento(sessao, lancamento_id)
    financeiro.alterar_lancamento(
        sessao,
        lancamento,
        categoria_id=dados.categoria_id,
        descricao=dados.descricao,
        valor_centavos=dados.valor_centavos,
        vencimento=dados.vencimento,
        competencia=dados.competencia,
    )
    sessao.commit()
    return lancamento_out(lancamento)


@router.post("/financeiro/lancamentos/{lancamento_id}/baixa", response_model=LancamentoOut)
def dar_baixa(
    lancamento_id: int, dados: BaixaIn, sessao: Session = Depends(db.sessao)
) -> LancamentoOut:
    lancamento = _lancamento(sessao, lancamento_id)
    financeiro.dar_baixa(lancamento, dados.data, dados.forma)
    sessao.commit()
    return lancamento_out(lancamento)


@router.delete("/financeiro/lancamentos/{lancamento_id}/baixa", response_model=LancamentoOut)
def desfazer_baixa(lancamento_id: int, sessao: Session = Depends(db.sessao)) -> LancamentoOut:
    lancamento = _lancamento(sessao, lancamento_id)
    financeiro.desfazer_baixa(lancamento)
    sessao.commit()
    return lancamento_out(lancamento)


@router.post("/financeiro/lancamentos/{lancamento_id}/cancelar", response_model=LancamentoOut)
def cancelar_lancamento(
    lancamento_id: int,
    sessao: Session = Depends(db.sessao),
    gerente: Operador = Depends(acesso.exigir_gerente),
) -> LancamentoOut:
    lancamento = _lancamento(sessao, lancamento_id)
    if lancamento.origem == OrigemLancamento.COMPRA:
        raise RegraError(
            "Esta conta nasceu de uma nota de compra. Para tirá-la, estorne a nota em "
            "Entrada de NF.",
            status=409,
        )
    financeiro.cancelar_lancamento(lancamento, gerente)
    sessao.commit()
    return lancamento_out(lancamento)


# ---------------------------------------------------------------- fluxo de caixa


class DiaOut(BaseModel):
    dia: date
    vendas_centavos: int
    recebimentos_centavos: int
    pagamentos_centavos: int
    saldo_centavos: int  # do dia
    acumulado_centavos: int  # do começo do período até este dia
    a_receber_centavos: int
    a_pagar_centavos: int


class FluxoOut(BaseModel):
    inicio: date
    fim: date
    dias: list[DiaOut]
    vendas_centavos: int | None
    recebimentos_centavos: int | None
    entradas_centavos: int | None  # vendas + recebimentos
    pagamentos_centavos: int | None
    saldo_centavos: int | None  # entrou - saiu, no período
    a_receber_centavos: int
    a_pagar_centavos: int
    vencidos_a_pagar_centavos: int
    vencidos_a_receber_centavos: int
    recebido_por_forma: dict[FormaPagamento, int]
    motivo: str  # por que não há número, quando não há


@router.get("/financeiro/fluxo", response_model=FluxoOut)
def fluxo(
    inicio: date | None = None, fim: date | None = None, sessao: Session = Depends(db.sessao)
) -> FluxoOut:
    inicio, fim = _periodo(inicio, fim)
    dados = financeiro.fluxo_de_caixa(sessao, inicio, fim)
    acumulado = 0
    dias = []
    for d in dados.dias:
        acumulado += d.saldo
        dias.append(
            DiaOut(
                dia=d.dia,
                vendas_centavos=d.vendas,
                recebimentos_centavos=d.recebimentos,
                pagamentos_centavos=d.pagamentos,
                saldo_centavos=d.saldo,
                acumulado_centavos=acumulado,
                a_receber_centavos=d.a_receber,
                a_pagar_centavos=d.a_pagar,
            )
        )
    movimentou = any(d.vendas or d.recebimentos or d.pagamentos for d in dados.dias)
    return FluxoOut(
        inicio=inicio,
        fim=fim,
        dias=dias,
        vendas_centavos=dados.total("vendas") if movimentou else None,
        recebimentos_centavos=dados.total("recebimentos") if movimentou else None,
        entradas_centavos=dados.total("vendas") + dados.total("recebimentos")
        if movimentou
        else None,
        pagamentos_centavos=dados.total("pagamentos") if movimentou else None,
        saldo_centavos=dados.total("saldo") if movimentou else None,
        a_receber_centavos=dados.total("a_receber"),
        a_pagar_centavos=dados.total("a_pagar"),
        vencidos_a_pagar_centavos=dados.vencidos_a_pagar,
        vencidos_a_receber_centavos=dados.vencidos_a_receber,
        recebido_por_forma=financeiro.recebido_por_forma(sessao, inicio, fim),
        motivo="" if movimentou else "sem vendas nem pagamentos no período",
    )


# ---------------------------------------------------------------- DRE


class LinhaDre(BaseModel):
    chave: str = ""  # receita_bruta, receita_liquida, cmv, lucro_bruto, resultado... ("" = detalhe)
    rotulo: str
    valor_centavos: int | None  # None = não dá para dizer (ver `motivo`)
    nivel: str  # total, linha ou detalhe
    percentual: str | None = None  # sobre a receita líquida
    motivo: str = ""  # por que não há valor, ou o que falta nele ("parcial: ...")


class DreOut(BaseModel):
    inicio: date
    fim: date
    tem_dados: bool
    motivo: str
    vendas_quantidade: int
    linhas: list[LinhaDre]
    avisos: list[str]


SEM_MOVIMENTO = "sem vendas nem lançamentos de resultado no período"
SEM_CUSTO = "as vendas do período não têm custo gravado nem lançado"


def _linhas_do_dre(d: financeiro.Dre) -> list[LinhaDre]:
    """Monta o demonstrativo, linha por linha. Valor que diminui o resultado vai negativo."""
    liquida = d.receita_liquida
    conhecido = d.custo_conhecido
    parcial = (
        f"parcial: {d.itens_sem_custo} item(ns) vendido(s) sem custo gravado"
        if conhecido and d.itens_sem_custo
        else ""
    )
    linhas: list[LinhaDre] = []

    def por(
        nivel: str,
        rotulo: str,
        valor: int | None,
        *,
        chave: str = "",
        pct: bool = False,
        motivo: str = "",
    ) -> None:
        percentual = None
        if pct and valor is not None:
            percentual = _percentual(abs(valor) if nivel == "linha" else valor, liquida)
        linhas.append(
            LinhaDre(
                chave=chave,
                rotulo=rotulo,
                valor_centavos=valor,
                nivel=nivel,
                percentual=percentual,
                motivo=motivo,
            )
        )

    def detalhar(grupo: GrupoDRE, sinal: int) -> None:
        for nome, valor in sorted(d.por_grupo.get(grupo, {}).items()):
            por("detalhe", nome, sinal * valor)

    por("total", "Receita bruta", d.receita_bruta, chave="receita_bruta")
    por("detalhe", "Vendas no caixa", d.itens_vendidos)
    if d.acrescimos_de_forma:
        por("detalhe", "Acréscimos das formas de pagamento", d.acrescimos_de_forma)
    detalhar(GrupoDRE.RECEITA_BRUTA, 1)

    por("linha", "(−) Descontos concedidos", -d.descontos, chave="descontos")
    if d.descontos_do_gerente:
        por("detalhe", "Descontos na venda", -d.descontos_do_gerente)
    if d.descontos_de_forma:
        por("detalhe", "Descontos das formas de pagamento", -d.descontos_de_forma)

    por("linha", "(−) Deduções", -d.grupo(GrupoDRE.DEDUCAO), chave="deducoes", pct=True)
    detalhar(GrupoDRE.DEDUCAO, -1)

    por("total", "= Receita líquida", liquida, chave="receita_liquida", pct=True)

    cmv = "(−) Custo das mercadorias vendidas (CMV)"
    if conhecido:
        por("linha", cmv, -d.cmv, chave="cmv", pct=True, motivo=parcial)
        if d.vendas_quantidade:
            por("detalhe", "Custo dos itens vendidos", -d.cmv_das_vendas)
        detalhar(GrupoDRE.CMV, -1)
        por("total", "= Lucro bruto", d.lucro_bruto, chave="lucro_bruto", pct=True, motivo=parcial)
    else:
        por("linha", cmv, None, chave="cmv", motivo=SEM_CUSTO)
        por("total", "= Lucro bruto", None, chave="lucro_bruto", motivo=SEM_CUSTO)

    despesas = -d.grupo(GrupoDRE.DESPESA_OPERACIONAL)
    por("linha", "(−) Despesas operacionais", despesas, chave="despesas", pct=True)
    detalhar(GrupoDRE.DESPESA_OPERACIONAL, -1)
    if d.grupo(GrupoDRE.OUTRAS_RECEITAS):
        por("linha", "(+) Outras receitas", d.grupo(GrupoDRE.OUTRAS_RECEITAS), pct=True)
        detalhar(GrupoDRE.OUTRAS_RECEITAS, 1)
    if d.grupo(GrupoDRE.OUTRAS_DESPESAS):
        por("linha", "(−) Outras despesas", -d.grupo(GrupoDRE.OUTRAS_DESPESAS), pct=True)
        detalhar(GrupoDRE.OUTRAS_DESPESAS, -1)

    final = "= Resultado do período"
    if conhecido:
        por("total", final, d.resultado, chave="resultado", pct=True, motivo=parcial)
    else:
        por("total", final, None, chave="resultado", motivo=SEM_CUSTO)
    return linhas


def _avisos_do_dre(sessao: Session, d: financeiro.Dre) -> list[str]:
    if not d.itens_sem_custo:
        return []
    produtos = financeiro.itens_sem_custo_por_produto(sessao, d.inicio, d.fim)
    nomes = ", ".join(descricao for _codigo, descricao in produtos[:5])
    mais = f" e mais {len(produtos) - 5}" if len(produtos) > 5 else ""
    if d.custo_conhecido:
        efeito = (
            "O custo deles só está neste demonstrativo se foi lançado como despesa de custo; "
            "se não foi, o lucro bruto e o resultado estão maiores do que o real."
        )
    else:
        efeito = "Sem custo nenhum, o lucro bruto e o resultado não podem ser calculados."
    return [
        f"{d.itens_sem_custo} item(ns) vendido(s), somando "
        f"{dinheiro.formatar(d.venda_sem_custo)}, estão sem custo gravado ({nomes}{mais}): o "
        "produto estava sem custo na hora da venda, ou a venda é de antes da versão 0.4.0. "
        f"{efeito} Cadastre o custo em Produtos ou dê entrada pela nota: ele vale para as "
        "vendas feitas depois."
    ]


@router.get("/financeiro/dre", response_model=DreOut)
def dre(
    inicio: date | None = None, fim: date | None = None, sessao: Session = Depends(db.sessao)
) -> DreOut:
    inicio, fim = _periodo(inicio, fim)
    d = financeiro.dre(sessao, inicio, fim)
    if not d.tem_dados:
        nomes = (
            ("total", "receita_bruta", "Receita bruta"),
            ("linha", "descontos", "(−) Descontos concedidos"),
            ("linha", "deducoes", "(−) Deduções"),
            ("total", "receita_liquida", "= Receita líquida"),
            ("linha", "cmv", "(−) Custo das mercadorias vendidas (CMV)"),
            ("total", "lucro_bruto", "= Lucro bruto"),
            ("linha", "despesas", "(−) Despesas operacionais"),
            ("total", "resultado", "= Resultado do período"),
        )
        return DreOut(
            inicio=inicio,
            fim=fim,
            tem_dados=False,
            motivo=SEM_MOVIMENTO,
            vendas_quantidade=0,
            linhas=[
                LinhaDre(
                    chave=chave,
                    rotulo=rotulo,
                    valor_centavos=None,
                    nivel=nivel,
                    motivo=SEM_MOVIMENTO,
                )
                for nivel, chave, rotulo in nomes
            ],
            avisos=[],
        )
    return DreOut(
        inicio=inicio,
        fim=fim,
        tem_dados=True,
        motivo="",
        vendas_quantidade=d.vendas_quantidade,
        linhas=_linhas_do_dre(d),
        avisos=_avisos_do_dre(sessao, d),
    )


# ---------------------------------------------------------------- rentabilidade


class LinhaRentabilidadeOut(BaseModel):
    produto_id: int
    codigo: str
    descricao: str
    unidade: str
    quantidade: Decimal
    receita_centavos: int
    custo_centavos: int | None  # None = havia item sem custo
    margem_centavos: int | None
    margem_percentual: str | None  # sobre a receita
    motivo: str


class RentabilidadeOut(BaseModel):
    inicio: date
    fim: date
    linhas: list[LinhaRentabilidadeOut]
    receita_centavos: int | None  # de todos os produtos (= total das vendas)
    # Só dos produtos com custo completo: é sobre esta receita que a margem é calculada.
    receita_com_custo_centavos: int | None
    custo_centavos: int | None
    margem_centavos: int | None
    margem_percentual: str | None
    produtos_sem_custo: int
    receita_sem_custo_centavos: int  # vendido sem custo gravado (fora da margem)
    motivo: str


@router.get("/financeiro/rentabilidade", response_model=RentabilidadeOut)
def rentabilidade(
    inicio: date | None = None, fim: date | None = None, sessao: Session = Depends(db.sessao)
) -> RentabilidadeOut:
    inicio, fim = _periodo(inicio, fim)
    dados = financeiro.rentabilidade(sessao, inicio, fim)
    linhas = []
    for linha in dados:
        margem = linha.margem
        linhas.append(
            LinhaRentabilidadeOut(
                produto_id=linha.produto_id,
                codigo=linha.codigo,
                descricao=linha.descricao,
                unidade=linha.unidade,
                quantidade=linha.quantidade,
                receita_centavos=linha.receita,
                custo_centavos=linha.custo if linha.custo_completo else None,
                margem_centavos=margem,
                margem_percentual=_percentual(margem, linha.receita)
                if margem is not None
                else None,
                motivo="" if linha.custo_completo else "vendido sem custo gravado na venda",
            )
        )
    completas = [linha for linha in dados if linha.custo_completo]
    receita = sum(linha.receita for linha in dados)
    receita_com_custo = sum(linha.receita for linha in completas)
    custo = sum(linha.custo for linha in completas)
    tem_margem = bool(completas)
    if not dados:
        motivo = "sem vendas no período"
    elif not completas:
        motivo = "nenhuma venda do período tem o custo gravado"
    elif len(completas) < len(dados):
        motivo = "o custo e a margem somam só os produtos com o custo gravado nas vendas"
    else:
        motivo = ""
    return RentabilidadeOut(
        inicio=inicio,
        fim=fim,
        linhas=linhas,
        receita_centavos=receita if dados else None,
        receita_com_custo_centavos=receita_com_custo if tem_margem else None,
        custo_centavos=custo if tem_margem else None,
        margem_centavos=receita_com_custo - custo if tem_margem else None,
        margem_percentual=_percentual(receita_com_custo - custo, receita_com_custo)
        if tem_margem
        else None,
        produtos_sem_custo=len(dados) - len(completas),
        receita_sem_custo_centavos=receita - receita_com_custo,
        motivo=motivo,
    )

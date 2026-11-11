"""Estoque pela API: saldos, ajuste com motivo, contagem e histórico. Só o gerente."""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import acesso, db, dinheiro, estoque, tempo
from app.models import MovimentoEstoque, Operador, Produto, TipoMovimentoEstoque
from app.operadores import RegraError
from app.pesquisa import sem_acento

router = APIRouter(tags=["estoque"], dependencies=[Depends(acesso.exigir_gerente)])
log = logging.getLogger("moleka.estoque")


class ItemEstoqueOut(BaseModel):
    produto_id: int
    codigo: str
    descricao: str
    categoria: str | None
    unidade: str
    saldo: Decimal
    estoque_minimo: Decimal
    situacao: str  # ok, abaixo (do mínimo), zerado ou negativo
    custo_centavos: int | None  # custo médio
    ultimo_custo_centavos: int | None
    valor_centavos: int | None  # saldo × custo médio; None sem custo ou sem saldo positivo
    ativo: bool


class ResumoEstoqueOut(BaseModel):
    produtos: int  # produtos ativos
    com_saldo: int
    abaixo_do_minimo: int
    negativos: int
    valor_centavos: int | None  # None = nenhum produto com saldo tem custo
    sem_custo: int  # produtos com saldo e sem custo (ficam fora do valor)
    motivo_do_valor: str


class EstoqueOut(BaseModel):
    itens: list[ItemEstoqueOut]
    resumo: ResumoEstoqueOut


class AjusteIn(BaseModel):
    produto_id: int
    tipo: str  # entrada ou saida
    quantidade: str | int | float
    motivo: str = ""
    custo_unitario_centavos: int | None = None  # só na entrada, opcional


class ContagemIn(BaseModel):
    produto_id: int
    contado: str | int | float
    motivo: str = ""


class ContagemOut(BaseModel):
    item: ItemEstoqueOut
    saldo_antes: Decimal
    diferenca: Decimal


class MovimentoOut(BaseModel):
    id: int
    em: str | None
    tipo: TipoMovimentoEstoque
    rotulo: str
    quantidade: Decimal
    saldo_depois: Decimal
    custo_unitario_centavos: int | None
    motivo: str | None
    referencia: str | None
    operador: str | None


def _decimal(valor: str | int | float, campo: str) -> Decimal:
    try:
        return Decimal(str(valor).strip().replace(",", "."))
    except (InvalidOperation, ValueError) as erro:
        raise RegraError(f"{campo} inválida.") from erro


def _situacao(saldo: Decimal, minimo: Decimal) -> str:
    if saldo < 0:
        return "negativo"
    if minimo > 0 and saldo < minimo:
        return "abaixo"
    return "zerado" if saldo == 0 else "ok"


def item_out(produto: Produto, saldo: Decimal) -> ItemEstoqueOut:
    minimo = Decimal(produto.estoque_minimo)
    valor = None
    if produto.custo_centavos is not None and saldo > 0:
        valor = dinheiro.multiplicar(produto.custo_centavos, saldo)
    return ItemEstoqueOut(
        produto_id=produto.id,
        codigo=produto.codigo,
        descricao=produto.descricao,
        categoria=produto.categoria,
        unidade=produto.unidade,
        saldo=saldo,
        estoque_minimo=minimo,
        situacao=_situacao(saldo, minimo),
        custo_centavos=produto.custo_centavos,
        ultimo_custo_centavos=produto.ultimo_custo_centavos,
        valor_centavos=valor,
        ativo=produto.ativo,
    )


def _resumo(itens: list[ItemEstoqueOut]) -> ResumoEstoqueOut:
    ativos = [i for i in itens if i.ativo]
    com_saldo = [i for i in ativos if i.saldo > 0]
    com_valor = [i.valor_centavos for i in com_saldo if i.valor_centavos is not None]
    sem_custo = len(com_saldo) - len(com_valor)
    if not com_saldo:
        motivo = "nenhum produto com saldo"
    elif not com_valor:
        motivo = "os produtos com saldo estão sem custo cadastrado"
    elif sem_custo:
        motivo = f"{sem_custo} produto(s) com saldo estão sem custo e ficaram fora desta soma"
    else:
        motivo = ""
    return ResumoEstoqueOut(
        produtos=len(ativos),
        com_saldo=len(com_saldo),
        abaixo_do_minimo=sum(1 for i in ativos if i.situacao == "abaixo"),
        negativos=sum(1 for i in ativos if i.situacao == "negativo"),
        valor_centavos=sum(com_valor) if com_valor else None,
        sem_custo=sem_custo,
        motivo_do_valor=motivo,
    )


def _produto(sessao: Session, produto_id: int) -> Produto:
    produto = sessao.get(Produto, produto_id)
    if produto is None:
        raise HTTPException(404, "Produto não encontrado.")
    return produto


@router.get("/estoque", response_model=EstoqueOut)
def ver_estoque(
    busca: str | None = None,
    situacao: str | None = None,  # abaixo, negativo, com_saldo
    inativos: bool = False,
    sessao: Session = Depends(db.sessao),
) -> EstoqueOut:
    saldos = estoque.saldos(sessao)
    produtos = sessao.scalars(select(Produto).order_by(func.sem_acento(Produto.descricao)))
    todos = [item_out(p, saldos.get(p.id, Decimal("0.000"))) for p in produtos]
    resumo = _resumo(todos)
    termo = sem_acento(busca.strip()) if busca and busca.strip() else ""
    itens = []
    for item in todos:
        if not item.ativo and not inativos:
            continue
        if termo and not any(
            termo in sem_acento(campo) for campo in (item.descricao, item.codigo, item.categoria)
        ):
            continue
        if situacao == "abaixo" and item.situacao != "abaixo":
            continue
        if situacao == "negativo" and item.situacao != "negativo":
            continue
        if situacao == "com_saldo" and item.saldo <= 0:
            continue
        itens.append(item)
    return EstoqueOut(itens=itens, resumo=resumo)


@router.post("/estoque/ajustes", response_model=ItemEstoqueOut, status_code=201)
def ajustar(
    dados: AjusteIn,
    sessao: Session = Depends(db.sessao),
    gerente: Operador = Depends(acesso.exigir_gerente),
) -> ItemEstoqueOut:
    if dados.tipo not in ("entrada", "saida"):
        raise RegraError("Escolha entrada ou saída.")
    produto = _produto(sessao, dados.produto_id)
    estoque.ajustar(
        sessao,
        gerente,
        produto,
        entrada=dados.tipo == "entrada",
        quantidade=_decimal(dados.quantidade, "Quantidade"),
        motivo=dados.motivo,
        custo_unitario_centavos=dados.custo_unitario_centavos,
    )
    sessao.commit()
    return item_out(produto, estoque.saldo(sessao, produto.id))


@router.post("/estoque/contagens", response_model=ContagemOut, status_code=201)
def contar(
    dados: ContagemIn,
    sessao: Session = Depends(db.sessao),
    gerente: Operador = Depends(acesso.exigir_gerente),
) -> ContagemOut:
    produto = _produto(sessao, dados.produto_id)
    contagem = estoque.contar(
        sessao, gerente, produto, _decimal(dados.contado, "Quantidade contada"), dados.motivo
    )
    sessao.commit()
    return ContagemOut(
        item=item_out(produto, estoque.saldo(sessao, produto.id)),
        saldo_antes=contagem.saldo_antes,
        diferenca=contagem.diferenca,
    )


@router.get("/estoque/{produto_id}/movimentos", response_model=list[MovimentoOut])
def movimentos(
    produto_id: int, limite: int = 100, sessao: Session = Depends(db.sessao)
) -> list[MovimentoOut]:
    """Os últimos movimentos do produto, do mais novo para o mais antigo, com o saldo depois."""
    produto = _produto(sessao, produto_id)
    linhas = sessao.execute(
        select(MovimentoEstoque, Operador.nome)
        .outerjoin(Operador, Operador.id == MovimentoEstoque.operador_id)
        .where(MovimentoEstoque.produto_id == produto.id)
        .order_by(MovimentoEstoque.id.desc())
        .limit(max(1, min(limite, 500)))
    )
    saldo = estoque.saldo(sessao, produto.id)
    saida = []
    for movimento, nome in linhas:
        quantidade = Decimal(movimento.quantidade)
        saida.append(
            MovimentoOut(
                id=movimento.id,
                em=tempo.iso_na_loja(movimento.em),
                tipo=movimento.tipo,
                rotulo=estoque.ROTULOS[movimento.tipo],
                quantidade=quantidade,
                saldo_depois=saldo,
                custo_unitario_centavos=movimento.custo_unitario_centavos,
                motivo=movimento.motivo,
                referencia=movimento.referencia,
                operador=nome,
            )
        )
        saldo -= quantidade
    return saida

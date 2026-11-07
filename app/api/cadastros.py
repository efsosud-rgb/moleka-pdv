"""Cadastros básicos: produtos, clientes e tabelas de preço (listar e criar).

Edição, inativação e importação entram nas próximas frentes. Preços entram em centavos.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import db
from app.models import Cliente, PrecoProduto, Produto, TabelaPreco

router = APIRouter(tags=["cadastros"])


# ---------------------------------------------------------------- tabelas de preço


class TabelaPrecoOut(BaseModel):
    id: int
    nome: str
    padrao: bool
    ativo: bool


class TabelaPrecoIn(BaseModel):
    nome: str = Field(min_length=1, max_length=40)
    padrao: bool = False


@router.get("/tabelas-preco", response_model=list[TabelaPrecoOut])
def listar_tabelas(sessao: Session = Depends(db.sessao)) -> list[TabelaPreco]:
    return list(sessao.scalars(select(TabelaPreco).order_by(TabelaPreco.nome)))


@router.post("/tabelas-preco", response_model=TabelaPrecoOut, status_code=201)
def criar_tabela(dados: TabelaPrecoIn, sessao: Session = Depends(db.sessao)) -> TabelaPreco:
    nome = dados.nome.strip().upper()
    if sessao.scalar(select(TabelaPreco).where(TabelaPreco.nome == nome)):
        raise HTTPException(409, f"já existe a tabela {nome}")
    if dados.padrao:
        for t in sessao.scalars(select(TabelaPreco).where(TabelaPreco.padrao.is_(True))):
            t.padrao = False
    tabela = TabelaPreco(nome=nome, padrao=dados.padrao)
    sessao.add(tabela)
    sessao.commit()
    return tabela


# ---------------------------------------------------------------- produtos


class FaixaIn(BaseModel):
    tabela_id: int
    qtd_min: Decimal = Field(default=Decimal("1"), gt=0)
    preco_centavos: int = Field(ge=0)


class FaixaOut(BaseModel):
    tabela_id: int
    qtd_min: Decimal
    preco_centavos: int


class ProdutoIn(BaseModel):
    codigo: str = Field(min_length=1, max_length=30)
    descricao: str = Field(min_length=1, max_length=120)
    ean: str | None = Field(default=None, max_length=14)
    unidade: str = Field(default="UN", max_length=6)
    ncm: str | None = Field(default=None, max_length=8)
    cest: str | None = Field(default=None, max_length=7)
    cst_csosn: str | None = Field(default=None, max_length=4)
    origem: str = Field(default="0", max_length=1)
    custo_centavos: int | None = Field(default=None, ge=0)
    estoque_minimo: Decimal = Field(default=Decimal("0"), ge=0)
    precos: list[FaixaIn] = Field(default_factory=list)


class ProdutoOut(BaseModel):
    id: int
    codigo: str
    descricao: str
    ean: str | None
    unidade: str
    ncm: str | None
    cest: str | None
    cst_csosn: str | None
    origem: str
    custo_centavos: int | None
    estoque_minimo: Decimal
    ativo: bool
    precos: list[FaixaOut]


@router.get("/produtos", response_model=list[ProdutoOut])
def listar_produtos(
    busca: str | None = None, sessao: Session = Depends(db.sessao)
) -> list[Produto]:
    consulta = select(Produto).where(Produto.ativo.is_(True)).order_by(Produto.descricao)
    if busca:
        termo = f"%{busca.strip()}%"
        consulta = consulta.where(
            Produto.descricao.ilike(termo) | Produto.codigo.ilike(termo) | Produto.ean.ilike(termo)
        )
    return list(sessao.scalars(consulta))


@router.post("/produtos", response_model=ProdutoOut, status_code=201)
def criar_produto(dados: ProdutoIn, sessao: Session = Depends(db.sessao)) -> Produto:
    codigo = dados.codigo.strip()
    if sessao.scalar(select(Produto).where(Produto.codigo == codigo)):
        raise HTTPException(409, f"já existe produto com o código {codigo}")
    for faixa in dados.precos:
        if sessao.get(TabelaPreco, faixa.tabela_id) is None:
            raise HTTPException(422, f"tabela de preço {faixa.tabela_id} não existe")
    produto = Produto(
        codigo=codigo,
        descricao=dados.descricao.strip(),
        ean=dados.ean,
        unidade=dados.unidade.upper(),
        ncm=dados.ncm,
        cest=dados.cest,
        cst_csosn=dados.cst_csosn,
        origem=dados.origem,
        custo_centavos=dados.custo_centavos,
        estoque_minimo=dados.estoque_minimo,
    )
    produto.precos = [
        PrecoProduto(tabela_id=f.tabela_id, qtd_min=f.qtd_min, preco_centavos=f.preco_centavos)
        for f in dados.precos
    ]
    sessao.add(produto)
    sessao.commit()
    sessao.refresh(produto)
    return produto


# ---------------------------------------------------------------- clientes


class ClienteIn(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    cpf_cnpj: str | None = Field(default=None, max_length=14)
    telefone: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=120)
    endereco: str | None = Field(default=None, max_length=200)
    tabela_id: int | None = None
    observacao: str | None = None


class ClienteOut(ClienteIn):
    id: int
    ativo: bool


@router.get("/clientes", response_model=list[ClienteOut])
def listar_clientes(
    busca: str | None = None, sessao: Session = Depends(db.sessao)
) -> list[Cliente]:
    consulta = select(Cliente).where(Cliente.ativo.is_(True)).order_by(Cliente.nome)
    if busca:
        termo = f"%{busca.strip()}%"
        consulta = consulta.where(Cliente.nome.ilike(termo) | Cliente.cpf_cnpj.ilike(termo))
    return list(sessao.scalars(consulta))


@router.post("/clientes", response_model=ClienteOut, status_code=201)
def criar_cliente(dados: ClienteIn, sessao: Session = Depends(db.sessao)) -> Cliente:
    if dados.tabela_id is not None and sessao.get(TabelaPreco, dados.tabela_id) is None:
        raise HTTPException(422, f"tabela de preço {dados.tabela_id} não existe")
    cliente = Cliente(**dados.model_dump())
    cliente.nome = cliente.nome.strip()
    sessao.add(cliente)
    sessao.commit()
    return cliente

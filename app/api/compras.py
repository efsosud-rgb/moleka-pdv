"""Entrada de NF por XML pela API: conferir (não grava), importar, listar e estornar.

Só o gerente.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import acesso, compras, db, documentos, nfe_xml, tempo
from app.models import NotaEntrada, NotaEntradaItem, Operador

router = APIRouter(tags=["compras"], dependencies=[Depends(acesso.exigir_gerente)])


class ItemLidoOut(BaseModel):
    numero: int
    codigo: str
    ean: str | None
    descricao: str
    ncm: str | None
    unidade: str
    quantidade: Decimal
    valor_unitario_centavos: int
    valor_total_centavos: int
    custo_total_centavos: int  # com desconto, frete, IPI e ICMS-ST do item
    unidade_tributavel: str | None
    fator_da_nota: Decimal | None  # quando a nota informa (ex.: CX com 24 UN)
    sugestao_produto_id: int | None
    sugestao_descricao: str | None
    sugestao_fator: Decimal
    sugestao_origem: str | None  # memoria (ligado antes) ou ean (código de barras)


class ParcelaOut(BaseModel):
    numero: str
    vencimento: date
    valor_centavos: int


class NotaLidaOut(BaseModel):
    chave: str
    numero: int
    serie: int
    emitida_em: str | None
    natureza: str | None
    fornecedor_documento: str
    fornecedor_nome: str
    destinatario_documento: str | None
    destinatario_nome: str | None
    total_centavos: int
    custo_dos_itens_centavos: int
    autorizada: bool | None
    itens: list[ItemLidoOut]
    parcelas: list[ParcelaOut]
    avisos: list[str]
    ja_importada: bool
    importada_em: str | None


class XmlIn(BaseModel):
    xml: str = Field(max_length=nfe_xml.TAMANHO_MAXIMO)


class DecisaoIn(BaseModel):
    numero: int
    acao: str  # vincular, criar ou ignorar
    produto_id: int | None = None
    fator: Decimal = Decimal("1")


class ImportarIn(BaseModel):
    xml: str = Field(max_length=nfe_xml.TAMANHO_MAXIMO)
    itens: list[DecisaoIn]
    gerar_contas: bool = True
    categoria_id: int | None = None  # categoria das contas a pagar (vazio = compra p/ revenda)
    # Nota sem parcelas: preenchido, cria uma conta com o total da nota neste vencimento.
    vencimento_sem_parcelas: date | None = None


class ItemNotaOut(BaseModel):
    numero: int | None
    codigo_fornecedor: str
    descricao: str
    unidade: str
    quantidade: Decimal
    valor_total_centavos: int
    custo_total_centavos: int
    fator_conversao: Decimal
    produto_id: int | None
    produto_codigo: str | None
    produto_descricao: str | None
    entrou: Decimal | None  # quantidade que entrou no estoque (None = não deu entrada)
    custo_unitario_centavos: int | None


class NotaOut(BaseModel):
    id: int
    chave: str
    numero: int
    serie: int
    fornecedor_documento: str
    fornecedor_nome: str
    emitida_em: str | None
    importada_em: str | None
    total_centavos: int
    itens_quantidade: int
    contas_a_pagar: int  # contas em aberto ou pagas, nascidas desta nota
    estornada_em: str | None
    motivo_estorno: str | None
    itens: list[ItemNotaOut] = []


class ProdutoCriadoOut(BaseModel):
    id: int
    codigo: str
    descricao: str


class ImportacaoOut(BaseModel):
    nota: NotaOut
    produtos_criados: list[ProdutoCriadoOut]
    contas_a_pagar: int


class EstornoIn(BaseModel):
    motivo: str = ""


class EstornoOut(BaseModel):
    nota: NotaOut
    # Produtos cujo custo médio o estorno não conseguiu refazer: o gerente confere em Produtos.
    custos_para_conferir: list[str]


def _item_out(item: NotaEntradaItem) -> ItemNotaOut:
    entrou = None
    custo = None
    if item.produto is not None:
        entrou = compras.quantidade_que_entra(
            Decimal(item.quantidade), Decimal(item.fator_conversao)
        )
        custo = compras.custo_por_unidade(item.custo_total_centavos, entrou)
    return ItemNotaOut(
        numero=item.numero,
        codigo_fornecedor=item.codigo_fornecedor,
        descricao=item.descricao,
        unidade=item.unidade,
        quantidade=Decimal(item.quantidade),
        valor_total_centavos=item.valor_total_centavos,
        custo_total_centavos=item.custo_total_centavos,
        fator_conversao=Decimal(item.fator_conversao),
        produto_id=item.produto_id,
        produto_codigo=item.produto.codigo if item.produto else None,
        produto_descricao=item.produto.descricao if item.produto else None,
        entrou=entrou,
        custo_unitario_centavos=custo,
    )


def nota_out(sessao: Session, nota: NotaEntrada, *, com_itens: bool = False) -> NotaOut:
    return NotaOut(
        id=nota.id,
        chave=nota.chave,
        numero=nota.numero,
        serie=nota.serie,
        fornecedor_documento=documentos.formatar(nota.fornecedor_cnpj),
        fornecedor_nome=nota.fornecedor_nome,
        emitida_em=tempo.iso_na_loja(nota.emitida_em),
        importada_em=tempo.iso_na_loja(nota.importada_em),
        total_centavos=nota.total_centavos,
        itens_quantidade=len(nota.itens),
        contas_a_pagar=len(compras.contas_da_nota(sessao, nota)),
        estornada_em=tempo.iso_na_loja(nota.estornada_em),
        motivo_estorno=nota.motivo_estorno,
        itens=[_item_out(i) for i in nota.itens] if com_itens else [],
    )


@router.post("/compras/conferir", response_model=NotaLidaOut)
def conferir(dados: XmlIn, sessao: Session = Depends(db.sessao)) -> NotaLidaOut:
    """Lê o XML e sugere o produto de cada item. Não grava nada."""
    nota = nfe_xml.ler(dados.xml)
    sugestoes = compras.sugerir(sessao, nota)
    anterior = compras.ja_importada(sessao, nota.chave)
    em_vigor = anterior is not None and anterior.estornada_em is None
    itens = []
    for item in nota.itens:
        sugestao = sugestoes[item.numero]
        itens.append(
            ItemLidoOut(
                numero=item.numero,
                codigo=item.codigo,
                ean=item.ean,
                descricao=item.descricao,
                ncm=item.ncm,
                unidade=item.unidade,
                quantidade=item.quantidade,
                valor_unitario_centavos=item.valor_unitario_centavos,
                valor_total_centavos=item.valor_total_centavos,
                custo_total_centavos=item.custo_total_centavos,
                unidade_tributavel=item.unidade_tributavel,
                fator_da_nota=item.fator_da_nota,
                sugestao_produto_id=sugestao.produto.id if sugestao.produto else None,
                sugestao_descricao=sugestao.produto.descricao if sugestao.produto else None,
                sugestao_fator=sugestao.fator,
                sugestao_origem=sugestao.origem,
            )
        )
    return NotaLidaOut(
        chave=nota.chave,
        numero=nota.numero,
        serie=nota.serie,
        emitida_em=tempo.iso_na_loja(nota.emitida_em),
        natureza=nota.natureza,
        fornecedor_documento=documentos.formatar(nota.emitente_documento),
        fornecedor_nome=nota.emitente_nome,
        destinatario_documento=documentos.formatar(nota.destinatario_documento)
        if nota.destinatario_documento
        else None,
        destinatario_nome=nota.destinatario_nome,
        total_centavos=nota.total_centavos,
        custo_dos_itens_centavos=nota.custo_dos_itens_centavos,
        autorizada=nota.autorizada,
        itens=itens,
        parcelas=[
            ParcelaOut(numero=p.numero, vencimento=p.vencimento, valor_centavos=p.valor_centavos)
            for p in nota.parcelas
        ],
        avisos=list(nota.avisos),
        ja_importada=em_vigor,
        importada_em=tempo.iso_na_loja(anterior.importada_em) if anterior and em_vigor else None,
    )


@router.post("/compras/importar", response_model=ImportacaoOut, status_code=201)
def importar(
    dados: ImportarIn,
    sessao: Session = Depends(db.sessao),
    gerente: Operador = Depends(acesso.exigir_gerente),
) -> ImportacaoOut:
    decisoes = [
        compras.Decisao(numero=d.numero, acao=d.acao, produto_id=d.produto_id, fator=d.fator)
        for d in dados.itens
    ]
    feito = compras.importar(
        sessao,
        gerente,
        dados.xml,
        decisoes,
        gerar_contas=dados.gerar_contas,
        categoria_id=dados.categoria_id,
        vencimento_sem_parcelas=dados.vencimento_sem_parcelas,
    )
    return ImportacaoOut(
        nota=nota_out(sessao, feito.nota, com_itens=True),
        produtos_criados=[
            ProdutoCriadoOut(id=p.id, codigo=p.codigo, descricao=p.descricao)
            for p in feito.produtos_criados
        ],
        contas_a_pagar=feito.contas_a_pagar,
    )


@router.get("/compras", response_model=list[NotaOut])
def listar(limite: int = 100, sessao: Session = Depends(db.sessao)) -> list[NotaOut]:
    notas = sessao.scalars(
        select(NotaEntrada)
        .order_by(NotaEntrada.importada_em.desc())
        .limit(max(1, min(limite, 500)))
    )
    return [nota_out(sessao, n) for n in notas]


def _nota(sessao: Session, nota_id: int) -> NotaEntrada:
    nota = sessao.get(NotaEntrada, nota_id)
    if nota is None:
        raise HTTPException(404, "Nota não encontrada.")
    return nota


@router.get("/compras/{nota_id}", response_model=NotaOut)
def ver(nota_id: int, sessao: Session = Depends(db.sessao)) -> NotaOut:
    return nota_out(sessao, _nota(sessao, nota_id), com_itens=True)


@router.post("/compras/{nota_id}/estornar", response_model=EstornoOut)
def estornar(
    nota_id: int,
    dados: EstornoIn,
    sessao: Session = Depends(db.sessao),
    gerente: Operador = Depends(acesso.exigir_gerente),
) -> EstornoOut:
    nota = _nota(sessao, nota_id)
    conferir = compras.estornar(sessao, gerente, nota, dados.motivo)
    sessao.refresh(nota)
    return EstornoOut(
        nota=nota_out(sessao, nota, com_itens=True),
        custos_para_conferir=[p.descricao for p in conferir],
    )

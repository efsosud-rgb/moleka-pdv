"""Impressão dos documentos do dia a dia: comprovante de venda e resumo do caixa.

Vale para qualquer operador que entrou no sistema. Cada documento tem duas rotas: uma devolve
as linhas (para ver na tela) e a outra manda para a impressora de cupom. As linhas são as
mesmas nas duas.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import acesso, config, configuracoes, cupom, db, documentos, impressao, tempo
from app import caixa as regras_do_caixa
from app.models import Operador, SessaoCaixa, StatusVenda, Venda
from app.operadores import RegraError

router = APIRouter(tags=["impressão"])


class LinhaOut(BaseModel):
    texto: str
    negrito: bool
    grande: bool


class CupomOut(BaseModel):
    titulo: str
    colunas: int
    linhas: list[LinhaOut]
    pode_imprimir: bool
    motivo: str  # por que não dá para imprimir agora


class ImpressoOut(BaseModel):
    impressora: str
    vias: int


def _cupom_out(sessao: Session, documento: cupom.Cupom) -> CupomOut:
    pode, motivo = impressao.situacao(sessao)
    return CupomOut(
        titulo=documento.titulo,
        colunas=documento.colunas,
        linhas=[
            LinhaOut(texto=x.texto, negrito=x.negrito, grande=x.grande) for x in documento.linhas
        ],
        pode_imprimir=pode,
        motivo=motivo,
    )


def _impresso(opcoes: configuracoes.Impressao, vias: int | None = None) -> ImpressoOut:
    return ImpressoOut(impressora=opcoes.impressora, vias=vias or opcoes.vias)


# ---------------------------------------------------------------- relatórios em folha comum


class CabecalhoOut(BaseModel):
    """O que vai no alto e no pé dos relatórios impressos em impressora comum (A4)."""

    loja: str  # nome da loja em Configurações; vazio = ainda não preenchido
    cnpj: str  # com a pontuação; vazio = não preenchido
    operador: str
    versao: str
    agora: str  # data e hora da loja, para o "impresso em"


@router.get("/impressao/cabecalho", response_model=CabecalhoOut)
def cabecalho_dos_relatorios(
    sessao: Session = Depends(db.sessao),
    operador: Operador = Depends(acesso.exigir_operador),
) -> CabecalhoOut:
    loja = configuracoes.ler_loja(sessao)
    return CabecalhoOut(
        loja=loja.nome_fantasia or loja.razao_social,
        cnpj=documentos.formatar(loja.cnpj),
        operador=operador.nome,
        versao=config.VERSAO,
        agora=tempo.iso_na_loja(tempo.agora()) or "",
    )


# ---------------------------------------------------------------- comprovante de venda


def _comprovante(sessao: Session, venda_id: int) -> cupom.Cupom:
    venda = sessao.get(Venda, venda_id)
    if venda is None:
        raise HTTPException(404, "Venda não encontrada.")
    if venda.status == StatusVenda.ABERTA:
        raise RegraError("Esta venda ainda está aberta: finalize antes de imprimir.", status=409)
    return cupom.comprovante_de_venda(
        configuracoes.ler_loja(sessao),
        venda,
        configuracoes.ler_impressao(sessao).colunas,
        versao=config.VERSAO,
    )


@router.get("/vendas/{venda_id}/comprovante", response_model=CupomOut)
def ver_comprovante(venda_id: int, sessao: Session = Depends(db.sessao)) -> CupomOut:
    return _cupom_out(sessao, _comprovante(sessao, venda_id))


@router.post("/vendas/{venda_id}/imprimir", response_model=ImpressoOut)
def imprimir_comprovante(venda_id: int, sessao: Session = Depends(db.sessao)) -> ImpressoOut:
    """Imprime (ou reimprime) o comprovante. Aqui a gaveta não abre: ela abre na hora da venda."""
    return _impresso(impressao.imprimir(sessao, _comprovante(sessao, venda_id)))


# ---------------------------------------------------------------- resumo do caixa


def _sessao_de_caixa(sessao: Session, operador: Operador, sessao_id: int | None) -> SessaoCaixa:
    """A sessão aberta (qualquer operador) ou uma já fechada (o gerente, ou quem a fechou)."""
    if sessao_id is None:
        return regras_do_caixa.exigir_aberta(sessao)
    sessao_caixa = sessao.get(SessaoCaixa, sessao_id)
    if sessao_caixa is None:
        raise HTTPException(404, "Caixa não encontrado.")
    aberta = sessao_caixa.fechado_em is None
    if not (aberta or acesso.e_gerente(operador) or sessao_caixa.fechado_por_id == operador.id):
        raise HTTPException(403, "Só o gerente imprime os fechamentos anteriores.")
    return sessao_caixa


def _resumo(sessao: Session, operador: Operador, sessao_id: int | None) -> cupom.Cupom:
    return cupom.fechamento_de_caixa(
        configuracoes.ler_loja(sessao),
        sessao,
        _sessao_de_caixa(sessao, operador, sessao_id),
        configuracoes.ler_impressao(sessao).colunas,
        versao=config.VERSAO,
    )


@router.get("/caixa/resumo-impresso", response_model=CupomOut)
def ver_resumo_do_caixa(
    sessao_id: int | None = None,
    sessao: Session = Depends(db.sessao),
    operador: Operador = Depends(acesso.exigir_operador),
) -> CupomOut:
    return _cupom_out(sessao, _resumo(sessao, operador, sessao_id))


class ResumoIn(BaseModel):
    sessao_id: int | None = None  # vazio = o caixa aberto agora


@router.post("/caixa/imprimir", response_model=ImpressoOut)
def imprimir_resumo_do_caixa(
    dados: ResumoIn,
    sessao: Session = Depends(db.sessao),
    operador: Operador = Depends(acesso.exigir_operador),
) -> ImpressoOut:
    documento = _resumo(sessao, operador, dados.sessao_id)
    return _impresso(impressao.imprimir(sessao, documento, vias=1), vias=1)

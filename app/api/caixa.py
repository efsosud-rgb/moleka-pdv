"""Controle de caixa pela API: situação, abrir, sangria, suprimento, fechar e histórico.

Qualquer operador abre e fecha o caixa e registra sangria e suprimento; tudo fica gravado com
o nome de quem fez. O histórico dos fechamentos é do gerente.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import acesso, db, tempo
from app import caixa as regras
from app.models import FormaPagamento, Operador, SessaoCaixa, TipoMovimentoCaixa

router = APIRouter(tags=["caixa"])


class FormaOut(BaseModel):
    forma: FormaPagamento
    rotulo: str
    recebido_centavos: int  # entrou nas vendas desta sessão
    esperado_centavos: int  # o que deve existir (no dinheiro, conta fundo, suprimento e sangria)
    contado_centavos: int | None = None  # informado no fechamento
    diferenca_centavos: int | None = None  # contado - esperado


class MovimentoOut(BaseModel):
    id: int
    tipo: TipoMovimentoCaixa
    valor_centavos: int
    motivo: str | None
    em: str | None


class SessaoOut(BaseModel):
    id: int
    caixa: str
    operador: str
    aberto_em: str | None
    fechado_em: str | None
    fechado_por: str | None
    fundo_troco_centavos: int
    suprimentos_centavos: int
    sangrias_centavos: int
    vendas_quantidade: int
    vendas_total_centavos: int
    dinheiro_esperado_centavos: int
    formas: list[FormaOut]
    movimentos: list[MovimentoOut]
    observacao: str | None


class SituacaoOut(BaseModel):
    aberto: bool
    sessao: SessaoOut | None


class AbrirIn(BaseModel):
    fundo_troco_centavos: int = 0


class MovimentoIn(BaseModel):
    tipo: TipoMovimentoCaixa
    valor_centavos: int
    motivo: str = ""


class FecharIn(BaseModel):
    contado: dict[FormaPagamento, int]
    observacao: str | None = None


def sessao_out(sessao: Session, sessao_caixa: SessaoCaixa) -> SessaoOut:
    numeros = regras.totais(sessao, sessao_caixa)
    conferido = {c.forma: c for c in sessao_caixa.conferencias}
    formas = []
    for forma in FormaPagamento:
        linha = conferido.get(forma)
        # Depois de fechado, vale o esperado gravado no fechamento (retrato daquele momento).
        esperado = linha.esperado_centavos if linha else numeros.esperado(forma)
        formas.append(
            FormaOut(
                forma=forma,
                rotulo=regras.ROTULOS[forma],
                recebido_centavos=numeros.recebido.get(forma, 0),
                esperado_centavos=esperado,
                contado_centavos=linha.contado_centavos if linha else None,
                diferenca_centavos=linha.contado_centavos - esperado if linha else None,
            )
        )
    return SessaoOut(
        id=sessao_caixa.id,
        caixa=sessao_caixa.caixa.nome,
        operador=sessao_caixa.operador.nome,
        aberto_em=tempo.iso_na_loja(sessao_caixa.aberto_em),
        fechado_em=tempo.iso_na_loja(sessao_caixa.fechado_em),
        fechado_por=sessao_caixa.fechado_por.nome if sessao_caixa.fechado_por else None,
        fundo_troco_centavos=numeros.fundo,
        suprimentos_centavos=numeros.suprimentos,
        sangrias_centavos=numeros.sangrias,
        vendas_quantidade=numeros.vendas_quantidade,
        vendas_total_centavos=numeros.vendas_total,
        dinheiro_esperado_centavos=numeros.dinheiro_esperado,
        formas=formas,
        movimentos=[
            MovimentoOut(
                id=m.id,
                tipo=m.tipo,
                valor_centavos=m.valor_centavos,
                motivo=m.motivo,
                em=tempo.iso_na_loja(m.em),
            )
            for m in sessao_caixa.movimentos
        ],
        observacao=sessao_caixa.observacao,
    )


@router.get("/caixa", response_model=SituacaoOut)
def situacao(sessao: Session = Depends(db.sessao)) -> SituacaoOut:
    aberta = regras.aberta(sessao)
    return SituacaoOut(
        aberto=aberta is not None, sessao=sessao_out(sessao, aberta) if aberta else None
    )


@router.post("/caixa/abrir", response_model=SituacaoOut, status_code=201)
def abrir(
    dados: AbrirIn,
    sessao: Session = Depends(db.sessao),
    operador: Operador = Depends(acesso.exigir_operador),
) -> SituacaoOut:
    aberta = regras.abrir(sessao, operador, dados.fundo_troco_centavos)
    return SituacaoOut(aberto=True, sessao=sessao_out(sessao, aberta))


@router.post("/caixa/movimentos", response_model=SituacaoOut, status_code=201)
def movimentar(
    dados: MovimentoIn,
    sessao: Session = Depends(db.sessao),
    operador: Operador = Depends(acesso.exigir_operador),
) -> SituacaoOut:
    regras.movimentar(sessao, operador, dados.tipo, dados.valor_centavos, dados.motivo)
    aberta = regras.exigir_aberta(sessao)
    sessao.refresh(aberta)
    return SituacaoOut(aberto=True, sessao=sessao_out(sessao, aberta))


@router.post("/caixa/fechar", response_model=SessaoOut)
def fechar(
    dados: FecharIn,
    sessao: Session = Depends(db.sessao),
    operador: Operador = Depends(acesso.exigir_operador),
) -> SessaoOut:
    fechada = regras.fechar(sessao, operador, dados.contado, dados.observacao)
    sessao.refresh(fechada)
    return sessao_out(sessao, fechada)


@router.get("/caixa/historico", response_model=list[SessaoOut])
def historico(
    limite: int = 20,
    sessao: Session = Depends(db.sessao),
    _gerente: Operador = Depends(acesso.exigir_gerente),
) -> list[SessaoOut]:
    fechadas = sessao.scalars(
        select(SessaoCaixa)
        .where(SessaoCaixa.fechado_em.is_not(None))
        .order_by(SessaoCaixa.id.desc())
        .limit(max(1, min(limite, 100)))
    )
    return [sessao_out(sessao, s) for s in fechadas]

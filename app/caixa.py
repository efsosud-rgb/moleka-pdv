"""Controle de caixa: abertura com fundo de troco, sangria, suprimento e fechamento.

Uma "sessão de caixa" vai da abertura ao fechamento. Só existe uma aberta por vez (um caixa
na loja, nesta versão). Tudo o que entra e sai fica registrado com valor, motivo e hora.

Dinheiro esperado na gaveta = fundo de troco + vendas em dinheiro + suprimentos - sangrias.
Nas outras formas (Pix, débito, crédito), o esperado é o que foi recebido nas vendas.
Venda cancelada não entra na conta.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import tempo
from app.models import (
    Caixa,
    ConferenciaCaixa,
    FormaPagamento,
    MovimentoCaixa,
    Operador,
    Pagamento,
    SessaoCaixa,
    StatusVenda,
    TipoMovimentoCaixa,
    Venda,
)
from app.operadores import RegraError

log = logging.getLogger("moleka.caixa")

ROTULOS: dict[FormaPagamento, str] = {
    FormaPagamento.DINHEIRO: "Dinheiro",
    FormaPagamento.PIX: "Pix",
    FormaPagamento.DEBITO: "Débito",
    FormaPagamento.CREDITO: "Crédito",
}


@dataclass
class Totais:
    """Os números de uma sessão de caixa, todos em centavos e vindos do banco."""

    fundo: int = 0
    suprimentos: int = 0
    sangrias: int = 0
    vendas_quantidade: int = 0
    vendas_total: int = 0
    recebido: dict[FormaPagamento, int] = field(default_factory=dict)

    @property
    def dinheiro_esperado(self) -> int:
        dinheiro = self.recebido.get(FormaPagamento.DINHEIRO, 0)
        return self.fundo + dinheiro + self.suprimentos - self.sangrias

    def esperado(self, forma: FormaPagamento) -> int:
        if forma == FormaPagamento.DINHEIRO:
            return self.dinheiro_esperado
        return self.recebido.get(forma, 0)


def terminal(sessao: Session) -> Caixa:
    """O caixa da loja. Nesta versão há um só; é criado na primeira vez."""
    caixa = sessao.scalar(select(Caixa).where(Caixa.ativo.is_(True)).order_by(Caixa.id))
    if caixa is None:
        caixa = Caixa(nome="Caixa 01")
        sessao.add(caixa)
        sessao.flush()
    return caixa


def aberta(sessao: Session) -> SessaoCaixa | None:
    return sessao.scalar(
        select(SessaoCaixa).where(SessaoCaixa.fechado_em.is_(None)).order_by(SessaoCaixa.id.desc())
    )


def exigir_aberta(sessao: Session) -> SessaoCaixa:
    sessao_caixa = aberta(sessao)
    if sessao_caixa is None:
        raise RegraError("O caixa está fechado. Abra o caixa primeiro.", status=409)
    return sessao_caixa


def totais(sessao: Session, sessao_caixa: SessaoCaixa) -> Totais:
    resultado = Totais(fundo=sessao_caixa.fundo_troco_centavos)
    for movimento in sessao_caixa.movimentos:
        if movimento.tipo == TipoMovimentoCaixa.SUPRIMENTO:
            resultado.suprimentos += movimento.valor_centavos
        else:
            resultado.sangrias += movimento.valor_centavos
    finalizadas = (Venda.sessao_id == sessao_caixa.id) & (Venda.status == StatusVenda.FINALIZADA)
    quantidade, total = sessao.execute(
        select(func.count(Venda.id), func.coalesce(func.sum(Venda.total_centavos), 0)).where(
            finalizadas
        )
    ).one()
    resultado.vendas_quantidade = int(quantidade)
    resultado.vendas_total = int(total)
    por_forma = sessao.execute(
        select(Pagamento.forma, func.sum(Pagamento.valor_centavos))
        .join(Venda, Venda.id == Pagamento.venda_id)
        .where(finalizadas)
        .group_by(Pagamento.forma)
    )
    resultado.recebido = {forma: int(valor) for forma, valor in por_forma}
    return resultado


def abrir(sessao: Session, operador: Operador, fundo_centavos: int) -> SessaoCaixa:
    ja_aberta = aberta(sessao)
    if ja_aberta is not None:
        hora = tempo.na_loja(ja_aberta.aberto_em).strftime("%d/%m às %H:%M")
        raise RegraError(
            f"O caixa já está aberto (por {ja_aberta.operador.nome}, em {hora}).", status=409
        )
    if fundo_centavos < 0:
        raise RegraError("O fundo de troco não pode ser negativo.")
    sessao_caixa = SessaoCaixa(
        caixa_id=terminal(sessao).id,
        operador_id=operador.id,
        aberto_em=tempo.agora(),
        fundo_troco_centavos=fundo_centavos,
    )
    sessao.add(sessao_caixa)
    sessao.commit()
    log.info("caixa aberto por %s com fundo de %s centavos", operador.login, fundo_centavos)
    return sessao_caixa


def movimentar(
    sessao: Session,
    operador: Operador,
    tipo: TipoMovimentoCaixa,
    valor_centavos: int,
    motivo: str,
) -> MovimentoCaixa:
    sessao_caixa = exigir_aberta(sessao)
    motivo = " ".join(motivo.split())
    if valor_centavos <= 0:
        raise RegraError("Digite um valor maior que zero.")
    if not motivo:
        raise RegraError("Escreva o motivo (por exemplo: pagamento do fornecedor de gelo).")
    if tipo == TipoMovimentoCaixa.SANGRIA:
        na_gaveta = totais(sessao, sessao_caixa).dinheiro_esperado
        if valor_centavos > na_gaveta:
            raise RegraError(
                "A sangria é maior que o dinheiro que o sistema espera na gaveta. Confira o valor."
            )
    movimento = MovimentoCaixa(
        sessao_id=sessao_caixa.id,
        tipo=tipo,
        valor_centavos=valor_centavos,
        motivo=f"{motivo} ({operador.nome})"[:120],
        em=tempo.agora(),
    )
    sessao.add(movimento)
    sessao.commit()
    log.info("%s de %s centavos por %s: %s", tipo.value, valor_centavos, operador.login, motivo)
    return movimento


def fechar(
    sessao: Session,
    operador: Operador,
    contado: dict[FormaPagamento, int],
    observacao: str | None,
) -> SessaoCaixa:
    """Fecha o caixa guardando, por forma de pagamento, o esperado e o contado."""
    sessao_caixa = exigir_aberta(sessao)
    venda_aberta = sessao.scalar(
        select(Venda).where(Venda.sessao_id == sessao_caixa.id, Venda.status == StatusVenda.ABERTA)
    )
    if venda_aberta is not None:
        raise RegraError(
            f"A venda nº {venda_aberta.numero} está aberta. Finalize ou cancele a venda antes "
            "de fechar o caixa.",
            status=409,
        )
    if any(valor < 0 for valor in contado.values()):
        raise RegraError("O valor contado não pode ser negativo.")
    numeros = totais(sessao, sessao_caixa)
    for forma in FormaPagamento:
        sessao.add(
            ConferenciaCaixa(
                sessao_id=sessao_caixa.id,
                forma=forma,
                esperado_centavos=numeros.esperado(forma),
                contado_centavos=contado.get(forma, 0),
            )
        )
    sessao_caixa.fechado_em = tempo.agora()
    sessao_caixa.fechado_por_id = operador.id
    sessao_caixa.conferido_centavos = contado.get(FormaPagamento.DINHEIRO, 0)
    sessao_caixa.observacao = (observacao or "").strip() or None
    sessao.commit()
    log.info("caixa fechado por %s (sessão %s)", operador.login, sessao_caixa.id)
    return sessao_caixa

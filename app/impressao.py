"""Manda um cupom para a impressora escolhida em Configurações."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app import config, configuracoes, cupom, escpos, impressoras
from app.cupom import Cupom
from app.models import FormaPagamento, Venda
from app.operadores import RegraError

log = logging.getLogger("moleka.impressao")


def situacao(sessao: Session) -> tuple[bool, str]:
    """(dá para imprimir agora?, motivo quando não dá)."""
    pode, motivo = impressoras.disponivel()
    if not pode:
        return False, motivo
    if not configuracoes.ler_impressao(sessao).impressora:
        return False, "Nenhuma impressora de cupom escolhida. O gerente escolhe em Configurações."
    return True, ""


def imprimir(sessao: Session, cupom: Cupom, *, vias: int | None = None) -> configuracoes.Impressao:
    """Põe o cupom na fila da impressora de cupom. Devolve as opções usadas."""
    opcoes = configuracoes.ler_impressao(sessao)
    pode, motivo = situacao(sessao)
    if not pode:
        raise RegraError(motivo, status=409)
    dados = escpos.codificar(
        cupom, acentos=opcoes.acentos, cortar=opcoes.cortar, vias=vias or opcoes.vias
    )
    impressoras.enviar(opcoes.impressora, dados, cupom.titulo)
    return opcoes


@dataclass(frozen=True)
class DepoisDaVenda:
    """O que aconteceu com a impressora logo depois de uma venda finalizada."""

    impressora: str  # vazio = nenhuma escolhida
    quando: str  # perguntar, sempre ou nunca
    enviado: bool  # o comprovante foi para a fila sozinho
    erro: str  # por que o comprovante (ou a abertura da gaveta) falhou; vazio = nada falhou


def depois_da_venda(sessao: Session, venda: Venda) -> DepoisDaVenda:
    """Imprime sozinho (se for essa a opção) e abre a gaveta na venda com dinheiro.

    Nunca levanta erro: a venda já está gravada. O que falhar volta em `erro`, para o caixa ver.
    """
    opcoes = configuracoes.ler_impressao(sessao)
    pode, _motivo = situacao(sessao)
    if not pode:
        return DepoisDaVenda(opcoes.impressora, opcoes.quando, enviado=False, erro="")
    em_dinheiro = any(p.forma == FormaPagamento.DINHEIRO for p in venda.pagamentos)
    try:
        if opcoes.quando == "sempre":
            comprovante = cupom.comprovante_de_venda(
                configuracoes.ler_loja(sessao),
                venda,
                opcoes.colunas,
                versao=config.VERSAO,
                abre_gaveta=opcoes.gaveta,
            )
            imprimir(sessao, comprovante)
            return DepoisDaVenda(opcoes.impressora, opcoes.quando, enviado=True, erro="")
        if opcoes.gaveta and em_dinheiro:
            impressoras.enviar(opcoes.impressora, escpos.GAVETA, "Moleka - gaveta")
    except RegraError as erro:
        log.warning("depois da venda %s: %s", venda.numero, erro)
        return DepoisDaVenda(opcoes.impressora, opcoes.quando, enviado=False, erro=str(erro))
    except Exception as erro:  # a venda já está gravada: nenhum defeito da impressão a desfaz
        log.exception("depois da venda %s: a impressão falhou", venda.numero)
        return DepoisDaVenda(
            opcoes.impressora,
            opcoes.quando,
            enviado=False,
            erro=f"A impressora de cupom falhou: {erro}.",
        )
    return DepoisDaVenda(opcoes.impressora, opcoes.quando, enviado=False, erro="")

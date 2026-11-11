"""/api/status — estado real do sistema para os indicadores da interface.

Cada item traz `ok` e `motivo`. Quando `ok` é falso a interface mostra "—" e o motivo
no tooltip. Nada aqui é estimado: ou o backend verificou, ou diz que não verificou.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import backup, config, configuracoes, db, impressoras, tempo
from app.fiscal import provedor_configurado
from app.models import Configuracao, SessaoCaixa
from app.tempo import FUSO

router = APIRouter(tags=["status"])


class Indicador(BaseModel):
    ok: bool
    texto: str  # o que mostrar quando ok (ex.: "Homologação", "Caixa 01 · aberto 08:12")
    motivo: str  # por que não está ok, ou detalhe quando está
    # O que mostrar quando não está ok mas o sistema sabe o que há (ex.: "fechado").
    # Vazio = não há o que dizer e a interface mostra "—".
    estado: str = ""


class Status(BaseModel):
    app: str
    versao: str
    agora: str
    banco: Indicador
    fiscal: Indicador
    certificado: Indicador
    impressora_cupom: Indicador
    backup: Indicador
    caixa: Indicador


def _config(sessao: Session, chave: str) -> str | None:
    item = sessao.get(Configuracao, chave)
    return item.valor if item and item.valor else None


def _impressora_de_cupom(sessao: Session) -> Indicador:
    """Só fica "ok" depois que o gerente confirma que o teste saiu no papel."""
    opcoes = configuracoes.ler_impressao(sessao)
    if not opcoes.impressora:
        return Indicador(ok=False, texto="", motivo="nenhuma impressora de cupom escolhida")
    pode, motivo = impressoras.disponivel()
    if not pode:
        return Indicador(ok=False, texto="", motivo=motivo, estado="indisponível")
    if not opcoes.confirmada:
        return Indicador(
            ok=False,
            texto="",
            estado="não testada",
            motivo=f"{opcoes.impressora}: escolhida, mas o teste de impressão ainda não foi "
            "confirmado em Configurações",
        )
    return Indicador(ok=True, texto=opcoes.impressora, motivo="teste confirmado pelo gerente")


def _copia_de_seguranca(sessao: Session) -> Indicador:
    """A cópia de hoje existe? E a da pasta extra (pendrive ou nuvem), quando há uma?"""
    ultima = backup.ultima()
    if ultima is None:
        return Indicador(
            ok=False, texto="", estado="nunca feita", motivo="ainda não há cópia de segurança"
        )
    hoje = tempo.hoje()
    hora = f"{ultima.feita_em:%H:%M}"
    if ultima.dia == hoje:
        quando = f"hoje {hora}"
    elif ultima.dia == hoje - timedelta(days=1):
        quando = f"ontem {hora}"
    else:
        quando = f"{ultima.dia:%d/%m/%Y}"
    if ultima.dia != hoje:
        return Indicador(
            ok=False,
            texto="",
            estado=f"atrasada ({quando})",
            motivo=f"a última cópia de segurança é de {ultima.dia:%d/%m/%Y}",
        )
    opcoes = configuracoes.ler_backup(sessao)
    erro = configuracoes.ler_valor(sessao, "backup.extra_erro")
    if opcoes.pasta_extra and erro:
        return Indicador(
            ok=False,
            texto="",
            estado=f"{quando}, sem a pasta extra",
            motivo=f"a cópia deste computador foi feita, mas a da pasta extra falhou: {erro}",
        )
    if not opcoes.pasta_extra:
        motivo = (
            "cópia só neste computador: escolha uma pasta extra (pendrive ou nuvem) em "
            "Configurações para não perder os dados se o disco estragar"
        )
    else:
        motivo = f"também copiada para {opcoes.pasta_extra}"
    return Indicador(ok=True, texto=quando, motivo=motivo)


@router.get("/status", response_model=Status)
def status(sessao: Session = Depends(db.sessao)) -> Status:
    ok_banco, motivo_banco = db.banco_ok()
    fiscal = provedor_configurado().status()

    certificado_caminho = _config(sessao, "fiscal.certificado_caminho")

    aberta = sessao.scalar(
        select(SessaoCaixa).where(SessaoCaixa.fechado_em.is_(None)).order_by(SessaoCaixa.id.desc())
    )

    return Status(
        app=config.APP_NOME,
        versao=config.VERSAO,
        agora=datetime.now(FUSO).isoformat(timespec="seconds"),
        banco=Indicador(
            ok=ok_banco,
            texto="conectado",
            motivo=motivo_banco if not ok_banco else str(config.caminho_banco()),
        ),
        fiscal=Indicador(
            ok=fiscal.configurado,
            texto=f"{fiscal.nome} · {fiscal.ambiente}",
            motivo=fiscal.motivo,
        ),
        certificado=Indicador(
            ok=certificado_caminho is not None,
            texto="A1 configurado",
            motivo="nenhum certificado A1 configurado"
            if not certificado_caminho
            else certificado_caminho,
        ),
        impressora_cupom=_impressora_de_cupom(sessao),
        backup=_copia_de_seguranca(sessao),
        caixa=Indicador(
            ok=aberta is not None,
            texto=(
                f"{aberta.caixa.nome} · aberto {tempo.na_loja(aberta.aberto_em).strftime('%H:%M')}"
                if aberta
                else ""
            ),
            motivo="nenhum caixa aberto" if not aberta else f"operador {aberta.operador.nome}",
            estado="" if aberta else "fechado",
        ),
    )

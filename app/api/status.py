"""/api/status — estado real do sistema para os indicadores da interface.

Cada item traz `ok` e `motivo`. Quando `ok` é falso a interface mostra "—" e o motivo
no tooltip. Nada aqui é estimado: ou o backend verificou, ou diz que não verificou.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config, db, tempo
from app.fiscal import provedor_configurado
from app.models import Configuracao, SessaoCaixa
from app.tempo import FUSO

router = APIRouter(tags=["status"])


class Indicador(BaseModel):
    ok: bool
    texto: str  # o que mostrar quando ok (ex.: "Homologação", "Caixa 01 · aberto 08:12")
    motivo: str  # por que não está ok, ou detalhe quando está


class Status(BaseModel):
    app: str
    versao: str
    agora: str
    banco: Indicador
    fiscal: Indicador
    certificado: Indicador
    impressora_cupom: Indicador
    impressora_a4: Indicador
    caixa: Indicador


def _config(sessao: Session, chave: str) -> str | None:
    item = sessao.get(Configuracao, chave)
    return item.valor if item and item.valor else None


@router.get("/status", response_model=Status)
def status(sessao: Session = Depends(db.sessao)) -> Status:
    ok_banco, motivo_banco = db.banco_ok()
    fiscal = provedor_configurado().status()

    certificado_caminho = _config(sessao, "fiscal.certificado_caminho")
    impressora_cupom = _config(sessao, "impressao.cupom")
    impressora_a4 = _config(sessao, "impressao.a4")

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
        impressora_cupom=Indicador(
            ok=impressora_cupom is not None,
            texto=impressora_cupom or "",
            motivo="nenhuma impressora de cupom configurada"
            if not impressora_cupom
            else "configurada (não testada)",
        ),
        impressora_a4=Indicador(
            ok=impressora_a4 is not None,
            texto=impressora_a4 or "",
            motivo="nenhuma impressora A4 configurada"
            if not impressora_a4
            else "configurada (não testada)",
        ),
        caixa=Indicador(
            ok=aberta is not None,
            texto=(
                f"{aberta.caixa.nome} · aberto {tempo.na_loja(aberta.aberto_em).strftime('%H:%M')}"
                if aberta
                else ""
            ),
            motivo="nenhum caixa aberto" if not aberta else f"operador {aberta.operador.nome}",
        ),
    )

"""Datas e horas do sistema.

O banco guarda sempre a hora universal (UTC), sem fuso. A loja trabalha no horário de Brasília:
"hoje" e "as vendas do dia" são contados por esse horário.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

FUSO = ZoneInfo("America/Sao_Paulo")


def agora() -> datetime:
    """Agora, em UTC e sem fuso, do jeito que vai para o banco."""
    return datetime.now(UTC).replace(tzinfo=None)


def hoje() -> date:
    """A data de hoje no horário da loja."""
    return datetime.now(FUSO).date()


def limites_do_dia(dia: date | None = None) -> tuple[datetime, datetime]:
    """Início e fim (exclusivo) de um dia da loja, em UTC sem fuso, para filtrar no banco."""
    dia = dia or hoje()
    inicio = datetime.combine(dia, time.min, tzinfo=FUSO)
    fim = inicio + timedelta(days=1)
    return (
        inicio.astimezone(UTC).replace(tzinfo=None),
        fim.astimezone(UTC).replace(tzinfo=None),
    )


def limites_do_periodo(inicio: date, fim: date) -> tuple[datetime, datetime]:
    """Do começo de `inicio` ao fim de `fim` (dias da loja), em UTC sem fuso."""
    return limites_do_dia(inicio)[0], limites_do_dia(fim)[1]


def meio_dia(dia: date) -> datetime:
    """Guarda uma data "sem hora" (vencimento, competência, dia do pagamento).

    Vai como meio-dia para que nenhuma conversão de fuso a empurre para o dia vizinho.
    """
    return datetime.combine(dia, time(12, 0))


def na_loja(momento: datetime) -> datetime:
    """Converte uma hora do banco (UTC sem fuso) para o horário da loja."""
    return momento.replace(tzinfo=UTC).astimezone(FUSO)


def iso_na_loja(momento: datetime | None) -> str | None:
    """Texto ISO com fuso, para a interface mostrar a hora certa."""
    return na_loja(momento).isoformat(timespec="seconds") if momento else None

"""Evolução do banco de dados entre versões do programa, sem perder os dados da loja.

O SQLite guarda um número de versão no próprio arquivo (`PRAGMA user_version`). Cada vez que o
formato de uma tabela mudar, somamos 1 em `VERSAO_DO_BANCO` e escrevemos em `PASSOS` a função
que leva da versão anterior para a nova. Ao abrir, o programa guarda uma cópia do banco em
`<dados>/backups` e aplica os passos que faltam.

Tabela nova não precisa de passo: `create_all` cria o que não existe. Passo é para mudar tabela
que já existe (coluna nova, índice, conversão de dados).
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from sqlalchemy import Connection, Engine

from app.models import Base

log = logging.getLogger("moleka.banco")

VERSAO_DO_BANCO = 2


def _colunas(con: Connection, tabela: str) -> set[str]:
    return {linha[1] for linha in con.exec_driver_sql(f"PRAGMA table_info({tabela})")}


def _acrescentar_colunas(con: Connection, tabela: str, colunas: dict[str, str]) -> None:
    """Acrescenta as colunas que faltam (pode rodar de novo sem erro)."""
    existentes = _colunas(con, tabela)
    for nome, tipo in colunas.items():
        if nome not in existentes:
            con.exec_driver_sql(f"ALTER TABLE {tabela} ADD COLUMN {nome} {tipo}")


def _formato_1_para_2(con: Connection) -> None:
    """Versão 0.3.0: cadastros completos, controle de caixa e venda."""
    _acrescentar_colunas(con, "produto", {"categoria": "VARCHAR(40)"})
    _acrescentar_colunas(con, "sessao_caixa", {"fechado_por_id": "INTEGER REFERENCES operador(id)"})
    _acrescentar_colunas(
        con,
        "venda",
        {
            "operador_id": "INTEGER REFERENCES operador(id)",
            "desconto_por_id": "INTEGER REFERENCES operador(id)",
            "ajuste_pagamento_centavos": "INTEGER NOT NULL DEFAULT 0",
            "quer_nfce": "BOOLEAN",
            "cancelada_em": "DATETIME",
            "cancelada_por_id": "INTEGER REFERENCES operador(id)",
            "motivo_cancelamento": "VARCHAR(160)",
        },
    )
    _acrescentar_colunas(
        con,
        "venda_item",
        {"codigo": "VARCHAR(30)", "descricao": "VARCHAR(120)", "unidade": "VARCHAR(6)"},
    )
    _acrescentar_colunas(con, "pagamento", {"ajuste_centavos": "INTEGER NOT NULL DEFAULT 0"})
    con.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_produto_categoria ON produto (categoria)")


# PASSOS[n] leva o banco da versão n para a n + 1.
PASSOS: dict[int, Callable[[Connection], None]] = {1: _formato_1_para_2}


class BancoMaisNovoError(RuntimeError):
    """O arquivo do banco foi gravado por uma versão mais nova do programa."""


def versao_gravada(con: Connection) -> int:
    return int(con.exec_driver_sql("PRAGMA user_version").scalar() or 0)


def _gravar_versao(con: Connection, versao: int) -> None:
    con.exec_driver_sql(f"PRAGMA user_version = {int(versao)}")


def _copiar_banco(arquivo: Path, pasta_backups: Path, versao: int) -> Path:
    """Copia o banco com a API de backup do SQLite (pega também o que ainda está no WAL)."""
    pasta_backups.mkdir(parents=True, exist_ok=True)
    carimbo = datetime.now().strftime("%Y%m%d-%H%M%S")
    destino = pasta_backups / f"moleka-antes-do-formato-{versao + 1}-{carimbo}.db"
    origem_con = sqlite3.connect(arquivo)
    destino_con = sqlite3.connect(destino)
    try:
        origem_con.backup(destino_con)
    finally:
        destino_con.close()
        origem_con.close()
    return destino


def preparar(engine: Engine, arquivo: Path | None = None, pasta_backups: Path | None = None) -> int:
    """Cria o que falta e aplica os passos pendentes. Devolve a versão final do banco.

    `arquivo` e `pasta_backups` são usados para a cópia de segurança antes de um passo;
    sem eles (banco em memória, nos testes) a cópia não é feita.
    """
    with engine.connect() as con:
        tinha_tabelas = (
            con.exec_driver_sql("SELECT 1 FROM sqlite_master WHERE type = 'table' LIMIT 1").first()
            is not None
        )
        versao = versao_gravada(con)
    if versao > VERSAO_DO_BANCO:
        raise BancoMaisNovoError(
            f"Os dados deste computador foram gravados por uma versão mais nova do programa "
            f"(formato {versao}; esta versão entende até o formato {VERSAO_DO_BANCO}). "
            "Instale a versão mais recente do Moleka PDV."
        )

    Base.metadata.create_all(engine)
    if not tinha_tabelas or versao == 0:
        # Banco novo já nasce no formato atual; banco criado antes deste controle está no formato 1.
        versao = VERSAO_DO_BANCO if not tinha_tabelas else 1
        with engine.begin() as con:
            _gravar_versao(con, versao)

    if versao < VERSAO_DO_BANCO and arquivo is not None and pasta_backups is not None:
        copia = _copiar_banco(arquivo, pasta_backups, versao)
        log.info("cópia de segurança antes de atualizar o banco: %s", copia)
    while versao < VERSAO_DO_BANCO:
        with engine.begin() as con:
            PASSOS[versao](con)
            _gravar_versao(con, versao + 1)
        log.info("banco atualizado do formato %s para o %s", versao, versao + 1)
        versao += 1
    return versao

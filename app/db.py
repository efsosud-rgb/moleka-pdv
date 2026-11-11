"""Conexão com o banco (SQLite em arquivo, modo WAL) e criação do schema."""

from __future__ import annotations

import os
from collections.abc import Iterator

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import config
from app.models import Base
from app.pesquisa import sem_acento

_engine: Engine | None = None
_fabrica: sessionmaker[Session] | None = None


def url_banco() -> str:
    env = os.environ.get("MOLEKA_PDV_BANCO_URL")
    if env:
        return env
    return f"sqlite:///{config.caminho_banco()}"


def engine() -> Engine:
    global _engine, _fabrica
    if _engine is None:
        url = url_banco()
        kwargs: dict[str, object] = {}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
            if "mode=memory" in url:
                kwargs["poolclass"] = StaticPool
        _engine = create_engine(url, **kwargs)
        if url.startswith("sqlite"):

            @event.listens_for(_engine, "connect")
            def _pragmas(conexao, _registro):  # type: ignore[no-untyped-def]
                # Pesquisa sem acento: sem_acento('Água') = 'agua' (ver app/pesquisa.py).
                conexao.create_function("sem_acento", 1, sem_acento, deterministic=True)
                cursor = conexao.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                if ":memory:" not in url:
                    cursor.execute("PRAGMA journal_mode=WAL")
                cursor.close()

        _fabrica = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def criar_schema() -> None:
    """Cria as tabelas que faltam e leva o banco ao formato desta versão do programa.

    No SQLite, a evolução entre versões é feita por `app/migracoes.py`, com cópia de
    segurança antes de qualquer mudança.
    """
    from app import migracoes  # importado aqui para não criar ciclo de importação

    url = url_banco()
    if not url.startswith("sqlite"):
        Base.metadata.create_all(engine())
    else:
        em_arquivo = "memory" not in url and not os.environ.get("MOLEKA_PDV_BANCO_URL")
        migracoes.preparar(
            engine(),
            arquivo=config.caminho_banco() if em_arquivo else None,
            pasta_backups=config.pasta_dados() / "backups" if em_arquivo else None,
        )
    semear_padroes()


def semear_padroes() -> None:
    """Cria o mínimo para a loja começar: as tabelas VAREJO (padrão) e ATACADO, o Caixa 01 e
    as categorias do financeiro (só os nomes: aluguel, energia, compra de mercadorias...).

    Só cria o que não existe; nunca altera o que a loja já cadastrou. Não são dados de
    exemplo: são os nomes que o Eric pediu (tabela varejista e atacadista) e um plano de
    contas inicial, sem nenhum valor, que o gerente renomeia e completa.
    """
    from sqlalchemy import select

    from app import financeiro  # importado aqui para não criar ciclo de importação
    from app.models import Caixa, TabelaPreco

    with nova_sessao() as sessao:
        if sessao.scalar(select(TabelaPreco).limit(1)) is None:
            sessao.add_all([TabelaPreco(nome="VAREJO", padrao=True), TabelaPreco(nome="ATACADO")])
        if sessao.scalar(select(Caixa).limit(1)) is None:
            sessao.add(Caixa(nome="Caixa 01"))
        financeiro.semear_categorias(sessao)
        sessao.commit()


def sessao() -> Iterator[Session]:
    """Dependência do FastAPI: uma sessão por requisição."""
    engine()
    assert _fabrica is not None
    with _fabrica() as s:
        yield s


def nova_sessao() -> Session:
    """Sessão avulsa, para usar fora de uma requisição: `with db.nova_sessao() as sessao:`."""
    engine()
    assert _fabrica is not None
    return _fabrica()


def banco_ok() -> tuple[bool, str]:
    try:
        with engine().connect() as c:
            c.execute(text("SELECT 1"))
        return True, "conectado"
    except Exception as exc:  # noqa: BLE001 — queremos o motivo, qualquer que seja
        return False, f"erro ao abrir o banco: {exc}"


def resetar_para_testes() -> None:
    """Descarta o engine (usado pelos testes para trocar a URL do banco)."""
    global _engine, _fabrica
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _fabrica = None

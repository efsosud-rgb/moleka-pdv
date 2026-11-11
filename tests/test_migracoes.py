"""O banco evolui entre versões do programa sem perder dados (app/migracoes.py)."""

import pytest
from sqlalchemy import create_engine, inspect, text

from app import migracoes


def _engine(caminho):
    return create_engine(f"sqlite:///{caminho}")


def test_banco_novo_nasce_no_formato_atual(tmp_path):
    engine = _engine(tmp_path / "novo.db")
    assert migracoes.preparar(engine) == migracoes.VERSAO_DO_BANCO
    with engine.connect() as con:
        assert migracoes.versao_gravada(con) == migracoes.VERSAO_DO_BANCO
    assert "produto" in inspect(engine).get_table_names()


def test_banco_antigo_sem_numero_e_tratado_como_formato_1(tmp_path):
    engine = _engine(tmp_path / "antigo.db")
    migracoes.Base.metadata.create_all(engine)  # como as versões anteriores a este controle
    with engine.connect() as con:
        assert migracoes.versao_gravada(con) == 0
    assert migracoes.preparar(engine) == 1


def test_passo_pendente_e_aplicado_com_copia_de_seguranca(tmp_path, monkeypatch):
    arquivo = tmp_path / "loja.db"
    engine = _engine(arquivo)
    migracoes.preparar(engine)
    with engine.begin() as con:
        con.execute(text("INSERT INTO configuracao (chave, valor) VALUES ('teste', 'fica')"))

    def passo(con):
        con.exec_driver_sql("ALTER TABLE configuracao ADD COLUMN observacao TEXT")

    monkeypatch.setattr(migracoes, "VERSAO_DO_BANCO", 2)
    monkeypatch.setattr(migracoes, "PASSOS", {1: passo})
    backups = tmp_path / "backups"
    assert migracoes.preparar(engine, arquivo=arquivo, pasta_backups=backups) == 2

    colunas = [c["name"] for c in inspect(engine).get_columns("configuracao")]
    assert "observacao" in colunas
    with engine.connect() as con:
        assert (
            con.execute(text("SELECT valor FROM configuracao WHERE chave = 'teste'")).scalar()
            == "fica"
        )
        assert migracoes.versao_gravada(con) == 2
    copias = list(backups.glob("moleka-antes-do-formato-2-*.db"))
    assert len(copias) == 1 and copias[0].stat().st_size > 0
    # Rodar de novo não repete o passo nem cria outra cópia.
    assert migracoes.preparar(engine, arquivo=arquivo, pasta_backups=backups) == 2
    assert len(list(backups.glob("*.db"))) == 1


def test_banco_de_versao_mais_nova_nao_e_aberto(tmp_path):
    engine = _engine(tmp_path / "futuro.db")
    migracoes.preparar(engine)
    with engine.begin() as con:
        con.exec_driver_sql(f"PRAGMA user_version = {migracoes.VERSAO_DO_BANCO + 1}")
    with pytest.raises(migracoes.BancoMaisNovoError, match="versão mais nova"):
        migracoes.preparar(engine)

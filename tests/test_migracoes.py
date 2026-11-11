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


def test_banco_antigo_sem_numero_e_tratado_como_formato_1(tmp_path, monkeypatch):
    monkeypatch.setattr(migracoes, "VERSAO_DO_BANCO", 1)
    monkeypatch.setattr(migracoes, "PASSOS", {})
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

    atual = migracoes.VERSAO_DO_BANCO
    monkeypatch.setattr(migracoes, "VERSAO_DO_BANCO", atual + 1)
    monkeypatch.setattr(migracoes, "PASSOS", {atual: passo})
    backups = tmp_path / "backups"
    assert migracoes.preparar(engine, arquivo=arquivo, pasta_backups=backups) == atual + 1

    colunas = [c["name"] for c in inspect(engine).get_columns("configuracao")]
    assert "observacao" in colunas
    with engine.connect() as con:
        assert (
            con.execute(text("SELECT valor FROM configuracao WHERE chave = 'teste'")).scalar()
            == "fica"
        )
        assert migracoes.versao_gravada(con) == atual + 1
    copias = list(backups.glob(f"moleka-antes-do-formato-{atual + 1}-*.db"))
    assert len(copias) == 1 and copias[0].stat().st_size > 0
    # Rodar de novo não repete o passo nem cria outra cópia.
    assert migracoes.preparar(engine, arquivo=arquivo, pasta_backups=backups) == atual + 1
    assert len(list(backups.glob("*.db"))) == 1


# As cinco tabelas que mudaram do formato 1 (versões 0.1.0 e 0.2.0) para o 2, como eram.
FORMATO_1 = """
CREATE TABLE produto (id INTEGER PRIMARY KEY, codigo VARCHAR(30) NOT NULL UNIQUE, ean VARCHAR(14),
  descricao VARCHAR(120) NOT NULL, unidade VARCHAR(6) NOT NULL, ncm VARCHAR(8), cest VARCHAR(7),
  cst_csosn VARCHAR(4), origem VARCHAR(1) NOT NULL, custo_centavos INTEGER,
  estoque_minimo NUMERIC(12, 3) NOT NULL, ativo BOOLEAN NOT NULL,
  criado_em DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
  atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL);
CREATE TABLE sessao_caixa (id INTEGER PRIMARY KEY, caixa_id INTEGER NOT NULL,
  operador_id INTEGER NOT NULL, aberto_em DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
  fechado_em DATETIME, fundo_troco_centavos INTEGER NOT NULL, conferido_centavos INTEGER,
  observacao TEXT);
CREATE TABLE venda (id INTEGER PRIMARY KEY, sessao_id INTEGER NOT NULL, cliente_id INTEGER,
  tabela_id INTEGER NOT NULL, numero INTEGER NOT NULL, status VARCHAR(10) NOT NULL,
  cpf_na_nota VARCHAR(14), subtotal_centavos INTEGER NOT NULL, desconto_centavos INTEGER NOT NULL,
  total_centavos INTEGER NOT NULL, iniciada_em DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
  finalizada_em DATETIME);
CREATE TABLE venda_item (id INTEGER PRIMARY KEY, venda_id INTEGER NOT NULL,
  produto_id INTEGER NOT NULL, quantidade NUMERIC(12, 3) NOT NULL,
  preco_unitario_centavos INTEGER NOT NULL, faixa_qtd_min NUMERIC(12, 3),
  desconto_centavos INTEGER NOT NULL, total_centavos INTEGER NOT NULL);
CREATE TABLE pagamento (id INTEGER PRIMARY KEY, venda_id INTEGER NOT NULL,
  forma VARCHAR(8) NOT NULL, valor_centavos INTEGER NOT NULL, troco_centavos INTEGER NOT NULL);
"""


def test_banco_das_versoes_0_1_e_0_2_e_atualizado_sem_perder_dados(tmp_path):
    """Quem instalou a 0.2.0 e criou o gerente continua com ele depois de atualizar."""
    arquivo = tmp_path / "loja.db"
    engine = _engine(arquivo)
    with engine.begin() as con:
        for comando in FORMATO_1.split(";"):
            if comando.strip():
                con.exec_driver_sql(comando)
    migracoes.Base.metadata.create_all(engine)  # as outras tabelas não mudaram
    with engine.begin() as con:
        con.exec_driver_sql("DROP TABLE regra_forma_pagamento")  # tabelas que só existem no 2
        con.exec_driver_sql("DROP TABLE conferencia_caixa")
        con.exec_driver_sql("PRAGMA user_version = 1")
        con.execute(
            text(
                "INSERT INTO operador (nome, login, senha_hash, perfil, ativo) "
                "VALUES ('Gerente de Teste', 'gerente', 'scrypt$x', 'GERENTE', 1)"
            )
        )
        con.execute(
            text(
                "INSERT INTO produto (codigo, descricao, unidade, origem, estoque_minimo, ativo) "
                "VALUES ('1', 'Produto antigo de teste', 'UN', '0', 0, 1)"
            )
        )

    backups = tmp_path / "backups"
    assert migracoes.preparar(engine, arquivo=arquivo, pasta_backups=backups) == 2
    inspetor = inspect(engine)
    colunas = {t: {c["name"] for c in inspetor.get_columns(t)} for t in inspetor.get_table_names()}
    assert "categoria" in colunas["produto"]
    assert "fechado_por_id" in colunas["sessao_caixa"]
    assert {"operador_id", "quer_nfce", "ajuste_pagamento_centavos"} <= colunas["venda"]
    assert {"codigo", "descricao", "unidade"} <= colunas["venda_item"]
    assert "ajuste_centavos" in colunas["pagamento"]
    assert "regra_forma_pagamento" in colunas and "conferencia_caixa" in colunas
    with engine.connect() as con:
        assert con.execute(text("SELECT login FROM operador")).scalar() == "gerente"
        assert con.execute(text("SELECT descricao, categoria FROM produto")).one() == (
            "Produto antigo de teste",
            None,
        )
    assert len(list(backups.glob("moleka-antes-do-formato-2-*.db"))) == 1
    # Rodar de novo não muda nada nem faz outra cópia.
    assert migracoes.preparar(engine, arquivo=arquivo, pasta_backups=backups) == 2
    assert len(list(backups.glob("*.db"))) == 1


def test_banco_de_versao_mais_nova_nao_e_aberto(tmp_path):
    engine = _engine(tmp_path / "futuro.db")
    migracoes.preparar(engine)
    with engine.begin() as con:
        con.exec_driver_sql(f"PRAGMA user_version = {migracoes.VERSAO_DO_BANCO + 1}")
    with pytest.raises(migracoes.BancoMaisNovoError, match="versão mais nova"):
        migracoes.preparar(engine)

import os

import pytest
from fastapi.testclient import TestClient

# Banco SQLite em memória, compartilhado entre conexões (StaticPool); pasta de dados temporária
os.environ["MOLEKA_PDV_BANCO_URL"] = (
    "sqlite:///file:moleka_testes?mode=memory&cache=shared&uri=true"
)

# O mesmo endereço que a janela do programa usa (o servidor recusa outros).
ENDERECO = "http://127.0.0.1:8765"
# Operadores fictícios, só para os testes.
GERENTE = {"nome": "Gerente de Teste", "login": "gerente", "senha": "senha-do-gerente"}
OPERADOR = {"nome": "Caixa de Teste", "login": "caixa", "senha": "1234", "perfil": "operador"}


@pytest.fixture()
def app_teste(tmp_path, monkeypatch):
    """Aplicação nova, com o banco vazio (nenhum operador cadastrado)."""
    monkeypatch.setenv("MOLEKA_PDV_DADOS", str(tmp_path))
    from app import db, seguranca
    from app.api import criar_app
    from app.models import Base

    # Hash de senha mais barato nos testes (o custo real é testado em test_seguranca.py).
    monkeypatch.setattr(seguranca, "_N", 2**8)
    seguranca._hash_de_ninguem.cache_clear()
    db.resetar_para_testes()
    engine = db.engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield criar_app()
    db.resetar_para_testes()
    seguranca._hash_de_ninguem.cache_clear()


def _navegador(app):
    return TestClient(app, base_url=ENDERECO)


@pytest.fixture()
def anonimo(app_teste):
    """Janela sem login."""
    with _navegador(app_teste) as c:
        yield c


@pytest.fixture()
def cliente(app_teste):
    """Janela com o gerente logado (criado pela configuração inicial)."""
    with _navegador(app_teste) as c:
        resposta = c.post("/api/configuracao-inicial", json=GERENTE)
        assert resposta.status_code == 201, resposta.text
        yield c


@pytest.fixture()
def caixa(app_teste, cliente):
    """Outra janela, com um operador comum (sem perfil de gerente) logado."""
    resposta = cliente.post("/api/operadores", json=OPERADOR)
    assert resposta.status_code == 201, resposta.text
    with _navegador(app_teste) as c:
        entrada = c.post(
            "/api/login", json={"login": OPERADOR["login"], "senha": OPERADOR["senha"]}
        )
        assert entrada.status_code == 200, entrada.text
        yield c

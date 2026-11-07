import os

import pytest
from fastapi.testclient import TestClient

# Banco SQLite em memória, compartilhado entre conexões (StaticPool); pasta de dados temporária
os.environ["MOLEKA_PDV_BANCO_URL"] = (
    "sqlite:///file:moleka_testes?mode=memory&cache=shared&uri=true"
)


@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    monkeypatch.setenv("MOLEKA_PDV_DADOS", str(tmp_path))
    from app import db
    from app.api import criar_app
    from app.models import Base

    db.resetar_para_testes()
    engine = db.engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(criar_app()) as c:
        yield c
    db.resetar_para_testes()

"""Leitura do certificado digital A1 (app/certificado.py).

Os certificados são fictícios, gerados na hora (tests/certificado_ficticio.py).
"""

from datetime import UTC, datetime

import pytest
from certificado_ficticio import CNPJ, EMISSOR, SENHA, TITULAR, gerar

from app import certificado
from app.operadores import RegraError


def test_le_titular_cnpj_emissor_e_validade():
    lido = certificado.ler(gerar(), SENHA)
    assert (lido.titular, lido.cnpj, lido.emissor, lido.pessoa_fisica) == (
        TITULAR,
        CNPJ,
        EMISSOR,
        False,
    )
    agora = datetime.now(UTC)
    assert lido.inicio < agora < lido.fim
    assert (lido.fim - agora).days in (364, 365)


def test_o_cnpj_vem_do_campo_proprio_da_icp_brasil():
    lido = certificado.ler(gerar(titular="SO O NOME", cnpj_no_nome=False), SENHA)
    assert (lido.titular, lido.cnpj) == ("SO O NOME", CNPJ)


def test_sem_o_campo_proprio_vale_o_cnpj_do_fim_do_nome():
    lido = certificado.ler(gerar(cnpj_no_campo_proprio=False), SENHA)
    assert (lido.titular, lido.cnpj) == (TITULAR, CNPJ)


def test_cnpj_alfanumerico():
    lido = certificado.ler(gerar(cnpj="12ABC34501DE35"), SENHA)
    assert lido.cnpj == "12ABC34501DE35"


def test_certificado_de_pessoa_fisica_nao_tem_cnpj():
    lido = certificado.ler(gerar(titular="PESSOA FICTICIA", cnpj="", pessoa_fisica=True), SENHA)
    assert (lido.cnpj, lido.pessoa_fisica) == ("", True)


def test_arquivo_sem_senha():
    lido = certificado.ler(gerar(senha=""), "")
    assert lido.cnpj == CNPJ


def test_senha_errada_e_recusada():
    with pytest.raises(RegraError, match="com esta senha") as erro:
        certificado.ler(gerar(), "senha-errada-ficticia")
    assert "senha-errada-ficticia" not in str(erro.value)


@pytest.mark.parametrize(
    ("conteudo", "trecho"),
    [
        (b"", "Escolha o arquivo"),
        (b"isto nao e um certificado", "com esta senha"),
        (b"0" * (certificado.LIMITE_BYTES + 1), "grande demais"),
    ],
)
def test_arquivo_que_nao_e_certificado(conteudo, trecho):
    with pytest.raises(RegraError, match=trecho):
        certificado.ler(conteudo, SENHA)


def test_sem_a_chave_privada_e_recusado():
    with pytest.raises(RegraError, match="chave privada"):
        certificado.ler(gerar(com_chave=False), SENHA)

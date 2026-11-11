"""CPF e CNPJ (inclusive o CNPJ com letras, que existe desde julho de 2026)."""

import pytest

from app import documentos

# Números de teste: gerados pela regra dos dígitos, não são de pessoas ou empresas reais.
CPF_BOM = "529.982.247-25"
CNPJ_BOM = "11.222.333/0001-81"
CNPJ_COM_LETRAS = "12.ABC.345/01DE-35"  # exemplo da documentação da Receita Federal


def test_cpf():
    assert documentos.cpf_valido(CPF_BOM)
    assert documentos.cpf_valido("52998224725")
    assert not documentos.cpf_valido("529.982.247-26")  # último dígito trocado
    assert not documentos.cpf_valido("111.111.111-11")  # repetido passa na conta, mas não existe
    assert not documentos.cpf_valido("5299822472")  # faltou um dígito
    assert not documentos.cpf_valido("")


def test_cnpj_so_com_numeros():
    assert documentos.cnpj_valido(CNPJ_BOM)
    assert not documentos.cnpj_valido("11.222.333/0001-82")
    assert not documentos.cnpj_valido("00.000.000/0000-00")
    assert not documentos.cnpj_valido("1122233300018")


def test_cnpj_com_letras():
    assert documentos.cnpj_valido(CNPJ_COM_LETRAS)
    assert documentos.cnpj_valido("12abc34501de35")  # minúsculas são aceitas e viram maiúsculas
    assert documentos.cnpj_valido("00.000.000/E08G-12")
    assert not documentos.cnpj_valido("12.ABC.345/01DE-36")
    assert not documentos.cnpj_valido("12.ABC.345/01DE-3X")  # os dois últimos são sempre números


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [(CPF_BOM, "cpf"), (CNPJ_BOM, "cnpj"), (CNPJ_COM_LETRAS, "cnpj"), ("123", None), ("", None)],
)
def test_tipo(texto, esperado):
    assert documentos.tipo(texto) == esperado


def test_limpar_e_formatar():
    assert documentos.limpar(" 529.982.247-25 ") == "52998224725"
    assert documentos.formatar("52998224725") == CPF_BOM
    assert documentos.formatar("11222333000181") == CNPJ_BOM
    assert documentos.formatar("12abc34501de35") == CNPJ_COM_LETRAS
    assert documentos.formatar("123") == "123"
    assert documentos.formatar(None) == ""

from decimal import Decimal

import pytest

from app.dinheiro import de_reais, formatar, multiplicar, percentual, rateio


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("R$ 1.234,56", 123456),
        ("1234,56", 123456),
        ("1234.56", 123456),
        ("12,5", 1250),
        ("0,01", 1),
        ("5", 500),
        ("-1,50", -150),
        (12, 1200),
        (Decimal("12.345"), 1235),  # HALF_UP
        (12.345, 1235),
    ],
)
def test_de_reais(entrada, esperado):
    assert de_reais(entrada) == esperado


@pytest.mark.parametrize("entrada", ["", "abc", "R$", ",", True])
def test_de_reais_invalido(entrada):
    with pytest.raises((ValueError, TypeError)):
        de_reais(entrada)


@pytest.mark.parametrize(
    ("centavos", "esperado"),
    [
        (0, "R$ 0,00"),
        (1, "R$ 0,01"),
        (1250, "R$ 12,50"),
        (123456, "R$ 1.234,56"),
        (1234567890, "R$ 12.345.678,90"),
        (-150, "-R$ 1,50"),
    ],
)
def test_formatar(centavos, esperado):
    assert formatar(centavos) == esperado


def test_formatar_sem_simbolo():
    assert formatar(1250, simbolo=False) == "12,50"


def test_multiplicar_quantidade_fracionada_arredonda_half_up():
    # 0,350 kg a R$ 39,90/kg = 13,965 -> R$ 13,97
    assert multiplicar(3990, Decimal("0.350")) == 1397
    assert multiplicar(500, 3) == 1500
    with pytest.raises(ValueError):
        multiplicar(500, -1)


def test_percentual():
    assert percentual(1250, 10) == 125
    assert percentual(999, "33.333") == 333
    assert percentual(1, 50) == 1  # 0,5 centavo arredonda para cima


def test_rateio_nao_perde_centavos():
    partes = rateio(100, [1, 1, 1])
    assert sum(partes) == 100
    assert sorted(partes) == [33, 33, 34]


def test_rateio_proporcional():
    assert rateio(1000, [3, 1]) == [750, 250]
    assert rateio(0, [5, 5]) == [0, 0]
    assert rateio(-7, [1, 1]) == [-4, -3] or rateio(-7, [1, 1]) == [-3, -4]
    assert sum(rateio(-7, [1, 1])) == -7


def test_rateio_pesos_zero_vai_para_o_ultimo():
    assert rateio(50, [0, 0]) == [0, 50]
    assert rateio(50, []) == []

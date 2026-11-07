from decimal import Decimal

import pytest

from app.precos import Faixa, PrecoProduto, escolher_tabela

# Picolé: 1+ → 5,00 · 10+ → 4,50 · 50+ → 4,00 (faixas fora de ordem de propósito)
PICOLE = PrecoProduto(
    faixas=(
        Faixa(Decimal("50"), 400),
        Faixa(Decimal("1"), 500),
        Faixa(Decimal("10"), 450),
    )
)


@pytest.mark.parametrize(
    ("qtd", "unitario", "total"),
    [
        (1, 500, 500),
        (9, 500, 4500),
        (10, 450, 4500),  # na virada da faixa, 10 un custam o mesmo que 9
        (49, 450, 22050),
        (50, 400, 20000),
        (120, 400, 48000),
    ],
)
def test_faixa_por_quantidade(qtd, unitario, total):
    assert PICOLE.preco_unitario(qtd) == unitario
    assert PICOLE.total(qtd) == total


def test_faixas_ficam_ordenadas():
    assert [f.qtd_min for f in PICOLE.faixas] == [Decimal("1"), Decimal("10"), Decimal("50")]


def test_quantidade_fracionada_usa_faixa_correta():
    sorvete_kg = PrecoProduto(faixas=(Faixa(Decimal("0.001"), 3990), Faixa(Decimal("2"), 3590)))
    assert sorvete_kg.preco_unitario(Decimal("0.350")) == 3990
    assert sorvete_kg.total(Decimal("0.350")) == 1397
    assert sorvete_kg.preco_unitario(Decimal("2.5")) == 3590


def test_produto_precisa_de_faixa_inicial():
    with pytest.raises(ValueError):
        PrecoProduto(faixas=())
    with pytest.raises(ValueError):
        PrecoProduto(faixas=(Faixa(Decimal("10"), 450),))
    with pytest.raises(ValueError):
        PrecoProduto(faixas=(Faixa(Decimal("1"), 500), Faixa(Decimal("1"), 450)))


def test_quantidade_zero_ou_negativa():
    with pytest.raises(ValueError):
        PICOLE.preco_unitario(0)
    with pytest.raises(ValueError):
        PICOLE.total(Decimal("-1"))


def test_escolha_da_tabela():
    assert escolher_tabela(None, None, "VAREJO") == "VAREJO"
    assert escolher_tabela(None, "ATACADO", "VAREJO") == "ATACADO"
    assert escolher_tabela("VAREJO", "ATACADO", "VAREJO") == "VAREJO"

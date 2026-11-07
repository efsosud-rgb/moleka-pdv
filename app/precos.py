"""Regras de preço: tabelas (varejo/atacado) e faixas por quantidade.

Uma tabela de preço tem, por produto, uma ou mais faixas `(qtd_min, preco)`.
A faixa aplicada é a de maior `qtd_min` que seja <= quantidade vendida.
Exemplo (picolé): 1+ → R$ 5,00 · 10+ → R$ 4,50 · 50+ → R$ 4,00.

O PDV escolhe a tabela assim: a escolhida na venda > a padrão do cliente > a padrão da loja.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.dinheiro import Centavos, multiplicar


@dataclass(frozen=True, order=True)
class Faixa:
    qtd_min: Decimal
    preco: Centavos


@dataclass(frozen=True)
class PrecoProduto:
    """Faixas de um produto dentro de uma tabela. Precisa de uma faixa que comece em 1 ou menos."""

    faixas: tuple[Faixa, ...]

    def __post_init__(self) -> None:
        if not self.faixas:
            raise ValueError("produto sem faixa de preço")
        ordenadas = tuple(sorted(self.faixas))
        object.__setattr__(self, "faixas", ordenadas)
        if ordenadas[0].qtd_min > 1:
            raise ValueError("a primeira faixa precisa começar em quantidade <= 1")
        minimos = [f.qtd_min for f in ordenadas]
        if len(set(minimos)) != len(minimos):
            raise ValueError("faixas com a mesma quantidade mínima")

    def faixa_para(self, quantidade: Decimal | int) -> Faixa:
        qtd = Decimal(quantidade)
        if qtd <= 0:
            raise ValueError("quantidade precisa ser maior que zero")
        escolhida = self.faixas[0]
        for faixa in self.faixas:
            if faixa.qtd_min <= qtd:
                escolhida = faixa
            else:
                break
        return escolhida

    def preco_unitario(self, quantidade: Decimal | int) -> Centavos:
        return self.faixa_para(quantidade).preco

    def total(self, quantidade: Decimal | int) -> Centavos:
        return multiplicar(self.preco_unitario(quantidade), Decimal(quantidade))


def escolher_tabela(
    escolhida_na_venda: str | None,
    padrao_do_cliente: str | None,
    padrao_da_loja: str,
) -> str:
    """Prioridade: tabela escolhida na venda > padrão do cliente > padrão da loja."""
    return escolhida_na_venda or padrao_do_cliente or padrao_da_loja

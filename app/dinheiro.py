"""Dinheiro em centavos (inteiro). Nunca `float` para valores monetários.

Convenções:
- `Centavos` é um `int`: R$ 12,50 == 1250.
- Quantidades podem ser fracionadas (ex.: 0,350 kg) e são `Decimal`.
- Arredondamento sempre HALF_UP (o que a NFC-e e o consumidor esperam).
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

Centavos = int

_LIMPAR = re.compile(r"[^\d,.\-]")


def de_reais(texto: str | int | float | Decimal) -> Centavos:
    """Converte "R$ 1.234,56", "1234,56", "1234.56" ou um número em centavos.

    Regra para texto: se houver vírgula, ela é o separador decimal e pontos são de milhar;
    se houver só ponto, ele é o decimal (entrada vinda de XML/planilha).
    """
    if isinstance(texto, bool):
        raise TypeError("bool não é valor monetário")
    if isinstance(texto, int):
        return texto * 100
    if isinstance(texto, float):
        return int((Decimal(str(texto)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if isinstance(texto, Decimal):
        return int((texto * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    limpo = _LIMPAR.sub("", texto.strip())
    if not limpo or limpo in {"-", ",", "."}:
        raise ValueError(f"valor monetário inválido: {texto!r}")
    if "," in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    try:
        valor = Decimal(limpo)
    except InvalidOperation as exc:
        raise ValueError(f"valor monetário inválido: {texto!r}") from exc
    return int((valor * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def formatar(centavos: Centavos, simbolo: bool = True) -> str:
    """1234567 -> "R$ 12.345,67"; -150 -> "-R$ 1,50"."""
    negativo = centavos < 0
    reais, cents = divmod(abs(centavos), 100)
    inteiro = f"{reais:,}".replace(",", ".")
    texto = f"{inteiro},{cents:02d}"
    if simbolo:
        texto = f"R$ {texto}"
    return f"-{texto}" if negativo else texto


def multiplicar(preco_unitario: Centavos, quantidade: Decimal | int) -> Centavos:
    """Total de um item: preço × quantidade, arredondado HALF_UP para o centavo."""
    qtd = Decimal(quantidade)
    if qtd < 0:
        raise ValueError("quantidade negativa")
    return int((Decimal(preco_unitario) * qtd).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def percentual(valor: Centavos, pct: Decimal | int | str) -> Centavos:
    """pct% de um valor (ex.: desconto de 10% sobre 1250 -> 125), HALF_UP."""
    p = Decimal(str(pct))
    return int((Decimal(valor) * p / Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def rateio(total: Centavos, pesos: list[int]) -> list[Centavos]:
    """Divide `total` proporcionalmente aos `pesos` sem perder nem criar centavos.

    Usado para distribuir desconto da venda entre itens e para fechar diferenças
    de arredondamento. A sobra vai para as maiores frações (método de Hamilton).
    """
    if not pesos:
        return []
    if any(p < 0 for p in pesos):
        raise ValueError("peso negativo")
    soma = sum(pesos)
    if soma == 0:
        partes = [0] * len(pesos)
        partes[-1] = total
        return partes
    brutos = [Decimal(total) * Decimal(p) / Decimal(soma) for p in pesos]
    pisos = [int(b.to_integral_value(rounding="ROUND_FLOOR")) for b in brutos]
    sobra = total - sum(pisos)
    fracoes = sorted(range(len(pesos)), key=lambda i: brutos[i] - pisos[i], reverse=True)
    for i in fracoes[: abs(sobra)]:
        pisos[i] += 1 if sobra > 0 else -1
    return pisos


def media(total: Centavos, quantidade: int) -> Centavos | None:
    """Valor médio (ex.: ticket médio = faturamento / número de vendas), HALF_UP.

    None quando não há sobre o que calcular: zero vendas não têm média.
    """
    if quantidade <= 0:
        return None
    return int((Decimal(total) / Decimal(quantidade)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def porcentagem(parte: int, todo: int) -> Decimal | None:
    """Quanto `parte` representa de `todo`, em por cento, com uma casa (HALF_UP).

    12,5% volta como Decimal("12.5"). None quando `todo` não é positivo.
    """
    if todo <= 0:
        return None
    return (Decimal(parte) * 100 / Decimal(todo)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

"""Estoque: o saldo de cada produto é a soma dos movimentos. Ninguém edita o saldo direto.

Movimentos: venda (sai), cancelamento de venda (volta), entrada de nota por XML, ajuste (entra
ou sai, sempre com motivo) e inventário (a diferença entre o que foi contado e o saldo).

Custo médio. Cada entrada com custo refaz a média do produto:

    novo custo = (saldo × custo atual + quantidade × custo da entrada) ÷ (saldo + quantidade)

Com saldo zerado ou negativo, ou sem custo anterior, o custo da entrada vira o custo médio.
O custo fica em centavos inteiros (arredondado para o centavo mais próximo): é o que a venda
guarda para o cálculo do lucro. Por causa do arredondamento, uma caixa de 48 unidades que
custou R$ 109,60 entra a R$ 2,28 cada (48 × 2,28 = R$ 109,44): a diferença de centavos fica
fora do valor do estoque.

Saída, contagem e cancelamento de venda mudam a quantidade e não mexem no custo médio.

Vender sem saldo não é bloqueado. O saldo fica negativo e aparece em destaque, para ser
corrigido com uma entrada ou uma contagem.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import tempo
from app.models import MovimentoEstoque, Operador, Produto, TipoMovimentoEstoque
from app.operadores import RegraError

log = logging.getLogger("moleka.estoque")

# Unidades em que a quantidade pode ter casas decimais (ex.: 0,350 kg). As outras são inteiras.
UNIDADES_FRACIONADAS = frozenset({"KG", "G", "L", "ML", "M"})
QUANTIDADE_MAXIMA = Decimal("999999")
MILESIMO = Decimal("0.001")

ROTULOS: dict[TipoMovimentoEstoque, str] = {
    TipoMovimentoEstoque.VENDA: "Venda",
    TipoMovimentoEstoque.CANCELAMENTO: "Venda cancelada",
    TipoMovimentoEstoque.AJUSTE: "Ajuste",
    TipoMovimentoEstoque.ENTRADA_XML: "Entrada de nota",
    TipoMovimentoEstoque.INVENTARIO: "Contagem",
}


def arredondar(quantidade: Decimal) -> Decimal:
    return quantidade.quantize(MILESIMO, rounding=ROUND_HALF_UP)


def conferir_quantidade(
    produto: Produto, quantidade: Decimal, *, aceita_zero: bool = False
) -> Decimal:
    """Recusa quantidade negativa, absurda ou quebrada num produto vendido por unidade inteira."""
    if quantidade < 0 or (quantidade == 0 and not aceita_zero):
        raise RegraError(
            "A quantidade não pode ser negativa."
            if aceita_zero
            else "A quantidade precisa ser maior que zero."
        )
    if quantidade > QUANTIDADE_MAXIMA:
        raise RegraError("Quantidade grande demais. Confira o que foi digitado.")
    fracionada = produto.unidade.upper() in UNIDADES_FRACIONADAS
    if not fracionada and quantidade != quantidade.to_integral_value():
        raise RegraError(
            f"“{produto.descricao}” é controlado por unidade inteira ({produto.unidade}). "
            "Digite a quantidade sem casas decimais."
        )
    return arredondar(quantidade)


# ---------------------------------------------------------------- saldo


def saldos(sessao: Session) -> dict[int, Decimal]:
    """O saldo de todos os produtos que já tiveram movimento."""
    linhas = sessao.execute(
        select(MovimentoEstoque.produto_id, func.sum(MovimentoEstoque.quantidade)).group_by(
            MovimentoEstoque.produto_id
        )
    )
    return {produto_id: arredondar(Decimal(total)) for produto_id, total in linhas}


def saldo(sessao: Session, produto_id: int) -> Decimal:
    total = sessao.scalar(
        select(func.sum(MovimentoEstoque.quantidade)).where(
            MovimentoEstoque.produto_id == produto_id
        )
    )
    return arredondar(Decimal(total)) if total is not None else Decimal("0.000")


# ---------------------------------------------------------------- custo médio


def custo_medio(
    saldo_atual: Decimal, custo_atual: int | None, quantidade: Decimal, custo_entrada: int
) -> int:
    """O custo médio depois de uma entrada (ver a fórmula no começo do arquivo)."""
    if custo_atual is None or saldo_atual <= 0:
        return custo_entrada
    total = saldo_atual * Decimal(custo_atual) + quantidade * Decimal(custo_entrada)
    return int((total / (saldo_atual + quantidade)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def custo_medio_sem_a_entrada(
    saldo_atual: Decimal, custo_atual: int | None, quantidade: Decimal, custo_entrada: int
) -> int | None:
    """O inverso de `custo_medio`, para o estorno de uma entrada.

    Devolve None quando não dá para saber (a entrada estornada era todo o saldo, ou mais).
    """
    resto = saldo_atual - quantidade
    if custo_atual is None or resto <= 0:
        return None
    total = saldo_atual * Decimal(custo_atual) - quantidade * Decimal(custo_entrada)
    if total <= 0:
        return None
    return int((total / resto).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


# ---------------------------------------------------------------- movimentos


def registrar(
    sessao: Session,
    produto: Produto,
    quantidade: Decimal,
    tipo: TipoMovimentoEstoque,
    *,
    operador: Operador | None,
    motivo: str | None = None,
    referencia: str | None = None,
    custo_unitario_centavos: int | None = None,
) -> MovimentoEstoque:
    """Grava um movimento (quantidade negativa = saída). Não mexe no custo."""
    movimento = MovimentoEstoque(
        produto_id=produto.id,
        tipo=tipo,
        quantidade=arredondar(quantidade),
        custo_unitario_centavos=custo_unitario_centavos,
        motivo=" ".join(motivo.split())[:160] if motivo else None,
        referencia=referencia,
        operador_id=operador.id if operador else None,
        em=tempo.agora(),
    )
    sessao.add(movimento)
    return movimento


def entrar(
    sessao: Session,
    produto: Produto,
    quantidade: Decimal,
    tipo: TipoMovimentoEstoque,
    *,
    operador: Operador | None,
    custo_unitario_centavos: int | None = None,
    motivo: str | None = None,
    referencia: str | None = None,
) -> MovimentoEstoque:
    """Entrada de mercadoria. Com custo informado, refaz o custo médio e guarda o último custo."""
    if custo_unitario_centavos is not None:
        if custo_unitario_centavos < 0:
            raise RegraError("O custo não pode ser negativo.")
        antes = saldo(sessao, produto.id)
        produto.custo_centavos = custo_medio(
            antes, produto.custo_centavos, quantidade, custo_unitario_centavos
        )
        produto.ultimo_custo_centavos = custo_unitario_centavos
    return registrar(
        sessao,
        produto,
        quantidade,
        tipo,
        operador=operador,
        motivo=motivo,
        referencia=referencia,
        custo_unitario_centavos=custo_unitario_centavos,
    )


def ajustar(
    sessao: Session,
    operador: Operador,
    produto: Produto,
    *,
    entrada: bool,
    quantidade: Decimal,
    motivo: str,
    custo_unitario_centavos: int | None = None,
) -> MovimentoEstoque:
    """Ajuste manual: entrada (compra sem XML, produção, devolução) ou saída (perda, consumo)."""
    quantidade = conferir_quantidade(produto, quantidade)
    motivo = " ".join(motivo.split())
    if not motivo:
        raise RegraError("Escreva o motivo do ajuste (por exemplo: quebra, produção do dia).")
    if entrada:
        movimento = entrar(
            sessao,
            produto,
            quantidade,
            TipoMovimentoEstoque.AJUSTE,
            operador=operador,
            custo_unitario_centavos=custo_unitario_centavos,
            motivo=motivo,
        )
    else:
        if custo_unitario_centavos is not None:
            raise RegraError("O custo só é informado numa entrada.")
        movimento = registrar(
            sessao,
            produto,
            -quantidade,
            TipoMovimentoEstoque.AJUSTE,
            operador=operador,
            motivo=motivo,
        )
    log.info(
        "ajuste de estoque por %s: %s %s de %s (%s)",
        operador.login,
        "entrada" if entrada else "saída",
        quantidade,
        produto.codigo,
        motivo,
    )
    return movimento


@dataclass(frozen=True)
class Contagem:
    saldo_antes: Decimal
    contado: Decimal
    movimento: MovimentoEstoque | None  # None = o contado bateu com o saldo

    @property
    def diferenca(self) -> Decimal:
        return self.contado - self.saldo_antes


def contar(
    sessao: Session, operador: Operador, produto: Produto, contado: Decimal, motivo: str = ""
) -> Contagem:
    """Inventário de um produto: grava a diferença entre o contado e o saldo do sistema."""
    contado = conferir_quantidade(produto, contado, aceita_zero=True)
    antes = saldo(sessao, produto.id)
    diferenca = contado - antes
    if diferenca == 0:
        return Contagem(antes, contado, None)
    texto = " ".join(motivo.split())
    descricao = (
        f"Contagem: o sistema tinha {texto_da_quantidade(antes)} "
        f"e foram contados {texto_da_quantidade(contado)}"
    )
    movimento = registrar(
        sessao,
        produto,
        diferenca,
        TipoMovimentoEstoque.INVENTARIO,
        operador=operador,
        motivo=f"{descricao}. {texto}" if texto else descricao,
    )
    log.info(
        "contagem de estoque por %s: %s de %s para %s",
        operador.login,
        produto.codigo,
        antes,
        contado,
    )
    return Contagem(antes, contado, movimento)


def texto_da_quantidade(valor: Decimal) -> str:
    """3 → "3"; 0.350 → "0,350"."""
    texto = f"{valor:f}"
    if "." in texto:
        texto = texto.rstrip("0").rstrip(".")
    return texto.replace(".", ",") or "0"

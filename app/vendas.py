"""A venda no caixa: itens, preços, cliente, desconto, pagamentos e finalização.

Contas (tudo em centavos, sem `float`):

    subtotal = soma dos itens (preço da faixa × quantidade)
    base     = subtotal - desconto            (o que a venda vale antes da forma de pagamento)
    total    = base + ajustes das formas      (o que o cliente paga de fato)

Preço por forma de pagamento (decisão do Eric, 11/11/2026): cada forma tem um percentual de
desconto ou acréscimo. Com mais de uma forma na mesma venda, o percentual vale só sobre a
parte paga em cada uma. Cada pagamento guarda o valor que entrou (`valor_centavos`) e o ajuste
embutido nele (`ajuste_centavos`); a parte da venda que ele quita é a diferença dos dois.

Preço do item: tabela do cliente (se ele tiver uma) ou a tabela padrão da loja; dentro da
tabela, vale a faixa de maior quantidade mínima que a quantidade vendida alcança. Produto sem
preço na tabela do cliente usa o preço da tabela padrão.

Qualquer mudança nos itens, no cliente ou no desconto desfaz os pagamentos já lançados, porque
os valores mudam.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import dinheiro, estoque, tempo
from app.models import (
    Cliente,
    FormaPagamento,
    MovimentoEstoque,
    Operador,
    Pagamento,
    Perfil,
    PrecoProduto,
    Produto,
    RegraFormaPagamento,
    SessaoCaixa,
    StatusVenda,
    TabelaPreco,
    TipoMovimentoEstoque,
    Venda,
    VendaItem,
)
from app.operadores import RegraError
from app.precos import Faixa
from app.precos import PrecoProduto as Faixas

log = logging.getLogger("moleka.vendas")

# Unidades em que a quantidade pode ter casas decimais (ex.: 0,350 kg). As outras são inteiras.
UNIDADES_FRACIONADAS = estoque.UNIDADES_FRACIONADAS
AJUSTE_MAXIMO_BP = 5000  # 50%, para mais ou para menos
# Troco acima disto (R$ 1.000,00) quase sempre é engano: valor digitado sem a vírgula ou o
# leitor de código de barras bipado com o cursor no campo do valor.
TROCO_MAXIMO = 100_000


@dataclass(frozen=True)
class Regra:
    ajuste_bp: int = 0
    ativo: bool = True


# ---------------------------------------------------------------- formas de pagamento


def regras_de_pagamento(sessao: Session) -> dict[FormaPagamento, Regra]:
    """A regra de cada forma. Forma sem cadastro vale 0% e está ativa."""
    gravadas = {r.forma: r for r in sessao.scalars(select(RegraFormaPagamento))}
    return {
        forma: Regra(gravadas[forma].ajuste_bp, gravadas[forma].ativo)
        if forma in gravadas
        else Regra()
        for forma in FormaPagamento
    }


def ajuste_sobre(base_centavos: int, ajuste_bp: int) -> int:
    """Desconto (negativo) ou acréscimo (positivo) da forma sobre uma parte da venda."""
    return dinheiro.percentual(base_centavos, Decimal(ajuste_bp) / Decimal(100))


def base_de_um_valor(valor_centavos: int, ajuste_bp: int) -> int:
    """Quanto da venda um valor pago numa forma quita (o inverso de `ajuste_sobre`)."""
    bruto = Decimal(valor_centavos) * Decimal(10000) / Decimal(10000 + ajuste_bp)
    return int(bruto.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


# ---------------------------------------------------------------- tabelas e preços


def tabela_padrao(sessao: Session) -> TabelaPreco:
    tabela = sessao.scalar(
        select(TabelaPreco).where(TabelaPreco.padrao.is_(True), TabelaPreco.ativo.is_(True))
    )
    if tabela is None:
        raise RegraError(
            "Falta a tabela de preço padrão. Cadastre em Cadastros → Tabelas de preço.",
            status=409,
        )
    return tabela


def tabela_do_cliente(sessao: Session, cliente: Cliente | None) -> TabelaPreco:
    if cliente is not None and cliente.tabela is not None and cliente.tabela.ativo:
        return cliente.tabela
    return tabela_padrao(sessao)


def _faixas(sessao: Session, produto_id: int, tabela_id: int) -> Faixas | None:
    linhas = sessao.scalars(
        select(PrecoProduto).where(
            PrecoProduto.produto_id == produto_id, PrecoProduto.tabela_id == tabela_id
        )
    ).all()
    if not linhas:
        return None
    try:
        return Faixas(tuple(Faixa(Decimal(p.qtd_min), p.preco_centavos) for p in linhas))
    except ValueError:
        return None  # cadastro de preço incompleto (sem faixa a partir de 1)


def preco_de(sessao: Session, produto: Produto, tabela: TabelaPreco, quantidade: Decimal) -> Faixa:
    """A faixa de preço que vale para esta quantidade (tabela da venda ou, na falta, a padrão)."""
    faixas = _faixas(sessao, produto.id, tabela.id)
    if faixas is None and not tabela.padrao:
        faixas = _faixas(sessao, produto.id, tabela_padrao(sessao).id)
    if faixas is None:
        raise RegraError(
            f"O produto “{produto.descricao}” está sem preço. Cadastre o preço em Produtos."
        )
    return faixas.faixa_para(quantidade)


def conferir_quantidade(produto: Produto, quantidade: Decimal) -> Decimal:
    if quantidade <= 0:
        raise RegraError("A quantidade precisa ser maior que zero.")
    if quantidade > Decimal("99999"):
        raise RegraError("Quantidade grande demais. Confira o que foi digitado.")
    fracionada = produto.unidade.upper() in UNIDADES_FRACIONADAS
    if not fracionada and quantidade != quantidade.to_integral_value():
        raise RegraError(
            f"“{produto.descricao}” é vendido por unidade inteira ({produto.unidade}). "
            "Digite a quantidade sem casas decimais."
        )
    return quantidade.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------- a venda aberta


def aberta(sessao: Session, sessao_caixa: SessaoCaixa) -> Venda | None:
    return sessao.scalar(
        select(Venda)
        .where(Venda.sessao_id == sessao_caixa.id, Venda.status == StatusVenda.ABERTA)
        .order_by(Venda.id.desc())
    )


def nova(sessao: Session, sessao_caixa: SessaoCaixa, operador: Operador) -> Venda:
    proximo = (sessao.scalar(select(func.max(Venda.numero))) or 0) + 1
    venda = Venda(
        sessao_id=sessao_caixa.id,
        tabela_id=tabela_padrao(sessao).id,
        numero=proximo,
        status=StatusVenda.ABERTA,
        operador_id=operador.id,
        iniciada_em=tempo.agora(),
        subtotal_centavos=0,
        desconto_centavos=0,
        total_centavos=0,
        ajuste_pagamento_centavos=0,
    )
    sessao.add(venda)
    sessao.flush()
    return venda


def base(venda: Venda) -> int:
    """O valor da venda antes do ajuste das formas de pagamento."""
    return venda.subtotal_centavos - venda.desconto_centavos


def quitado(venda: Venda) -> int:
    """Quanto da base os pagamentos lançados já quitam."""
    return sum(p.valor_centavos - p.ajuste_centavos for p in venda.pagamentos)


def restante(venda: Venda) -> int:
    return base(venda) - quitado(venda)


def troco(venda: Venda) -> int:
    return sum(p.troco_centavos for p in venda.pagamentos)


def _somar(venda: Venda) -> None:
    venda.subtotal_centavos = sum(item.total_centavos for item in venda.itens)
    venda.desconto_centavos = min(venda.desconto_centavos, venda.subtotal_centavos)
    if venda.desconto_centavos == 0:
        venda.desconto_por_id = None
    venda.ajuste_pagamento_centavos = sum(p.ajuste_centavos for p in venda.pagamentos)
    venda.total_centavos = base(venda) + venda.ajuste_pagamento_centavos


def _reprecificar(sessao: Session, venda: Venda) -> bool:
    """Recalcula o preço de todos os itens. Devolve True se algum preço unitário mudou."""
    mudou = False
    for item in venda.itens:
        faixa = preco_de(sessao, item.produto, venda.tabela, Decimal(item.quantidade))
        if item.preco_unitario_centavos != faixa.preco:
            mudou = True
        item.preco_unitario_centavos = faixa.preco
        item.faixa_qtd_min = faixa.qtd_min
        item.total_centavos = dinheiro.multiplicar(faixa.preco, Decimal(item.quantidade))
    return mudou


def _mudou(sessao: Session, venda: Venda) -> bool:
    """Depois de mexer em itens, cliente ou desconto: desfaz pagamentos e refaz as contas."""
    venda.pagamentos.clear()
    mudou = _reprecificar(sessao, venda)
    _somar(venda)
    return mudou


def _exigir_aberta(venda: Venda) -> None:
    if venda.status != StatusVenda.ABERTA:
        raise RegraError("Esta venda já foi encerrada.", status=409)


def adicionar_item(sessao: Session, venda: Venda, produto: Produto, quantidade: Decimal) -> None:
    _exigir_aberta(venda)
    if not produto.ativo:
        raise RegraError(f"O produto “{produto.descricao}” está inativo.")
    existente = next((i for i in venda.itens if i.produto_id == produto.id), None)
    total = quantidade + (Decimal(existente.quantidade) if existente else Decimal(0))
    total = conferir_quantidade(produto, total)
    preco_de(sessao, produto, venda.tabela, total)  # recusa produto sem preço antes de gravar
    if existente is not None:
        existente.quantidade = total
    else:
        venda.itens.append(
            VendaItem(
                produto=produto,
                quantidade=total,
                preco_unitario_centavos=0,
                total_centavos=0,
                desconto_centavos=0,
                codigo=produto.codigo,
                descricao=produto.descricao,
                unidade=produto.unidade,
            )
        )
    _mudou(sessao, venda)


def alterar_quantidade(sessao: Session, venda: Venda, item: VendaItem, quantidade: Decimal) -> None:
    _exigir_aberta(venda)
    item.quantidade = conferir_quantidade(item.produto, quantidade)
    _mudou(sessao, venda)


def remover_item(sessao: Session, venda: Venda, item: VendaItem) -> None:
    _exigir_aberta(venda)
    venda.itens.remove(item)
    _mudou(sessao, venda)


def definir_cliente(sessao: Session, venda: Venda, cliente: Cliente | None) -> bool:
    """Escolhe ou troca o cliente da venda. Devolve True se os preços dos itens mudaram."""
    _exigir_aberta(venda)
    if cliente is not None and not cliente.ativo:
        raise RegraError(f"O cliente “{cliente.nome}” está inativo.")
    venda.cliente = cliente
    venda.tabela = tabela_do_cliente(sessao, cliente)
    return _mudou(sessao, venda)


def definir_desconto(sessao: Session, venda: Venda, operador: Operador, centavos: int) -> None:
    """Desconto no total da venda. Decisão do Eric (11/11/2026): só o gerente dá desconto."""
    _exigir_aberta(venda)
    if operador.perfil != Perfil.GERENTE:
        raise RegraError("Só o gerente dá desconto.", status=403)
    if centavos < 0:
        raise RegraError("O desconto não pode ser negativo.")
    if centavos > venda.subtotal_centavos:
        raise RegraError("O desconto não pode ser maior que o total dos itens.")
    venda.desconto_centavos = centavos
    venda.desconto_por_id = operador.id if centavos else None
    _mudou(sessao, venda)


# ---------------------------------------------------------------- pagamentos


def a_pagar_na_forma(venda: Venda, regra: Regra) -> int:
    """Quanto o cliente paga se quitar todo o restante nesta forma."""
    falta = restante(venda)
    return falta + ajuste_sobre(falta, regra.ajuste_bp)


def adicionar_pagamento(
    sessao: Session, venda: Venda, forma: FormaPagamento, valor_centavos: int | None
) -> Pagamento:
    """Lança um pagamento. Sem valor, quita todo o restante nesta forma.

    Em dinheiro, um valor maior que o devido vira troco. Nas outras formas, não pode passar.
    """
    _exigir_aberta(venda)
    if not venda.itens:
        raise RegraError("A venda está sem itens.")
    regra = regras_de_pagamento(sessao)[forma]
    if not regra.ativo:
        raise RegraError("Esta forma de pagamento está desativada.")
    falta = restante(venda)
    if falta <= 0:
        raise RegraError("A venda já está toda paga.")
    devido = a_pagar_na_forma(venda, regra)
    if valor_centavos is None or valor_centavos == devido:
        pagamento = Pagamento(
            forma=forma, valor_centavos=devido, ajuste_centavos=devido - falta, troco_centavos=0
        )
    elif valor_centavos <= 0:
        raise RegraError("Digite um valor maior que zero.")
    elif valor_centavos > devido:
        if forma != FormaPagamento.DINHEIRO:
            raise RegraError(
                f"O valor é maior que o que falta pagar ({dinheiro.formatar(devido)}). "
                "Só o dinheiro tem troco."
            )
        if valor_centavos - devido > TROCO_MAXIMO:
            raise RegraError(
                f"O valor em dinheiro ({dinheiro.formatar(valor_centavos)}) é muito maior que o "
                f"que falta pagar ({dinheiro.formatar(devido)}). Confira o que foi digitado."
            )
        pagamento = Pagamento(
            forma=forma,
            valor_centavos=devido,
            ajuste_centavos=devido - falta,
            troco_centavos=valor_centavos - devido,
        )
    else:
        quita = min(base_de_um_valor(valor_centavos, regra.ajuste_bp), falta)
        pagamento = Pagamento(
            forma=forma,
            valor_centavos=valor_centavos,
            ajuste_centavos=valor_centavos - quita,
            troco_centavos=0,
        )
    venda.pagamentos.append(pagamento)
    _somar(venda)
    return pagamento


def trocar_forma(
    sessao: Session, venda: Venda, pagamento: Pagamento, forma: FormaPagamento
) -> None:
    """Troca a forma de um pagamento já lançado, mantendo a parte da venda que ele quita."""
    _exigir_aberta(venda)
    regra = regras_de_pagamento(sessao)[forma]
    if not regra.ativo:
        raise RegraError("Esta forma de pagamento está desativada.")
    quita = pagamento.valor_centavos - pagamento.ajuste_centavos
    ajuste = ajuste_sobre(quita, regra.ajuste_bp)
    pagamento.forma = forma
    pagamento.ajuste_centavos = ajuste
    pagamento.valor_centavos = quita + ajuste
    pagamento.troco_centavos = 0  # o troco era do valor em dinheiro digitado antes
    _somar(venda)


def remover_pagamento(venda: Venda, pagamento: Pagamento) -> None:
    _exigir_aberta(venda)
    venda.pagamentos.remove(pagamento)
    _somar(venda)


# ---------------------------------------------------------------- encerrar


def finalizar(sessao: Session, venda: Venda, operador: Operador, *, quer_nfce: bool) -> None:
    """Fecha a venda paga: grava a hora, a escolha da NFC-e e dá baixa no estoque."""
    _exigir_aberta(venda)
    if not venda.itens:
        raise RegraError("A venda está sem itens.")
    falta = restante(venda)
    if falta > 0:
        raise RegraError(f"Ainda falta pagar {dinheiro.formatar(falta)}.")
    if falta < 0:
        raise RegraError("Os pagamentos passam do valor da venda. Refaça os pagamentos.")
    _somar(venda)
    agora = tempo.agora()
    venda.status = StatusVenda.FINALIZADA
    venda.finalizada_em = agora
    venda.quer_nfce = quer_nfce
    for item in venda.itens:
        # O custo de hoje fica guardado na venda: o lucro não muda se o custo mudar depois.
        item.custo_unitario_centavos = item.produto.custo_centavos
        sessao.add(
            MovimentoEstoque(
                produto_id=item.produto_id,
                tipo=TipoMovimentoEstoque.VENDA,
                quantidade=-Decimal(item.quantidade),
                referencia=f"venda:{venda.id}",
                operador_id=operador.id,
                em=agora,
            )
        )
    log.info(
        "venda %s finalizada por %s: total %s centavos, %s item(ns)",
        venda.numero,
        operador.login,
        venda.total_centavos,
        len(venda.itens),
    )


def cancelar(sessao: Session, venda: Venda, operador: Operador, motivo: str) -> None:
    """Cancela a venda. Aberta: qualquer operador. Finalizada: só o gerente (estorna o estoque)."""
    if venda.status == StatusVenda.CANCELADA:
        raise RegraError("Esta venda já está cancelada.", status=409)
    motivo = " ".join(motivo.split())[:160]
    agora = tempo.agora()
    if venda.status == StatusVenda.FINALIZADA:
        if operador.perfil != Perfil.GERENTE:
            raise RegraError("Só o gerente cancela uma venda já finalizada.", status=403)
        if not motivo:
            raise RegraError("Escreva o motivo do cancelamento.")
        for item in venda.itens:
            sessao.add(
                MovimentoEstoque(
                    produto_id=item.produto_id,
                    tipo=TipoMovimentoEstoque.CANCELAMENTO,
                    quantidade=Decimal(item.quantidade),
                    referencia=f"venda:{venda.id}",
                    motivo=motivo,
                    operador_id=operador.id,
                    em=agora,
                )
            )
    venda.status = StatusVenda.CANCELADA
    venda.cancelada_em = agora
    venda.cancelada_por_id = operador.id
    venda.motivo_cancelamento = motivo or None
    log.warning(
        "venda %s cancelada por %s (total %s centavos): %s",
        venda.numero,
        operador.login,
        venda.total_centavos,
        motivo or "sem motivo informado",
    )


# ---------------------------------------------------------------- números do dia


@dataclass
class ResumoDoDia:
    dia: date
    quantidade: int
    total_centavos: int
    recebido: dict[FormaPagamento, int]

    @property
    def ticket_medio_centavos(self) -> int | None:
        if not self.quantidade:
            return None
        media = Decimal(self.total_centavos) / Decimal(self.quantidade)
        return int(media.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def resumo_do_dia(sessao: Session, dia: date | None = None) -> ResumoDoDia:
    """Vendas finalizadas num dia da loja (horário de Brasília). Canceladas ficam de fora."""
    dia = dia or tempo.hoje()
    inicio, fim = tempo.limites_do_dia(dia)
    do_dia = (
        (Venda.status == StatusVenda.FINALIZADA)
        & (Venda.finalizada_em >= inicio)
        & (Venda.finalizada_em < fim)
    )
    quantidade, total = sessao.execute(
        select(func.count(Venda.id), func.coalesce(func.sum(Venda.total_centavos), 0)).where(do_dia)
    ).one()
    por_forma = sessao.execute(
        select(Pagamento.forma, func.sum(Pagamento.valor_centavos))
        .join(Venda, Venda.id == Pagamento.venda_id)
        .where(do_dia)
        .group_by(Pagamento.forma)
    )
    return ResumoDoDia(
        dia=dia,
        quantidade=int(quantidade),
        total_centavos=int(total),
        recebido={forma: int(valor) for forma, valor in por_forma},
    )

"""A venda do caixa pela API. Cada pedido devolve a venda inteira, já com as contas refeitas.

Há no máximo uma venda aberta por vez (um caixa na loja). Para vender, o caixa precisa estar
aberto. Todos os valores são centavos inteiros.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import acesso, db, dinheiro, documentos, impressao, tempo, vendas
from app import caixa as regras_do_caixa
from app.fiscal import provedor_configurado
from app.models import Cliente, FormaPagamento, Operador, Produto, StatusVenda, Venda
from app.operadores import RegraError

router = APIRouter(tags=["vendas"])


class ItemOut(BaseModel):
    id: int
    produto_id: int
    codigo: str
    descricao: str
    unidade: str
    quantidade: Decimal
    preco_unitario_centavos: int
    total_centavos: int
    faixa_qtd_min: (
        Decimal | None
    )  # faixa de quantidade aplicada (maior que 1 = preço por quantidade)


class PagamentoOut(BaseModel):
    id: int
    forma: FormaPagamento
    rotulo: str
    valor_centavos: int
    ajuste_centavos: int
    troco_centavos: int


class ClienteDaVenda(BaseModel):
    id: int
    nome: str
    documento: str


class FormaDaVenda(BaseModel):
    forma: FormaPagamento
    rotulo: str
    ajuste_bp: int
    ativo: bool
    a_pagar_centavos: int  # quanto o cliente paga se quitar todo o restante nesta forma


class VendaOut(BaseModel):
    id: int
    numero: int
    status: StatusVenda
    operador: str | None
    cliente: ClienteDaVenda | None
    tabela: str
    itens: list[ItemOut]
    subtotal_centavos: int
    desconto_centavos: int
    base_centavos: int  # subtotal - desconto
    ajuste_pagamento_centavos: int
    total_centavos: int  # o que o cliente paga, com o ajuste das formas já lançadas
    pagamentos: list[PagamentoOut]
    restante_centavos: int  # quanto da base ainda falta quitar
    troco_centavos: int
    pode_finalizar: bool
    formas: list[FormaDaVenda]
    quer_nfce: bool | None
    iniciada_em: str | None
    finalizada_em: str | None
    cancelada_em: str | None
    motivo_cancelamento: str | None


class DepoisDaVendaOut(BaseModel):
    """O que a impressora de cupom fez logo depois da venda finalizada."""

    impressora: str  # vazio = nenhuma escolhida em Configurações
    quando: str  # perguntar, sempre ou nunca
    enviado: bool  # o comprovante foi para a fila sozinho
    erro: str  # por que o comprovante (ou a gaveta) falhou; vazio = nada falhou


class EstadoOut(BaseModel):
    caixa_aberto: bool
    venda: VendaOut | None
    nfce_disponivel: bool
    nfce_motivo: str
    aviso: str | None = None  # recado para o operador (ex.: os preços mudaram com o cliente)
    depois: DepoisDaVendaOut | None = None  # só na resposta da finalização


class ItemIn(BaseModel):
    produto_id: int | None = None
    codigo: str | None = None  # código interno ou código de barras, como o leitor envia
    quantidade: str | int | float = 1


class QuantidadeIn(BaseModel):
    quantidade: str | int | float


class ClienteIn(BaseModel):
    cliente_id: int | None = None


class DescontoIn(BaseModel):
    centavos: int | None = None
    percentual: str | int | float | None = None


class PagamentoIn(BaseModel):
    forma: FormaPagamento
    valor_centavos: int | None = None  # vazio = todo o restante nesta forma


class FormaIn(BaseModel):
    forma: FormaPagamento


class FinalizarIn(BaseModel):
    emitir_nfce: bool = False


class CancelarIn(BaseModel):
    motivo: str = ""


class ResumoOut(BaseModel):
    dia: str
    quantidade: int
    total_centavos: int | None  # None = sem vendas no dia (a tela mostra "—")
    ticket_medio_centavos: int | None
    recebido: dict[FormaPagamento, int]
    motivo: str  # por que não há número, quando não há


def _quantidade(valor: str | int | float) -> Decimal:
    try:
        return Decimal(str(valor).strip().replace(",", "."))
    except (InvalidOperation, ValueError) as erro:
        raise RegraError("Quantidade inválida.") from erro


def venda_out(sessao: Session, venda: Venda) -> VendaOut:
    regras = vendas.regras_de_pagamento(sessao)
    falta = vendas.restante(venda) if venda.status == StatusVenda.ABERTA else 0
    return VendaOut(
        id=venda.id,
        numero=venda.numero,
        status=venda.status,
        operador=venda.operador.nome if venda.operador else None,
        cliente=ClienteDaVenda(
            id=venda.cliente.id,
            nome=venda.cliente.nome,
            documento=documentos.formatar(venda.cliente.cpf_cnpj),
        )
        if venda.cliente
        else None,
        tabela=venda.tabela.nome,
        itens=[
            ItemOut(
                id=i.id,
                produto_id=i.produto_id,
                codigo=i.codigo or i.produto.codigo,
                descricao=i.descricao or i.produto.descricao,
                unidade=i.unidade or i.produto.unidade,
                quantidade=Decimal(i.quantidade),
                preco_unitario_centavos=i.preco_unitario_centavos,
                total_centavos=i.total_centavos,
                faixa_qtd_min=i.faixa_qtd_min,
            )
            for i in venda.itens
        ],
        subtotal_centavos=venda.subtotal_centavos,
        desconto_centavos=venda.desconto_centavos,
        base_centavos=vendas.base(venda),
        ajuste_pagamento_centavos=venda.ajuste_pagamento_centavos,
        total_centavos=venda.total_centavos,
        pagamentos=[
            PagamentoOut(
                id=p.id,
                forma=p.forma,
                rotulo=regras_do_caixa.ROTULOS[p.forma],
                valor_centavos=p.valor_centavos,
                ajuste_centavos=p.ajuste_centavos,
                troco_centavos=p.troco_centavos,
            )
            for p in venda.pagamentos
        ],
        restante_centavos=falta,
        troco_centavos=vendas.troco(venda),
        pode_finalizar=venda.status == StatusVenda.ABERTA and bool(venda.itens) and falta == 0,
        formas=[
            FormaDaVenda(
                forma=forma,
                rotulo=regras_do_caixa.ROTULOS[forma],
                ajuste_bp=regra.ajuste_bp,
                ativo=regra.ativo,
                a_pagar_centavos=falta + vendas.ajuste_sobre(falta, regra.ajuste_bp),
            )
            for forma, regra in regras.items()
        ],
        quer_nfce=venda.quer_nfce,
        iniciada_em=tempo.iso_na_loja(venda.iniciada_em),
        finalizada_em=tempo.iso_na_loja(venda.finalizada_em),
        cancelada_em=tempo.iso_na_loja(venda.cancelada_em),
        motivo_cancelamento=venda.motivo_cancelamento,
    )


def _estado(sessao: Session, venda: Venda | None, aviso: str | None = None) -> EstadoOut:
    fiscal = provedor_configurado().status()
    return EstadoOut(
        caixa_aberto=regras_do_caixa.aberta(sessao) is not None,
        venda=venda_out(sessao, venda) if venda else None,
        nfce_disponivel=fiscal.configurado,
        nfce_motivo=fiscal.motivo,
        aviso=aviso,
    )


def _venda_aberta(sessao: Session) -> Venda:
    venda = vendas.aberta(sessao, regras_do_caixa.exigir_aberta(sessao))
    if venda is None:
        raise RegraError("Não há venda aberta.", status=409)
    return venda


def _responder(sessao: Session, venda: Venda, aviso: str | None = None) -> EstadoOut:
    sessao.commit()
    sessao.refresh(venda)
    return _estado(sessao, venda, aviso)


# ---------------------------------------------------------------- venda aberta


@router.get("/venda", response_model=EstadoOut)
def ver_venda(sessao: Session = Depends(db.sessao)) -> EstadoOut:
    sessao_caixa = regras_do_caixa.aberta(sessao)
    return _estado(sessao, vendas.aberta(sessao, sessao_caixa) if sessao_caixa else None)


@router.post("/venda/itens", response_model=EstadoOut, status_code=201)
def adicionar_item(
    dados: ItemIn,
    sessao: Session = Depends(db.sessao),
    operador: Operador = Depends(acesso.exigir_operador),
) -> EstadoOut:
    """Acrescenta um produto à venda (abre a venda, se não houver). Repetido soma a quantidade."""
    sessao_caixa = regras_do_caixa.exigir_aberta(sessao)
    produto: Produto | None = None
    if dados.produto_id is not None:
        produto = sessao.get(Produto, dados.produto_id)
    elif dados.codigo and dados.codigo.strip():
        codigo = dados.codigo.strip()
        ativos = select(Produto).where(Produto.ativo.is_(True))
        produto = sessao.scalar(ativos.where(Produto.ean == codigo)) or sessao.scalar(
            ativos.where(Produto.codigo == codigo)
        )
    if produto is None:
        raise RegraError("Produto não encontrado.", status=404)
    venda = vendas.aberta(sessao, sessao_caixa) or vendas.nova(sessao, sessao_caixa, operador)
    vendas.adicionar_item(sessao, venda, produto, _quantidade(dados.quantidade))
    return _responder(sessao, venda)


@router.put("/venda/itens/{item_id}", response_model=EstadoOut)
def alterar_item(
    item_id: int,
    dados: QuantidadeIn,
    sessao: Session = Depends(db.sessao),
    _operador: Operador = Depends(acesso.exigir_operador),
) -> EstadoOut:
    venda = _venda_aberta(sessao)
    item = next((i for i in venda.itens if i.id == item_id), None)
    if item is None:
        raise HTTPException(404, "Item não encontrado nesta venda.")
    vendas.alterar_quantidade(sessao, venda, item, _quantidade(dados.quantidade))
    return _responder(sessao, venda)


@router.delete("/venda/itens/{item_id}", response_model=EstadoOut)
def remover_item(
    item_id: int,
    sessao: Session = Depends(db.sessao),
    _operador: Operador = Depends(acesso.exigir_operador),
) -> EstadoOut:
    venda = _venda_aberta(sessao)
    item = next((i for i in venda.itens if i.id == item_id), None)
    if item is None:
        raise HTTPException(404, "Item não encontrado nesta venda.")
    vendas.remover_item(sessao, venda, item)
    return _responder(sessao, venda)


@router.put("/venda/cliente", response_model=EstadoOut)
def definir_cliente(
    dados: ClienteIn,
    sessao: Session = Depends(db.sessao),
    operador: Operador = Depends(acesso.exigir_operador),
) -> EstadoOut:
    """Escolhe ou troca o cliente (vazio = consumidor final). Pode abrir a venda pelo cliente."""
    sessao_caixa = regras_do_caixa.exigir_aberta(sessao)
    cliente = None
    if dados.cliente_id is not None:
        cliente = sessao.get(Cliente, dados.cliente_id)
        if cliente is None:
            raise HTTPException(404, "Cliente não encontrado.")
    venda = vendas.aberta(sessao, sessao_caixa)
    if venda is None:
        if cliente is None:
            return _estado(sessao, None)
        venda = vendas.nova(sessao, sessao_caixa, operador)
    tinha_pagamentos = bool(venda.pagamentos)
    mudou = vendas.definir_cliente(sessao, venda, cliente)
    avisos = []
    if mudou:
        avisos.append(f"Os preços foram recalculados pela tabela {venda.tabela.nome}.")
    if tinha_pagamentos:
        avisos.append("Os pagamentos foram desfeitos; lance de novo.")
    return _responder(sessao, venda, " ".join(avisos) or None)


@router.put("/venda/desconto", response_model=EstadoOut)
def definir_desconto(
    dados: DescontoIn,
    sessao: Session = Depends(db.sessao),
    operador: Operador = Depends(acesso.exigir_operador),
) -> EstadoOut:
    venda = _venda_aberta(sessao)
    if dados.percentual is not None:
        try:
            pct = Decimal(str(dados.percentual).strip().replace(",", "."))
        except (InvalidOperation, ValueError) as erro:
            raise RegraError("Percentual inválido.") from erro
        if not 0 <= pct <= 100:
            raise RegraError("O desconto em % vai de 0 a 100.")
        centavos = dinheiro.percentual(venda.subtotal_centavos, pct)
    else:
        centavos = dados.centavos or 0
    vendas.definir_desconto(sessao, venda, operador, centavos)
    return _responder(sessao, venda)


@router.post("/venda/pagamentos", response_model=EstadoOut, status_code=201)
def adicionar_pagamento(
    dados: PagamentoIn,
    sessao: Session = Depends(db.sessao),
    _operador: Operador = Depends(acesso.exigir_operador),
) -> EstadoOut:
    venda = _venda_aberta(sessao)
    vendas.adicionar_pagamento(sessao, venda, dados.forma, dados.valor_centavos)
    return _responder(sessao, venda)


@router.put("/venda/pagamentos/{pagamento_id}", response_model=EstadoOut)
def trocar_forma(
    pagamento_id: int,
    dados: FormaIn,
    sessao: Session = Depends(db.sessao),
    _operador: Operador = Depends(acesso.exigir_operador),
) -> EstadoOut:
    """Troca a forma de um pagamento já lançado (ex.: era débito, o cliente passou no crédito)."""
    venda = _venda_aberta(sessao)
    pagamento = next((p for p in venda.pagamentos if p.id == pagamento_id), None)
    if pagamento is None:
        raise HTTPException(404, "Pagamento não encontrado nesta venda.")
    vendas.trocar_forma(sessao, venda, pagamento, dados.forma)
    return _responder(sessao, venda)


@router.delete("/venda/pagamentos/{pagamento_id}", response_model=EstadoOut)
def remover_pagamento(
    pagamento_id: int,
    sessao: Session = Depends(db.sessao),
    _operador: Operador = Depends(acesso.exigir_operador),
) -> EstadoOut:
    venda = _venda_aberta(sessao)
    pagamento = next((p for p in venda.pagamentos if p.id == pagamento_id), None)
    if pagamento is None:
        raise HTTPException(404, "Pagamento não encontrado nesta venda.")
    vendas.remover_pagamento(venda, pagamento)
    return _responder(sessao, venda)


@router.post("/venda/finalizar", response_model=EstadoOut)
def finalizar(
    dados: FinalizarIn,
    sessao: Session = Depends(db.sessao),
    operador: Operador = Depends(acesso.exigir_operador),
) -> EstadoOut:
    """Encerra a venda paga. A NFC-e só pode ser pedida quando o fiscal estiver configurado."""
    venda = _venda_aberta(sessao)
    fiscal = provedor_configurado().status()
    if dados.emitir_nfce and not fiscal.configurado:
        raise RegraError(
            f"A NFC-e ainda não pode ser emitida ({fiscal.motivo}). Finalize sem NFC-e.",
            status=409,
        )
    vendas.finalizar(sessao, venda, operador, quer_nfce=dados.emitir_nfce)
    estado = _responder(sessao, venda)
    # A venda já está gravada: a impressora não pode desfazer nem travar a finalização.
    depois = impressao.depois_da_venda(sessao, venda)
    estado.depois = DepoisDaVendaOut(
        impressora=depois.impressora,
        quando=depois.quando,
        enviado=depois.enviado,
        erro=depois.erro,
    )
    return estado


@router.post("/venda/cancelar", response_model=EstadoOut)
def cancelar_aberta(
    dados: CancelarIn,
    sessao: Session = Depends(db.sessao),
    operador: Operador = Depends(acesso.exigir_operador),
) -> EstadoOut:
    venda = _venda_aberta(sessao)
    vendas.cancelar(sessao, venda, operador, dados.motivo)
    return _responder(sessao, venda)


# ---------------------------------------------------------------- vendas encerradas


@router.get("/vendas/resumo-hoje", response_model=ResumoOut)
def resumo_de_hoje(sessao: Session = Depends(db.sessao)) -> ResumoOut:
    """Saldo de vendas do dia (horário de Brasília), para o caixa e para a tela inicial."""
    resumo = vendas.resumo_do_dia(sessao)
    tem = resumo.quantidade > 0
    return ResumoOut(
        dia=resumo.dia.isoformat(),
        quantidade=resumo.quantidade,
        total_centavos=resumo.total_centavos if tem else None,
        ticket_medio_centavos=resumo.ticket_medio_centavos,
        recebido=resumo.recebido,
        motivo="" if tem else "sem vendas finalizadas hoje",
    )


@router.get("/vendas", response_model=list[VendaOut])
def listar_vendas(
    sessao_id: int | None = None,
    limite: int = 100,
    sessao: Session = Depends(db.sessao),
) -> list[VendaOut]:
    """Vendas encerradas de uma sessão de caixa (padrão: a aberta), da mais nova para a antiga."""
    if sessao_id is None:
        aberta = regras_do_caixa.aberta(sessao)
        if aberta is None:
            return []
        sessao_id = aberta.id
    consulta = (
        select(Venda)
        .where(Venda.sessao_id == sessao_id, Venda.status != StatusVenda.ABERTA)
        .order_by(Venda.id.desc())
        .limit(max(1, min(limite, 500)))
    )
    return [venda_out(sessao, v) for v in sessao.scalars(consulta)]


@router.post("/vendas/{venda_id}/cancelar", response_model=VendaOut)
def cancelar_encerrada(
    venda_id: int,
    dados: CancelarIn,
    sessao: Session = Depends(db.sessao),
    gerente: Operador = Depends(acesso.exigir_gerente),
) -> VendaOut:
    """Cancela uma venda já finalizada (só o gerente): estorna o estoque e sai dos totais."""
    venda = sessao.get(Venda, venda_id)
    if venda is None:
        raise HTTPException(404, "Venda não encontrada.")
    if venda.status == StatusVenda.ABERTA:
        raise RegraError("Esta venda ainda está aberta: cancele pela tela do caixa.", status=409)
    if venda.sessao.fechado_em is not None:
        raise RegraError(
            "O caixa desta venda já foi fechado. O cancelamento depois do fechamento ainda "
            "não está disponível.",
            status=409,
        )
    vendas.cancelar(sessao, venda, gerente, dados.motivo)
    sessao.commit()
    sessao.refresh(venda)
    return venda_out(sessao, venda)

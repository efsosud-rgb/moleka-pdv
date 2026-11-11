"""Entrada de compras pela NF-e do fornecedor (XML).

O caminho é em dois passos, para ninguém gravar sem ver:
1. conferir: o XML é lido (app/nfe_xml.py) e cada item recebe uma sugestão de qual produto
   nosso ele é. Nada é gravado;
2. importar: com a decisão do gerente para cada item (ligar a um produto, criar um produto novo
   ou não dar entrada), o sistema grava a nota, dá entrada no estoque, refaz o custo médio,
   memoriza a ligação "código do fornecedor → nosso produto" e cria as contas a pagar das
   parcelas da nota.

Fator de conversão: quantas unidades do nosso produto há em cada unidade da nota. Caixa com 24
picolés, comprada por caixa e vendida por unidade: fator 24.

    quantidade que entra = quantidade da nota × fator
    custo por unidade    = custo do item na nota ÷ quantidade que entra

O XML é lido de novo no passo 2: os valores gravados são sempre os do arquivo, nunca os que a
tela mandou. A mesma nota (chave de acesso) não entra duas vezes.

Estorno: desfaz a entrada no estoque, volta o custo médio quando dá para calcular e cancela as
contas a pagar em aberto daquela nota. A nota continua no histórico, marcada como estornada, e
pode ser importada de novo.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import catalogo, config, estoque, financeiro, nfe_xml, tempo
from app.models import (
    CategoriaFinanceira,
    DeParaFornecedor,
    Lancamento,
    MovimentoEstoque,
    NotaEntrada,
    NotaEntradaItem,
    Operador,
    OrigemLancamento,
    Produto,
    TipoLancamento,
    TipoMovimentoEstoque,
)
from app.operadores import RegraError

log = logging.getLogger("moleka.compras")

FATOR_MAXIMO = Decimal("100000")
ACOES = ("vincular", "criar", "ignorar")


@dataclass(frozen=True)
class Sugestao:
    """Qual produto nosso parece ser o item da nota, e por quê."""

    produto: Produto | None
    fator: Decimal
    origem: str | None  # "memoria" (já ligado antes), "ean" (código de barras) ou None


@dataclass(frozen=True)
class Decisao:
    """O que o gerente decidiu para um item da nota."""

    numero: int
    acao: str  # vincular, criar ou ignorar
    produto_id: int | None = None
    fator: Decimal = Decimal(1)


@dataclass(frozen=True)
class Importacao:
    nota: NotaEntrada
    produtos_criados: list[Produto]
    contas_a_pagar: int


# ---------------------------------------------------------------- conferir


def ja_importada(sessao: Session, chave: str) -> NotaEntrada | None:
    return sessao.scalar(select(NotaEntrada).where(NotaEntrada.chave == chave))


def sugerir(sessao: Session, nota: nfe_xml.Nota) -> dict[int, Sugestao]:
    """Uma sugestão por item (pelo número do item na nota)."""
    memoria = {
        d.codigo_fornecedor: d
        for d in sessao.scalars(
            select(DeParaFornecedor).where(
                DeParaFornecedor.fornecedor_cnpj == nota.emitente_documento
            )
        )
    }
    sugestoes: dict[int, Sugestao] = {}
    for item in nota.itens:
        fator_da_nota = item.fator_da_nota or Decimal(1)
        lembrado = memoria.get(item.codigo)
        produto = sessao.get(Produto, lembrado.produto_id) if lembrado else None
        if lembrado is not None and produto is not None and produto.ativo:
            sugestoes[item.numero] = Sugestao(produto, Decimal(lembrado.fator_conversao), "memoria")
            continue
        # Código de barras: o da unidade comercial (fator 1) ou o da unidade tributável.
        achado = _produto_pelo_ean(sessao, item.ean)
        if achado is not None:
            sugestoes[item.numero] = Sugestao(achado, Decimal(1), "ean")
            continue
        achado = _produto_pelo_ean(sessao, item.ean_tributavel)
        if achado is not None:
            sugestoes[item.numero] = Sugestao(achado, fator_da_nota, "ean")
            continue
        sugestoes[item.numero] = Sugestao(None, fator_da_nota, None)
    return sugestoes


def _produto_pelo_ean(sessao: Session, ean: str | None) -> Produto | None:
    if not ean:
        return None
    return sessao.scalar(select(Produto).where(Produto.ean == ean, Produto.ativo.is_(True)))


# ---------------------------------------------------------------- importar


def quantidade_que_entra(quantidade_da_nota: Decimal, fator: Decimal) -> Decimal:
    """Quantidade da nota × fator, em três casas (é assim que a nota fica gravada)."""
    return estoque.arredondar(estoque.arredondar(Decimal(quantidade_da_nota)) * Decimal(fator))


def custo_por_unidade(custo_total_centavos: int, entra: Decimal) -> int:
    """Custo de cada unidade que entrou, arredondado para o centavo."""
    bruto = Decimal(custo_total_centavos) / entra
    return int(bruto.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def unidade_do_produto_novo(item: nfe_xml.ItemNota, fator: Decimal) -> str:
    """A unidade com que nasce o produto criado a partir de um item da nota.

    Fator 1: a mesma unidade da nota. Outro fator: o nosso produto é o que vem dentro da
    embalagem — vale a unidade tributável da nota quando ela é diferente da comercial (CX com
    24 UN), e "UN" quando a nota não diz.
    """
    if fator == 1:
        return (item.unidade or "UN")[:6].upper()
    por_dentro = item.unidade_tributavel
    if por_dentro and por_dentro.upper() != item.unidade.upper():
        return por_dentro[:6].upper()
    return "UN"


def _criar_produto(sessao: Session, item: nfe_xml.ItemNota, fator: Decimal) -> Produto:
    """Produto novo a partir do item da nota. Nasce sem preço de venda (o gerente põe depois)."""
    # Com fator diferente de 1, o nosso produto é a unidade de dentro da caixa.
    ean = item.ean_tributavel if fator != 1 else item.ean
    if ean and _produto_pelo_ean(sessao, ean) is not None:
        ean = None  # já é de outro produto: fica sem código de barras, para não duplicar
    produto = Produto(
        codigo=catalogo.proximo_codigo(sessao),
        descricao=item.descricao[:120],
        ean=ean,
        unidade=unidade_do_produto_novo(item, fator),
        ncm=item.ncm if item.ncm and item.ncm.isdigit() and len(item.ncm) == 8 else None,
        origem="0",
        estoque_minimo=Decimal(0),
        ativo=True,
    )
    sessao.add(produto)
    sessao.flush()
    return produto


def _guardar_xml(chave: str, texto: str) -> str:
    """Guarda o arquivo da nota na pasta de dados. Devolve o caminho relativo a ela, sempre com
    barras normais: o que fica gravado no banco é igual no Windows e fora dele."""
    pasta = config.pasta_dados() / "xml" / "entrada"
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / f"{chave}.xml").write_text(texto, encoding="utf-8")
    return f"xml/entrada/{chave}.xml"


def importar(
    sessao: Session,
    operador: Operador,
    texto_xml: str,
    decisoes: list[Decisao],
    *,
    gerar_contas: bool = True,
    categoria_id: int | None = None,
    vencimento_sem_parcelas: date | None = None,
    chave_esperada: str | None = None,
) -> Importacao:
    """Grava a nota e tudo o que decorre dela (ver o começo do arquivo).

    Contas a pagar (`gerar_contas`): uma por parcela da nota. Nota sem parcelas só gera conta
    se vier `vencimento_sem_parcelas` (uma conta com o total da nota, nesse vencimento).
    `categoria_id` é a categoria dessas contas; sem ela, "Compra de mercadorias para revenda".
    `chave_esperada` é a chave da nota que a pessoa conferiu na tela: se o arquivo enviado for de
    outra nota, nada é gravado (as decisões foram tomadas olhando para outra nota).
    """
    nota = nfe_xml.ler(texto_xml)
    if chave_esperada is not None and nota.chave != chave_esperada:
        raise RegraError(
            "O arquivo enviado não é o da nota que estava na tela. "
            "Escolha o arquivo de novo e confira antes de importar.",
            status=409,
        )
    registro = ja_importada(sessao, nota.chave)
    if registro is not None and registro.estornada_em is None:
        dia = tempo.na_loja(registro.importada_em).strftime("%d/%m/%Y")
        raise RegraError(f"Esta nota já foi importada em {dia}.", status=409)

    por_numero = {d.numero: d for d in decisoes}
    if len(por_numero) != len(decisoes):
        raise RegraError("Há mais de uma decisão para o mesmo item.")
    faltando = [str(i.numero) for i in nota.itens if i.numero not in por_numero]
    if faltando:
        raise RegraError(f"Falta decidir o que fazer com o item {', '.join(faltando)} da nota.")
    if set(por_numero) - {i.numero for i in nota.itens}:
        raise RegraError("Há decisão para um item que não existe nesta nota.")

    # 1) Confere tudo antes de gravar qualquer coisa.
    contas_previstas = _contas_previstas(nota, gerar_contas, vencimento_sem_parcelas)
    categoria = None
    if contas_previstas:
        categoria = _categoria_das_contas(sessao, categoria_id)
    plano: list[tuple[nfe_xml.ItemNota, Decisao, Produto | None, Decimal]] = []
    for item in nota.itens:
        decisao = por_numero[item.numero]
        if decisao.acao not in ACOES:
            raise RegraError(f"Item {item.numero}: escolha o que fazer com ele.")
        if decisao.acao == "ignorar":
            plano.append((item, decisao, None, Decimal(0)))
            continue
        # Três casas, como o banco guarda: o estorno refaz exatamente a mesma conta.
        fator = estoque.arredondar(Decimal(decisao.fator))
        if fator <= 0:
            raise RegraError(
                f"Item {item.numero}: o fator de conversão precisa ser maior que zero."
            )
        if fator > FATOR_MAXIMO:
            raise RegraError(
                f"Item {item.numero}: o fator de conversão está grande demais. "
                "Confira o que foi digitado."
            )
        produto = None
        if decisao.acao == "vincular":
            produto = sessao.get(Produto, decisao.produto_id) if decisao.produto_id else None
            if produto is None:
                raise RegraError(f"Item {item.numero}: escolha o produto que recebe a entrada.")
            if not produto.ativo:
                raise RegraError(
                    f"Item {item.numero}: o produto “{produto.descricao}” está inativo."
                )
        entra = quantidade_que_entra(item.quantidade, fator)
        if entra <= 0:
            raise RegraError(
                f"Item {item.numero}: a quantidade que entra ficou zerada. "
                "Confira o fator de conversão."
            )
        if produto is not None:
            try:
                estoque.conferir_quantidade(produto, entra)
            except RegraError as erro:
                raise RegraError(
                    f"Item {item.numero}: {erro} Confira o fator de conversão."
                ) from erro
        else:  # produto novo: a mesma regra, com a unidade que ele vai ter
            unidade = unidade_do_produto_novo(item, fator)
            if unidade not in estoque.UNIDADES_FRACIONADAS and entra != entra.to_integral_value():
                quanto = estoque.texto_da_quantidade(entra)
                raise RegraError(
                    f"Item {item.numero}: entrariam {quanto} {unidade}, e esta unidade não "
                    "aceita quantidade quebrada. Confira o fator de conversão."
                )
        plano.append((item, replace(decisao, fator=fator), produto, entra))

    # 2) Grava: nota, itens, estoque, custo, memória do fornecedor e contas a pagar.
    caminho = _guardar_xml(nota.chave, texto_xml)
    if registro is None:
        registro = NotaEntrada(chave=nota.chave)
        sessao.add(registro)
    else:  # nota estornada sendo importada de novo: o registro é reaproveitado
        registro.itens.clear()
        sessao.flush()
    registro.fornecedor_cnpj = nota.emitente_documento
    registro.fornecedor_nome = nota.emitente_nome
    registro.numero = nota.numero
    registro.serie = nota.serie
    registro.emitida_em = nota.emitida_em
    registro.total_centavos = nota.total_centavos
    registro.xml_caminho = caminho
    registro.importada_em = tempo.agora()
    registro.importada_por_id = operador.id
    registro.estornada_em = None
    registro.estornada_por_id = None
    registro.motivo_estorno = None
    sessao.flush()

    criados: list[Produto] = []
    for item, decisao, produto, entra in plano:
        if decisao.acao == "criar":
            produto = _criar_produto(sessao, item, Decimal(decisao.fator))
            criados.append(produto)
        linha = NotaEntradaItem(
            produto_id=produto.id if produto else None,
            numero=item.numero,
            codigo_fornecedor=item.codigo,
            ean=item.ean,
            descricao=item.descricao,
            ncm=item.ncm[:8] if item.ncm else None,
            unidade=item.unidade,
            quantidade=estoque.arredondar(item.quantidade),
            valor_unitario_centavos=item.valor_unitario_centavos,
            valor_total_centavos=item.valor_total_centavos,
            fator_conversao=Decimal(decisao.fator) if produto else Decimal(1),
            custo_total_centavos=item.custo_total_centavos,
        )
        registro.itens.append(linha)
        if produto is None:
            continue
        linha.custo_antes_centavos = produto.custo_centavos
        estoque.entrar(
            sessao,
            produto,
            entra,
            TipoMovimentoEstoque.ENTRADA_XML,
            operador=operador,
            custo_unitario_centavos=custo_por_unidade(item.custo_total_centavos, entra),
            motivo=f"NF {nota.numero} de {nota.emitente_nome}",
            referencia=f"nota:{registro.id}",
        )
        linha.custo_depois_centavos = produto.custo_centavos
        sessao.flush()  # o próximo item do mesmo produto já enxerga este saldo
        _memorizar(sessao, nota.emitente_documento, item.codigo, produto, Decimal(decisao.fator))

    contas = 0
    for descricao, vencimento, valor in contas_previstas:
        assert categoria is not None
        financeiro.criar_lancamento(
            sessao,
            operador,
            tipo=TipoLancamento.DESPESA,
            categoria_id=categoria.id,
            descricao=descricao,
            valor_centavos=valor,
            vencimento=vencimento,
            competencia=tempo.na_loja(nota.emitida_em).date(),
            origem=OrigemLancamento.COMPRA,
            referencia=f"nota:{registro.id}",
        )
        contas += 1
    sessao.commit()
    log.info(
        "nota %s de %s importada por %s: %s item(ns), %s produto(s) criado(s), %s conta(s) a pagar",
        nota.numero,
        nota.emitente_documento,
        operador.login,
        len(nota.itens),
        len(criados),
        contas,
    )
    return Importacao(registro, criados, contas)


def _contas_previstas(
    nota: nfe_xml.Nota, gerar_contas: bool, vencimento_sem_parcelas: date | None
) -> list[tuple[str, date, int]]:
    """(descrição, vencimento, centavos) de cada conta a pagar que a importação vai criar."""
    if not gerar_contas:
        return []
    origem = f"NF {nota.numero} de {nota.emitente_nome}"
    if nota.parcelas:
        return [
            (f"{origem}, parcela {p.numero}"[:160], p.vencimento, p.valor_centavos)
            for p in nota.parcelas
        ]
    if vencimento_sem_parcelas is not None and nota.total_centavos > 0:
        return [(origem[:160], vencimento_sem_parcelas, nota.total_centavos)]
    return []


def _categoria_das_contas(sessao: Session, categoria_id: int | None) -> CategoriaFinanceira:
    if categoria_id is None:
        return financeiro.categoria_de_compras(sessao)
    categoria = sessao.get(CategoriaFinanceira, categoria_id)
    if categoria is None:
        raise RegraError("Escolha a categoria das contas a pagar.")
    if categoria.grupo_dre not in financeiro.GRUPOS_DE_DESPESA:
        raise RegraError(f"A categoria “{categoria.nome}” não serve para despesa.")
    if not categoria.ativo:
        raise RegraError(f"A categoria “{categoria.nome}” está inativa.")
    return categoria


def _memorizar(
    sessao: Session, documento: str, codigo: str, produto: Produto, fator: Decimal
) -> None:
    lembrado = sessao.scalar(
        select(DeParaFornecedor).where(
            DeParaFornecedor.fornecedor_cnpj == documento,
            DeParaFornecedor.codigo_fornecedor == codigo,
        )
    )
    if lembrado is None:
        lembrado = DeParaFornecedor(fornecedor_cnpj=documento, codigo_fornecedor=codigo)
        sessao.add(lembrado)
    lembrado.produto_id = produto.id
    lembrado.fator_conversao = fator
    sessao.flush()


# ---------------------------------------------------------------- estornar


def contas_da_nota(sessao: Session, nota: NotaEntrada) -> list[Lancamento]:
    return list(
        sessao.scalars(
            select(Lancamento).where(
                Lancamento.referencia == f"nota:{nota.id}",
                Lancamento.origem == OrigemLancamento.COMPRA,
                Lancamento.cancelado_em.is_(None),
            )
        )
    )


def _ultimo_custo_fora_da_nota(sessao: Session, produto: Produto, nota: NotaEntrada) -> int | None:
    """O custo da entrada mais recente do produto que continua valendo (None = não há).

    Ficam de fora as entradas desta nota e as de notas já estornadas.
    """
    estornadas = sessao.scalars(select(NotaEntrada.id).where(NotaEntrada.estornada_em.is_not(None)))
    sem_efeito = {f"nota:{nota.id}"} | {f"nota:{nota_id}" for nota_id in estornadas}
    entradas = sessao.execute(
        select(MovimentoEstoque.custo_unitario_centavos, MovimentoEstoque.referencia)
        .where(
            MovimentoEstoque.produto_id == produto.id,
            MovimentoEstoque.quantidade > 0,
            MovimentoEstoque.custo_unitario_centavos.is_not(None),
        )
        .order_by(MovimentoEstoque.id.desc())
    )
    for custo, referencia in entradas:
        if custo is not None and referencia not in sem_efeito:
            return custo
    return None


def estornar(sessao: Session, operador: Operador, nota: NotaEntrada, motivo: str) -> list[Produto]:
    """Desfaz a entrada da nota. Devolve os produtos cujo custo médio precisa ser conferido.

    Custo médio de cada produto, do último item da nota para o primeiro:
    - se ninguém mexeu no custo desde a entrada, ele volta exatamente ao que era antes dela;
    - se outra entrada mexeu depois, faz-se a conta inversa da média;
    - se nem a conta inversa é possível (a entrada estornada era todo o saldo), o custo fica
      como está e o produto entra na lista devolvida, para o gerente conferir.
    """
    if nota.estornada_em is not None:
        raise RegraError("Esta nota já está estornada.", status=409)
    motivo = " ".join(motivo.split())[:160]
    if not motivo:
        raise RegraError("Escreva o motivo do estorno.")
    contas = contas_da_nota(sessao, nota)
    if any(c.pago_em is not None for c in contas):
        raise RegraError(
            "Há parcela desta nota já paga. Desfaça a baixa no Financeiro antes de estornar.",
            status=409,
        )
    for conta in contas:
        financeiro.cancelar_lancamento(conta, operador)

    conferir: list[Produto] = []
    for item in reversed(nota.itens):
        produto = item.produto
        if produto is None:
            continue
        entrou = quantidade_que_entra(Decimal(item.quantidade), Decimal(item.fator_conversao))
        custo = custo_por_unidade(item.custo_total_centavos, entrou)
        if produto.custo_centavos == item.custo_depois_centavos:
            produto.custo_centavos = item.custo_antes_centavos
        else:
            antes = estoque.saldo(sessao, produto.id)
            anterior = estoque.custo_medio_sem_a_entrada(
                antes, produto.custo_centavos, entrou, custo
            )
            if anterior is not None:
                produto.custo_centavos = anterior
            elif produto not in conferir:
                conferir.append(produto)
        estoque.registrar(
            sessao,
            produto,
            -entrou,
            TipoMovimentoEstoque.ENTRADA_XML,
            operador=operador,
            motivo=f"Estorno da NF {nota.numero} de {nota.fornecedor_nome}: {motivo}",
            referencia=f"nota:{nota.id}",
            custo_unitario_centavos=custo,
        )
        sessao.flush()
        produto.ultimo_custo_centavos = _ultimo_custo_fora_da_nota(sessao, produto, nota)
    nota.estornada_em = tempo.agora()
    nota.estornada_por_id = operador.id
    nota.motivo_estorno = motivo
    sessao.commit()
    log.warning(
        "nota %s (id %s) estornada por %s: %s", nota.numero, nota.id, operador.login, motivo
    )
    return conferir

"""Modelo de dados do Moleka PDV (SQLAlchemy 2, estilo declarativo com tipos).

Convenções:
- dinheiro em centavos (Integer);
- quantidades em Numeric(12, 3) (permite kg/litro fracionado);
- datas em UTC-naive gravadas pelo backend (America/Sao_Paulo na interface);
- nada é apagado fisicamente nos cadastros: usa-se `ativo = False`.
"""

from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------- cadastros


class Produto(Base):
    __tablename__ = "produto"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True)  # código interno
    ean: Mapped[str | None] = mapped_column(String(14), index=True)
    descricao: Mapped[str] = mapped_column(String(120))
    unidade: Mapped[str] = mapped_column(String(6), default="UN")  # UN, KG, L, CX...
    ncm: Mapped[str | None] = mapped_column(String(8))
    cest: Mapped[str | None] = mapped_column(String(7))
    cst_csosn: Mapped[str | None] = mapped_column(String(4))
    origem: Mapped[str] = mapped_column(String(1), default="0")  # 0 = nacional
    custo_centavos: Mapped[int | None] = mapped_column(Integer)  # último custo (XML) ou manual
    estoque_minimo: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=Decimal("0"))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    precos: Mapped[list[PrecoProduto]] = relationship(back_populates="produto")


class TabelaPreco(Base):
    __tablename__ = "tabela_preco"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(40), unique=True)  # VAREJO, ATACADO...
    padrao: Mapped[bool] = mapped_column(Boolean, default=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class PrecoProduto(Base):
    """Uma faixa de preço: a partir de `qtd_min` unidades, o produto custa `preco_centavos`."""

    __tablename__ = "preco_produto"
    __table_args__ = (UniqueConstraint("produto_id", "tabela_id", "qtd_min"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    produto_id: Mapped[int] = mapped_column(ForeignKey("produto.id"), index=True)
    tabela_id: Mapped[int] = mapped_column(ForeignKey("tabela_preco.id"), index=True)
    qtd_min: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=Decimal("1"))
    preco_centavos: Mapped[int] = mapped_column(Integer)

    produto: Mapped[Produto] = relationship(back_populates="precos")
    tabela: Mapped[TabelaPreco] = relationship()


class Cliente(Base):
    __tablename__ = "cliente"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), index=True)
    cpf_cnpj: Mapped[str | None] = mapped_column(String(14), index=True)
    telefone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(120))
    endereco: Mapped[str | None] = mapped_column(String(200))
    tabela_id: Mapped[int | None] = mapped_column(ForeignKey("tabela_preco.id"))
    observacao: Mapped[str | None] = mapped_column(Text)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    tabela: Mapped[TabelaPreco | None] = relationship()


class Perfil(enum.StrEnum):
    OPERADOR = "operador"
    GERENTE = "gerente"


class Operador(Base):
    __tablename__ = "operador"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(80))
    login: Mapped[str] = mapped_column(String(30), unique=True)
    senha_hash: Mapped[str] = mapped_column(String(200))
    perfil: Mapped[Perfil] = mapped_column(Enum(Perfil), default=Perfil.OPERADOR)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


# ---------------------------------------------------------------- caixa e vendas


class Caixa(Base):
    """Um terminal de caixa (Caixa 01, Caixa 02...)."""

    __tablename__ = "caixa"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(30), unique=True)
    serie_nfce: Mapped[int] = mapped_column(Integer, default=1)
    proximo_numero_nfce: Mapped[int] = mapped_column(Integer, default=1)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class SessaoCaixa(Base):
    """Abertura → movimentos → fechamento de um caixa por um operador."""

    __tablename__ = "sessao_caixa"

    id: Mapped[int] = mapped_column(primary_key=True)
    caixa_id: Mapped[int] = mapped_column(ForeignKey("caixa.id"))
    operador_id: Mapped[int] = mapped_column(ForeignKey("operador.id"))
    aberto_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    fechado_em: Mapped[datetime | None] = mapped_column(DateTime)
    fundo_troco_centavos: Mapped[int] = mapped_column(Integer, default=0)
    conferido_centavos: Mapped[int | None] = mapped_column(Integer)  # contado no fechamento
    observacao: Mapped[str | None] = mapped_column(Text)

    caixa: Mapped[Caixa] = relationship()
    operador: Mapped[Operador] = relationship()


class TipoMovimentoCaixa(enum.StrEnum):
    SANGRIA = "sangria"
    SUPRIMENTO = "suprimento"


class MovimentoCaixa(Base):
    __tablename__ = "movimento_caixa"

    id: Mapped[int] = mapped_column(primary_key=True)
    sessao_id: Mapped[int] = mapped_column(ForeignKey("sessao_caixa.id"), index=True)
    tipo: Mapped[TipoMovimentoCaixa] = mapped_column(Enum(TipoMovimentoCaixa))
    valor_centavos: Mapped[int] = mapped_column(Integer)
    motivo: Mapped[str | None] = mapped_column(String(120))
    em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class StatusVenda(enum.StrEnum):
    ABERTA = "aberta"
    FINALIZADA = "finalizada"
    CANCELADA = "cancelada"


class Venda(Base):
    __tablename__ = "venda"

    id: Mapped[int] = mapped_column(primary_key=True)
    sessao_id: Mapped[int] = mapped_column(ForeignKey("sessao_caixa.id"), index=True)
    cliente_id: Mapped[int | None] = mapped_column(ForeignKey("cliente.id"))
    tabela_id: Mapped[int] = mapped_column(ForeignKey("tabela_preco.id"))
    numero: Mapped[int] = mapped_column(Integer, index=True)  # sequencial por caixa
    status: Mapped[StatusVenda] = mapped_column(Enum(StatusVenda), default=StatusVenda.ABERTA)
    cpf_na_nota: Mapped[str | None] = mapped_column(String(14))
    subtotal_centavos: Mapped[int] = mapped_column(Integer, default=0)
    desconto_centavos: Mapped[int] = mapped_column(Integer, default=0)
    total_centavos: Mapped[int] = mapped_column(Integer, default=0)
    iniciada_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finalizada_em: Mapped[datetime | None] = mapped_column(DateTime)

    itens: Mapped[list[VendaItem]] = relationship(back_populates="venda")
    pagamentos: Mapped[list[Pagamento]] = relationship(back_populates="venda")


class VendaItem(Base):
    __tablename__ = "venda_item"

    id: Mapped[int] = mapped_column(primary_key=True)
    venda_id: Mapped[int] = mapped_column(ForeignKey("venda.id"), index=True)
    produto_id: Mapped[int] = mapped_column(ForeignKey("produto.id"))
    quantidade: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    preco_unitario_centavos: Mapped[int] = mapped_column(Integer)
    faixa_qtd_min: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))  # faixa aplicada
    desconto_centavos: Mapped[int] = mapped_column(Integer, default=0)
    total_centavos: Mapped[int] = mapped_column(Integer)

    venda: Mapped[Venda] = relationship(back_populates="itens")
    produto: Mapped[Produto] = relationship()


class FormaPagamento(enum.StrEnum):
    DINHEIRO = "dinheiro"
    PIX = "pix"
    DEBITO = "debito"
    CREDITO = "credito"


class Pagamento(Base):
    __tablename__ = "pagamento"

    id: Mapped[int] = mapped_column(primary_key=True)
    venda_id: Mapped[int] = mapped_column(ForeignKey("venda.id"), index=True)
    forma: Mapped[FormaPagamento] = mapped_column(Enum(FormaPagamento))
    valor_centavos: Mapped[int] = mapped_column(Integer)
    troco_centavos: Mapped[int] = mapped_column(Integer, default=0)

    venda: Mapped[Venda] = relationship(back_populates="pagamentos")


# ---------------------------------------------------------------- fiscal


class StatusFiscal(enum.StrEnum):
    PENDENTE = "pendente"
    AUTORIZADA = "autorizada"
    REJEITADA = "rejeitada"
    CANCELADA = "cancelada"
    CONTINGENCIA = "contingencia"  # emitida offline, aguardando transmissão
    INUTILIZADA = "inutilizada"


class DocumentoFiscal(Base):
    """Uma NFC-e (modelo 65) ligada a uma venda. O XML fica em disco, fora do banco."""

    __tablename__ = "documento_fiscal"

    id: Mapped[int] = mapped_column(primary_key=True)
    venda_id: Mapped[int] = mapped_column(ForeignKey("venda.id"), index=True)
    modelo: Mapped[str] = mapped_column(String(2), default="65")
    serie: Mapped[int] = mapped_column(Integer)
    numero: Mapped[int] = mapped_column(Integer)
    chave: Mapped[str | None] = mapped_column(String(44), unique=True)
    status: Mapped[StatusFiscal] = mapped_column(Enum(StatusFiscal), default=StatusFiscal.PENDENTE)
    protocolo: Mapped[str | None] = mapped_column(String(20))
    motivo: Mapped[str | None] = mapped_column(Text)  # mensagem da SEFAZ/provedor
    provedor: Mapped[str | None] = mapped_column(String(30))
    xml_caminho: Mapped[str | None] = mapped_column(String(300))
    emitido_em: Mapped[datetime | None] = mapped_column(DateTime)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


# ---------------------------------------------------------------- estoque e compras


class TipoMovimentoEstoque(enum.StrEnum):
    VENDA = "venda"
    CANCELAMENTO = "cancelamento"
    AJUSTE = "ajuste"
    ENTRADA_XML = "entrada_xml"
    INVENTARIO = "inventario"


class MovimentoEstoque(Base):
    """Toda variação de estoque é um movimento; o saldo é a soma. Nunca se edita o saldo direto."""

    __tablename__ = "movimento_estoque"

    id: Mapped[int] = mapped_column(primary_key=True)
    produto_id: Mapped[int] = mapped_column(ForeignKey("produto.id"), index=True)
    tipo: Mapped[TipoMovimentoEstoque] = mapped_column(Enum(TipoMovimentoEstoque))
    quantidade: Mapped[Decimal] = mapped_column(Numeric(12, 3))  # negativa = saída
    custo_unitario_centavos: Mapped[int | None] = mapped_column(Integer)
    motivo: Mapped[str | None] = mapped_column(String(160))
    referencia: Mapped[str | None] = mapped_column(String(60))  # venda:123, nota:456...
    operador_id: Mapped[int | None] = mapped_column(ForeignKey("operador.id"))
    em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class NotaEntrada(Base):
    """NF-e de compra importada por XML."""

    __tablename__ = "nota_entrada"

    id: Mapped[int] = mapped_column(primary_key=True)
    chave: Mapped[str] = mapped_column(String(44), unique=True)
    fornecedor_cnpj: Mapped[str] = mapped_column(String(14), index=True)
    fornecedor_nome: Mapped[str] = mapped_column(String(120))
    numero: Mapped[int] = mapped_column(Integer)
    serie: Mapped[int] = mapped_column(Integer)
    emitida_em: Mapped[datetime] = mapped_column(DateTime)
    total_centavos: Mapped[int] = mapped_column(Integer)
    xml_caminho: Mapped[str] = mapped_column(String(300))
    importada_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    itens: Mapped[list[NotaEntradaItem]] = relationship(back_populates="nota")


class NotaEntradaItem(Base):
    __tablename__ = "nota_entrada_item"

    id: Mapped[int] = mapped_column(primary_key=True)
    nota_id: Mapped[int] = mapped_column(ForeignKey("nota_entrada.id"), index=True)
    produto_id: Mapped[int | None] = mapped_column(ForeignKey("produto.id"))  # vinculado no de-para
    codigo_fornecedor: Mapped[str] = mapped_column(String(60))
    ean: Mapped[str | None] = mapped_column(String(14))
    descricao: Mapped[str] = mapped_column(String(160))
    ncm: Mapped[str | None] = mapped_column(String(8))
    unidade: Mapped[str] = mapped_column(String(6))
    quantidade: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    valor_unitario_centavos: Mapped[int] = mapped_column(Integer)
    valor_total_centavos: Mapped[int] = mapped_column(Integer)

    nota: Mapped[NotaEntrada] = relationship(back_populates="itens")


class DeParaFornecedor(Base):
    """Memoriza: o código X do fornecedor Y é o nosso produto Z.

    As próximas importações do mesmo fornecedor ficam automáticas.
    """

    __tablename__ = "de_para_fornecedor"
    __table_args__ = (UniqueConstraint("fornecedor_cnpj", "codigo_fornecedor"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    fornecedor_cnpj: Mapped[str] = mapped_column(String(14))
    codigo_fornecedor: Mapped[str] = mapped_column(String(60))
    produto_id: Mapped[int] = mapped_column(ForeignKey("produto.id"))
    fator_conversao: Mapped[Decimal] = mapped_column(
        Numeric(12, 3), default=Decimal("1")
    )  # CX de 24 → 24 UN


# ---------------------------------------------------------------- financeiro


class GrupoDRE(enum.StrEnum):
    RECEITA_BRUTA = "receita_bruta"
    DEDUCAO = "deducao"
    CMV = "cmv"
    DESPESA_OPERACIONAL = "despesa_operacional"
    OUTRAS_RECEITAS = "outras_receitas"
    OUTRAS_DESPESAS = "outras_despesas"


class CategoriaFinanceira(Base):
    __tablename__ = "categoria_financeira"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(60), unique=True)
    grupo_dre: Mapped[GrupoDRE] = mapped_column(Enum(GrupoDRE))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class TipoLancamento(enum.StrEnum):
    RECEITA = "receita"
    DESPESA = "despesa"


class OrigemLancamento(enum.StrEnum):
    MANUAL = "manual"
    VENDA = "venda"
    COMPRA = "compra"


class Lancamento(Base):
    """Conta a pagar/receber. `pago_em` vazio = em aberto (entra no fluxo previsto)."""

    __tablename__ = "lancamento"

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[TipoLancamento] = mapped_column(Enum(TipoLancamento))
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categoria_financeira.id"))
    descricao: Mapped[str] = mapped_column(String(160))
    valor_centavos: Mapped[int] = mapped_column(Integer)
    competencia: Mapped[datetime] = mapped_column(DateTime, index=True)  # mês do DRE
    vencimento: Mapped[datetime] = mapped_column(DateTime, index=True)
    pago_em: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    forma: Mapped[FormaPagamento | None] = mapped_column(Enum(FormaPagamento))
    origem: Mapped[OrigemLancamento] = mapped_column(
        Enum(OrigemLancamento), default=OrigemLancamento.MANUAL
    )
    referencia: Mapped[str | None] = mapped_column(String(60))
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    categoria: Mapped[CategoriaFinanceira] = relationship()


# ---------------------------------------------------------------- configuração


class Configuracao(Base):
    """Chave/valor para configurações (loja, fiscal, impressoras). Segredos NÃO ficam aqui."""

    __tablename__ = "configuracao"

    chave: Mapped[str] = mapped_column(String(60), primary_key=True)
    valor: Mapped[str | None] = mapped_column(Text)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

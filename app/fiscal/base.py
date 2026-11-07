"""Contrato do provedor fiscal.

Qualquer implementação (Focus NFe, PyNFe...) cumpre esta interface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class StatusProvedor:
    nome: str
    configurado: bool
    ambiente: str  # "homologacao" | "producao" | "nenhum"
    motivo: str  # por que não está configurado / resumo do estado
    sefaz_online: bool | None = None  # None = não consultado


@dataclass(frozen=True)
class ItemFiscal:
    codigo: str
    descricao: str
    ncm: str
    cest: str | None
    cfop: str
    unidade: str
    quantidade: str  # Decimal como texto, 3 casas
    valor_unitario_centavos: int
    valor_total_centavos: int
    cst_csosn: str
    origem: str


@dataclass(frozen=True)
class PagamentoFiscal:
    forma: str  # dinheiro | pix | debito | credito
    valor_centavos: int
    troco_centavos: int = 0


@dataclass(frozen=True)
class PedidoEmissao:
    """Tudo o que o provedor precisa para montar a NFC-e, já validado pelo caixa."""

    venda_id: int
    serie: int
    numero: int
    emitida_em: datetime
    itens: tuple[ItemFiscal, ...]
    pagamentos: tuple[PagamentoFiscal, ...]
    desconto_centavos: int
    total_centavos: int
    cpf_consumidor: str | None = None
    nome_consumidor: str | None = None


@dataclass(frozen=True)
class ResultadoEmissao:
    sucesso: bool
    status: str  # autorizada | rejeitada | contingencia | erro | nao_configurado
    mensagem: str
    chave: str | None = None
    protocolo: str | None = None
    xml_caminho: str | None = None
    qr_code: str | None = None
    detalhes: dict[str, str] = field(default_factory=dict)


class ProvedorFiscal(Protocol):
    @property
    def nome(self) -> str: ...

    def status(self) -> StatusProvedor: ...

    def emitir(self, pedido: PedidoEmissao) -> ResultadoEmissao: ...

    def cancelar(self, chave: str, justificativa: str) -> ResultadoEmissao: ...

    def inutilizar(
        self, serie: int, numero_inicial: int, numero_final: int, justificativa: str
    ) -> ResultadoEmissao: ...

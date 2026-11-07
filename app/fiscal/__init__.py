"""Módulo fiscal: adaptador único para emissão de NFC-e.

O resto do sistema só conhece `ProvedorFiscal` (base.py). A implementação concreta
(API intermediária ou PyNFe) é escolhida pela configuração e pode ser trocada sem
mexer no caixa. Enquanto nenhum provedor estiver configurado, `ProvedorNulo`
responde honestamente que não está configurado — nunca finge emitir.
"""

from app.fiscal.base import ProvedorFiscal, ResultadoEmissao, StatusProvedor
from app.fiscal.nulo import ProvedorNulo

__all__ = ["ProvedorFiscal", "ProvedorNulo", "ResultadoEmissao", "StatusProvedor"]


def provedor_configurado() -> ProvedorFiscal:
    """Devolve o provedor ativo. Por enquanto só existe o nulo (decisão pendente: API ou PyNFe)."""
    return ProvedorNulo()

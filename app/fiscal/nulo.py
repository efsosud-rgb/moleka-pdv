"""Provedor fiscal nulo: usado enquanto nenhum provedor real estiver configurado.

Nunca emite, nunca inventa chave ou protocolo. Toda chamada devolve `nao_configurado`
com o motivo, para a interface mostrar "—" e o caixa impedir a finalização fiscal.
"""

from __future__ import annotations

from app.fiscal.base import PedidoEmissao, ResultadoEmissao, StatusProvedor

MOTIVO = "provedor fiscal não configurado (decisão pendente: API intermediária ou PyNFe)"


class ProvedorNulo:
    @property
    def nome(self) -> str:
        return "nenhum"

    def status(self) -> StatusProvedor:
        return StatusProvedor(nome=self.nome, configurado=False, ambiente="nenhum", motivo=MOTIVO)

    def emitir(self, pedido: PedidoEmissao) -> ResultadoEmissao:
        return ResultadoEmissao(sucesso=False, status="nao_configurado", mensagem=MOTIVO)

    def cancelar(self, chave: str, justificativa: str) -> ResultadoEmissao:
        return ResultadoEmissao(sucesso=False, status="nao_configurado", mensagem=MOTIVO)

    def inutilizar(
        self, serie: int, numero_inicial: int, numero_final: int, justificativa: str
    ) -> ResultadoEmissao:
        return ResultadoEmissao(sucesso=False, status="nao_configurado", mensagem=MOTIVO)

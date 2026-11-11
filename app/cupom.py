"""O que sai na impressora de cupom: comprovante de venda, fechamento de caixa e página de teste.

Cada cupom é uma lista de linhas já montadas na largura do papel (48, 42 ou 32 colunas), com
os valores alinhados à direita por espaços. A mesma lista serve para mostrar na tela e para
mandar à impressora (`app/escpos.py`), então o que se vê é o que sai no papel.

O comprovante de venda NÃO é documento fiscal, e diz isso com todas as letras: a NFC-e é outra
coisa (Frente 5). Todos os números vêm da venda gravada no banco.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app import caixa as regras_do_caixa
from app import dinheiro, documentos, tempo
from app.configuracoes import ACENTOS, Impressao, Loja
from app.estoque import texto_da_quantidade
from app.models import (
    FormaPagamento,
    SessaoCaixa,
    StatusVenda,
    TipoMovimentoCaixa,
    Venda,
)


@dataclass(frozen=True)
class Linha:
    texto: str = ""
    negrito: bool = False
    grande: bool = False  # letra com o dobro da altura; cabem as mesmas colunas


@dataclass(frozen=True)
class Cupom:
    titulo: str  # nome do trabalho na fila de impressão do Windows
    colunas: int
    linhas: tuple[Linha, ...]
    abre_gaveta: bool = False

    def texto(self) -> str:
        """O cupom como texto puro, uma linha por linha do papel."""
        return "\n".join(linha.texto for linha in self.linhas)


# ---------------------------------------------------------------- montagem das linhas


def _valor(centavos: int) -> str:
    return dinheiro.formatar(centavos, simbolo=False)


def _dia_e_hora(momento: datetime | None) -> str:
    return tempo.na_loja(momento).strftime("%d/%m/%Y %H:%M") if momento else "—"


class _Montagem:
    """Vai juntando as linhas de um cupom, sempre dentro da largura do papel."""

    def __init__(self, colunas: int) -> None:
        self.colunas = colunas
        self.linhas: list[Linha] = []

    def texto(self, texto: str = "", *, negrito: bool = False, grande: bool = False) -> None:
        for parte in textwrap.wrap(texto, self.colunas) or [""]:
            self.linhas.append(Linha(parte, negrito, grande))

    def centro(self, texto: str, *, negrito: bool = False, grande: bool = False) -> None:
        for parte in textwrap.wrap(texto, self.colunas) or [""]:
            self.linhas.append(Linha(parte.center(self.colunas).rstrip(), negrito, grande))

    def par(
        self, esquerda: str, direita: str, *, negrito: bool = False, grande: bool = False
    ) -> None:
        """Texto à esquerda e valor à direita na mesma linha; o texto é cortado se não couber."""
        direita = direita[: self.colunas]
        cabe = max(self.colunas - len(direita) - 1, 0)
        esquerda = esquerda[:cabe]
        meio = " " * (self.colunas - len(esquerda) - len(direita))
        self.linhas.append(Linha(esquerda + meio + direita, negrito, grande))

    def separador(self) -> None:
        self.linhas.append(Linha("-" * self.colunas))

    def cabecalho_da_loja(self, loja: Loja) -> None:
        """Só o que estiver preenchido em Configurações; nada é inventado."""
        if loja.nome_fantasia:
            self.centro(loja.nome_fantasia, negrito=True, grande=True)
        if loja.razao_social and loja.razao_social != loja.nome_fantasia:
            self.centro(loja.razao_social)
        registro = []
        if loja.cnpj:
            registro.append("CNPJ " + documentos.formatar(loja.cnpj))
        if loja.ie:
            registro.append("IE " + loja.ie)
        if registro:
            self.centro("  ".join(registro))
        rua = ", ".join(parte for parte in (loja.logradouro, loja.numero) if parte)
        primeira = " - ".join(parte for parte in (rua, loja.bairro) if parte)
        if primeira:
            self.centro(primeira)
        cidade = " - ".join(parte for parte in (loja.cidade, loja.uf) if parte)
        cep = f"CEP {loja.cep[:5]}-{loja.cep[5:]}" if loja.cep else ""
        segunda = "  ".join(parte for parte in (cidade, cep) if parte)
        if segunda:
            self.centro(segunda)
        if loja.telefone:
            self.centro("Tel. " + loja.telefone)
        if self.linhas:
            self.separador()

    def pronto(self, titulo: str, *, abre_gaveta: bool = False) -> Cupom:
        return Cupom(titulo, self.colunas, tuple(self.linhas), abre_gaveta)


# ---------------------------------------------------------------- comprovante de venda


def comprovante_de_venda(
    loja: Loja, venda: Venda, colunas: int, *, versao: str, abre_gaveta: bool = False
) -> Cupom:
    """O comprovante de uma venda finalizada (ou cancelada, que sai marcada como cancelada)."""
    m = _Montagem(colunas)
    m.cabecalho_da_loja(loja)
    m.centro("COMPROVANTE DE VENDA", negrito=True)
    m.centro("NÃO É DOCUMENTO FISCAL")
    if venda.status == StatusVenda.CANCELADA:
        m.centro("*** VENDA CANCELADA ***", negrito=True)
        if venda.motivo_cancelamento:
            m.texto("Motivo: " + venda.motivo_cancelamento)
    m.separador()
    m.par(f"Venda nº {venda.numero}", _dia_e_hora(venda.finalizada_em))
    if venda.operador is not None:
        m.texto("Operador: " + venda.operador.nome)
    if venda.cliente is not None:
        m.texto("Cliente: " + venda.cliente.nome)
    m.separador()

    for ordem, item in enumerate(venda.itens, start=1):
        descricao = item.descricao or item.produto.descricao
        unidade = item.unidade or item.produto.unidade
        partes = textwrap.wrap(descricao, colunas - 4) or [""]
        m.linhas.append(Linha(f"{ordem:03d} {partes[0]}"))
        for resto in partes[1:]:
            m.linhas.append(Linha("    " + resto))
        conta = (
            f"    {texto_da_quantidade(item.quantidade)} {unidade} x "
            f"{_valor(item.preco_unitario_centavos)}"
        )
        m.par(conta, _valor(item.total_centavos))
    m.separador()

    ajustes = [p for p in venda.pagamentos if p.ajuste_centavos != 0]
    if venda.desconto_centavos or ajustes:
        m.par("Subtotal", _valor(venda.subtotal_centavos))
    if venda.desconto_centavos:
        m.par("Desconto", "-" + _valor(venda.desconto_centavos))
    for pagamento in ajustes:
        forma = regras_do_caixa.ROTULOS[pagamento.forma]
        if pagamento.ajuste_centavos < 0:
            m.par(f"Desconto no {forma}", "-" + _valor(-pagamento.ajuste_centavos))
        else:
            m.par(f"Acréscimo no {forma}", "+" + _valor(pagamento.ajuste_centavos))
    m.par("TOTAL", dinheiro.formatar(venda.total_centavos), negrito=True, grande=True)
    m.separador()

    troco = 0
    for pagamento in venda.pagamentos:
        forma = regras_do_caixa.ROTULOS[pagamento.forma]
        # No dinheiro, mostra o que o cliente entregou; o troco vem na linha de baixo.
        m.par(forma, _valor(pagamento.valor_centavos + pagamento.troco_centavos))
        troco += pagamento.troco_centavos
    if troco:
        m.par("Troco", _valor(troco))
    if venda.pagamentos:
        m.separador()

    if loja.rodape:
        m.centro(loja.rodape)
    m.centro(f"Moleka PDV {versao}")
    em_dinheiro = any(p.forma == FormaPagamento.DINHEIRO for p in venda.pagamentos)
    return m.pronto(f"Moleka - venda {venda.numero}", abre_gaveta=abre_gaveta and em_dinheiro)


# ---------------------------------------------------------------- fechamento de caixa


def fechamento_de_caixa(
    loja: Loja, sessao: Session, sessao_caixa: SessaoCaixa, colunas: int, *, versao: str
) -> Cupom:
    """O resumo de uma sessão de caixa: fechada (com a conferência) ou ainda aberta (parcial)."""
    numeros = regras_do_caixa.totais(sessao, sessao_caixa)
    fechada = sessao_caixa.fechado_em is not None
    m = _Montagem(colunas)
    m.cabecalho_da_loja(loja)
    m.centro("FECHAMENTO DE CAIXA" if fechada else "RESUMO DO CAIXA (AINDA ABERTO)", negrito=True)
    m.separador()
    m.texto(sessao_caixa.caixa.nome)
    m.par("Aberto em", _dia_e_hora(sessao_caixa.aberto_em))
    m.texto("  por " + sessao_caixa.operador.nome)
    if fechada:
        m.par("Fechado em", _dia_e_hora(sessao_caixa.fechado_em))
        if sessao_caixa.fechado_por is not None:
            m.texto("  por " + sessao_caixa.fechado_por.nome)
    else:
        m.par("Impresso em", _dia_e_hora(tempo.agora()))
    m.separador()

    m.par("Vendas finalizadas", str(numeros.vendas_quantidade))
    m.par("Total vendido", _valor(numeros.vendas_total), negrito=True)
    m.separador()
    m.texto("RECEBIDO POR FORMA", negrito=True)
    for forma in FormaPagamento:
        m.par(regras_do_caixa.ROTULOS[forma], _valor(numeros.recebido.get(forma, 0)))
    m.separador()

    m.texto("DINHEIRO NA GAVETA", negrito=True)
    m.par("Fundo de troco", _valor(numeros.fundo))
    m.par("(+) Vendas em dinheiro", _valor(numeros.recebido.get(FormaPagamento.DINHEIRO, 0)))
    m.par("(+) Suprimentos", _valor(numeros.suprimentos))
    m.par("(-) Sangrias", _valor(numeros.sangrias))
    m.par("(=) Esperado", _valor(numeros.dinheiro_esperado), negrito=True)
    m.separador()

    if fechada:
        m.texto("CONFERÊNCIA", negrito=True)
        conferido = {c.forma: c for c in sessao_caixa.conferencias}
        for forma in FormaPagamento:
            linha = conferido.get(forma)
            if linha is None:
                continue
            m.texto(regras_do_caixa.ROTULOS[forma])
            m.par("  Esperado", _valor(linha.esperado_centavos))
            m.par("  Contado", _valor(linha.contado_centavos))
            diferenca = linha.contado_centavos - linha.esperado_centavos
            m.par("  Diferença", _valor(diferenca), negrito=diferenca != 0)
        m.separador()

    if sessao_caixa.movimentos:
        m.texto("SANGRIAS E SUPRIMENTOS", negrito=True)
        for movimento in sessao_caixa.movimentos:
            nome = "Sangria" if movimento.tipo == TipoMovimentoCaixa.SANGRIA else "Suprimento"
            hora = tempo.na_loja(movimento.em).strftime("%H:%M")
            m.par(f"{hora} {nome}", _valor(movimento.valor_centavos))
            if movimento.motivo:
                m.texto("  " + movimento.motivo)
        m.separador()

    if sessao_caixa.observacao:
        m.texto("Observação: " + sessao_caixa.observacao)
        m.separador()
    m.texto("")
    m.texto("Conferido por: " + "_" * max(colunas - 15, 4))
    m.centro(f"Moleka PDV {versao}")
    return m.pronto(f"Moleka - caixa {sessao_caixa.id}")


# ---------------------------------------------------------------- página de teste


def pagina_de_teste(loja: Loja, impressao: Impressao, *, versao: str) -> Cupom:
    """Mostra se a largura, os acentos, o negrito e o corte estão certos nesta impressora."""
    colunas = impressao.colunas
    m = _Montagem(colunas)
    m.cabecalho_da_loja(loja)
    m.centro("TESTE DE IMPRESSÃO", negrito=True, grande=True)
    m.separador()
    m.texto("Impressora: " + impressao.impressora)
    m.texto(f"Colunas: {colunas}")
    m.texto("Acentos: " + ACENTOS[impressao.acentos])
    m.par("Impresso em", _dia_e_hora(tempo.agora()))
    m.separador()
    m.texto("A linha de números abaixo tem de caber numa linha só:")
    m.linhas.append(Linha("".join(str(n % 10) for n in range(1, colunas + 1))))
    m.texto("Letras com acento:")
    m.texto("á é í ó ú â ê ô ã õ à ç Á É Ç Ã Õ")
    m.texto("Negrito:")
    m.texto("Picolé de limão", negrito=True)
    m.texto("Letra grande, com a palavra da direita encostada na borda:")
    m.par("ESQUERDA", "DIREITA", negrito=True, grande=True)
    m.separador()
    m.texto("Se os números quebraram em duas linhas, diminua as colunas.")
    m.texto("Se os acentos saíram trocados, mude a opção Acentos.")
    m.centro(f"Moleka PDV {versao}")
    return m.pronto("Moleka - teste de impressão")

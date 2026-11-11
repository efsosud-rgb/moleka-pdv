"""Leitor do XML da NF-e (modelo 55) de uma compra. Só lê: não grava nada nem fala com a SEFAZ.

O que sai daqui é o que está escrito na nota, sem estimativa:
- quem emitiu, número, série, data, chave (com o dígito verificador conferido) e total;
- cada item, com o que ele custou de fato:

      custo do item = valor dos produtos - desconto + frete + seguro + outras despesas
                      + IPI + ICMS-ST (com o FCP-ST)

  É a conta de quem não recupera imposto na compra (empresa do Simples Nacional). A soma dos
  itens é comparada com o total da nota, e a diferença vira um aviso;
- as parcelas (duplicatas), quando a nota traz.

O texto é conferido antes de ser lido: arquivo grande demais ou com DOCTYPE/ENTITY (que uma
NF-e nunca tem, e que servem para ataques) é recusado.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app import dinheiro, documentos, tempo
from app.operadores import RegraError

TAMANHO_MAXIMO = 2_000_000  # caracteres; uma NF-e de verdade tem no máximo 500 kB
_DECLARACAO = re.compile(r"^\s*<\?xml[^>]*\?>", re.IGNORECASE)
_PROIBIDO = re.compile(r"<!\s*(DOCTYPE|ENTITY)", re.IGNORECASE)
# cUF e AAMM (6 dígitos), as 12 primeiras posições do CNPJ (letras ou números) e o resto.
_FORMATO_DA_CHAVE = re.compile(r"[0-9]{6}[0-9A-Z]{12}[0-9]{26}")
_NAO_E_DA_CHAVE = re.compile(r"[^0-9A-Za-z]")


@dataclass(frozen=True)
class ItemNota:
    numero: int  # nItem
    codigo: str  # código do produto no fornecedor (cProd)
    ean: str | None
    ean_tributavel: str | None
    descricao: str
    ncm: str | None
    cfop: str | None
    unidade: str  # uCom
    quantidade: Decimal  # qCom
    valor_unitario_centavos: int  # vUnCom arredondado ao centavo (só para mostrar)
    valor_total_centavos: int  # vProd
    unidade_tributavel: str | None
    quantidade_tributavel: Decimal | None
    desconto_centavos: int
    frete_centavos: int
    seguro_centavos: int
    outras_centavos: int
    ipi_centavos: int
    st_centavos: int  # ICMS-ST + FCP-ST
    compoe_o_total: bool  # indTot = 1

    @property
    def custo_total_centavos(self) -> int:
        """O que este item custou de fato (ver a conta no começo do arquivo)."""
        if not self.compoe_o_total:
            return 0
        return (
            self.valor_total_centavos
            - self.desconto_centavos
            + self.frete_centavos
            + self.seguro_centavos
            + self.outras_centavos
            + self.ipi_centavos
            + self.st_centavos
        )

    @property
    def fator_da_nota(self) -> Decimal | None:
        """Quantas unidades tributáveis há em cada unidade comercial (ex.: CX com 24 UN → 24).

        Só quando a própria nota informa as duas unidades e a conta dá um número limpo.
        """
        tributavel = self.quantidade_tributavel
        if not tributavel or self.quantidade <= 0 or not self.unidade_tributavel:
            return None
        if self.unidade_tributavel.upper() == self.unidade.upper():
            return None
        fator = (tributavel / self.quantidade).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        if fator <= 0 or fator * self.quantidade != tributavel:
            return None
        return fator


@dataclass(frozen=True)
class Parcela:
    numero: str
    vencimento: date
    valor_centavos: int


@dataclass(frozen=True)
class Nota:
    chave: str
    numero: int
    serie: int
    emitida_em: datetime  # UTC, sem fuso, como o banco guarda
    natureza: str | None
    emitente_documento: str  # CNPJ (ou CPF de produtor rural), só os caracteres
    emitente_nome: str
    destinatario_documento: str | None
    destinatario_nome: str | None
    total_centavos: int  # vNF
    autorizada: bool | None  # None = o arquivo veio sem o protocolo da SEFAZ
    itens: tuple[ItemNota, ...]
    parcelas: tuple[Parcela, ...]
    avisos: tuple[str, ...]

    @property
    def custo_dos_itens_centavos(self) -> int:
        return sum(item.custo_total_centavos for item in self.itens)


# ---------------------------------------------------------------- utilitários


def chave_valida(chave: str) -> bool:
    """44 posições, com a última (dígito verificador, módulo 11) batendo com as outras 43.

    Desde julho de 2026 o CNPJ pode ter letras, e a chave também (nas 12 primeiras posições do
    CNPJ). Na conta, cada caractere vale o seu código ASCII menos 48 — os algarismos continuam
    valendo o próprio número, e "A" vale 17 (Nota Técnica Conjunta 2025.001).
    """
    if not _FORMATO_DA_CHAVE.fullmatch(chave):
        return False
    soma = sum((ord(c) - 48) * (2 + i % 8) for i, c in enumerate(reversed(chave[:43])))
    resto = soma % 11
    return int(chave[43]) == (0 if resto in (0, 1) else 11 - resto)


def _chave_do_id(texto: str | None) -> str:
    """Do atributo Id ("NFe" + a chave) fica só a chave, em maiúsculas."""
    limpo = _NAO_E_DA_CHAVE.sub("", texto or "").upper()
    return limpo[3:] if limpo.startswith("NFE") else limpo


def _texto(no: ET.Element | None, caminho: str) -> str | None:
    if no is None:
        return None
    achado = no.find(caminho)
    if achado is None or achado.text is None:
        return None
    return " ".join(achado.text.split()) or None


def _centavos(no: ET.Element | None, caminho: str) -> int:
    texto = _texto(no, caminho)
    if texto is None:
        return 0
    try:
        return dinheiro.de_reais(texto)
    except ValueError as erro:
        raise RegraError(f"Valor inválido no XML ({caminho}: {texto}).") from erro


def _decimal(no: ET.Element | None, caminho: str) -> Decimal | None:
    texto = _texto(no, caminho)
    if texto is None:
        return None
    try:
        return Decimal(texto)
    except InvalidOperation as erro:
        raise RegraError(f"Quantidade inválida no XML ({caminho}: {texto}).") from erro


def _inteiro(no: ET.Element | None, caminho: str) -> int | None:
    texto = _texto(no, caminho)
    return int(texto) if texto and texto.isdigit() else None


def _ean(texto: str | None) -> str | None:
    """Código de barras de verdade (8, 12, 13 ou 14 dígitos). "SEM GTIN" e lixo viram None."""
    if not texto or not texto.isdigit() or len(texto) not in (8, 12, 13, 14):
        return None
    return texto


def _somar(no: ET.Element | None, nomes: tuple[str, ...]) -> int:
    """Soma, em qualquer nível abaixo de `no`, os valores das marcas com esses nomes."""
    if no is None:
        return 0
    total = 0
    for elemento in no.iter():
        if elemento.tag in nomes and elemento.text and elemento.text.strip():
            try:
                total += dinheiro.de_reais(elemento.text.strip())
            except ValueError as erro:
                raise RegraError(f"Valor inválido no XML ({elemento.tag}).") from erro
    return total


def _data_de_emissao(ide: ET.Element | None) -> datetime:
    texto = _texto(ide, "dhEmi") or _texto(ide, "dEmi")
    if not texto:
        raise RegraError("O XML não traz a data de emissão da nota.")
    try:
        momento = datetime.fromisoformat(texto)
    except ValueError as erro:
        raise RegraError(f"Data de emissão inválida no XML ({texto}).") from erro
    if momento.tzinfo is None:  # nota antiga, só com o dia: vale o horário da loja
        momento = momento.replace(tzinfo=tempo.FUSO)
    return momento.astimezone(UTC).replace(tzinfo=None)


# ---------------------------------------------------------------- leitura


def _raiz(texto: str) -> ET.Element:
    if not texto or not texto.strip():
        raise RegraError("O arquivo está vazio.")
    if len(texto) > TAMANHO_MAXIMO:
        raise RegraError("O arquivo é grande demais para ser uma NF-e.")
    if _PROIBIDO.search(texto):
        raise RegraError("Este arquivo não é o XML de uma NF-e (traz comandos que a nota não usa).")
    # Sem a declaração do começo, o leitor entende o texto como UTF-8, que é como ele chega aqui.
    limpo = _DECLARACAO.sub("", texto.lstrip("﻿"), count=1)
    try:
        raiz = ET.fromstring(limpo.encode("utf-8"))
    except ET.ParseError as erro:
        raise RegraError(
            "Não consegui ler o arquivo: ele não é um XML válido. Peça ao fornecedor o XML da nota."
        ) from erro
    for elemento in raiz.iter():  # tira o "sobrenome" (namespace) das marcas
        if "}" in elemento.tag:
            elemento.tag = elemento.tag.split("}", 1)[1]
    return raiz


def _ler_item(det: ET.Element) -> ItemNota:
    prod = det.find("prod")
    numero = int(det.get("nItem") or 0)
    codigo = _texto(prod, "cProd")
    descricao = _texto(prod, "xProd")
    quantidade = _decimal(prod, "qCom")
    if prod is None or not codigo or not descricao or quantidade is None or numero <= 0:
        raise RegraError(f"O item {numero or '?'} da nota está incompleto no XML.")
    if quantidade <= 0:
        raise RegraError(f"O item {numero} da nota está com quantidade zero ou negativa.")
    imposto = det.find("imposto")
    valor_unitario = _decimal(prod, "vUnCom") or Decimal(0)
    return ItemNota(
        numero=numero,
        codigo=codigo[:60],
        ean=_ean(_texto(prod, "cEAN")),
        ean_tributavel=_ean(_texto(prod, "cEANTrib")),
        descricao=descricao[:160],
        ncm=_texto(prod, "NCM"),
        cfop=_texto(prod, "CFOP"),
        unidade=(_texto(prod, "uCom") or "UN")[:6].upper(),
        quantidade=quantidade,
        valor_unitario_centavos=dinheiro.de_reais(valor_unitario),
        valor_total_centavos=_centavos(prod, "vProd"),
        unidade_tributavel=(_texto(prod, "uTrib") or "")[:6].upper() or None,
        quantidade_tributavel=_decimal(prod, "qTrib"),
        desconto_centavos=_centavos(prod, "vDesc"),
        frete_centavos=_centavos(prod, "vFrete"),
        seguro_centavos=_centavos(prod, "vSeg"),
        outras_centavos=_centavos(prod, "vOutro"),
        ipi_centavos=_somar(imposto.find("IPI") if imposto is not None else None, ("vIPI",)),
        st_centavos=_somar(
            imposto.find("ICMS") if imposto is not None else None, ("vICMSST", "vFCPST")
        ),
        compoe_o_total=(_texto(prod, "indTot") or "1") != "0",
    )


def ler(texto: str) -> Nota:
    """Lê o XML de uma NF-e de compra. Recusa, com o motivo, o que não for isso."""
    raiz = _raiz(texto)
    if raiz.tag in ("procEventoNFe", "evento", "envEvento", "retEnvEvento"):
        raise RegraError(
            "Este arquivo é um evento da nota (cancelamento ou carta de correção), não a nota."
        )
    inf = raiz if raiz.tag == "infNFe" else raiz.find(".//infNFe")
    if inf is None:
        raise RegraError("Este arquivo não é o XML de uma NF-e (não achei os dados da nota).")

    ide = inf.find("ide")
    modelo = _texto(ide, "mod")
    if modelo == "65":
        raise RegraError("Este XML é de um cupom (NFC-e), não de uma nota de compra (NF-e).")
    if modelo != "55":
        raise RegraError("Este XML não é de uma NF-e de compra (modelo 55).")

    chave = _chave_do_id(inf.get("Id")) or _chave_do_id(_texto(raiz, ".//protNFe/infProt/chNFe"))
    if not chave_valida(chave):
        raise RegraError(
            "A chave de acesso da nota não confere (44 posições, com dígito verificador). "
            "O arquivo pode estar corrompido."
        )
    numero = _inteiro(ide, "nNF")
    serie = _inteiro(ide, "serie")
    if numero is None or serie is None:
        raise RegraError("O XML não traz o número ou a série da nota.")

    emit = inf.find("emit")
    emitente_documento = documentos.limpar(_texto(emit, "CNPJ") or _texto(emit, "CPF") or "")
    emitente_nome = _texto(emit, "xNome") or _texto(emit, "xFant")
    if not emitente_documento or not emitente_nome:
        raise RegraError("O XML não traz o CNPJ ou o nome de quem emitiu a nota.")
    dest = inf.find("dest")

    itens = tuple(_ler_item(det) for det in inf.findall("det"))
    if not itens:
        raise RegraError("A nota não tem itens.")
    if len({item.numero for item in itens}) != len(itens):
        raise RegraError("O XML tem itens com o mesmo número.")

    parcelas: list[Parcela] = []
    for dup in inf.findall("cobr/dup"):
        vencimento = _texto(dup, "dVenc")
        valor = _centavos(dup, "vDup")
        if not vencimento or valor <= 0:
            continue
        try:
            dia = date.fromisoformat(vencimento)
        except ValueError as erro:
            raise RegraError(f"Vencimento inválido numa parcela da nota ({vencimento}).") from erro
        parcelas.append(Parcela(_texto(dup, "nDup") or str(len(parcelas) + 1), dia, valor))

    total = _centavos(inf, "total/ICMSTot/vNF")
    situacao = _texto(raiz, ".//protNFe/infProt/cStat")
    autorizada = None if situacao is None else situacao in ("100", "150")

    avisos: list[str] = []
    if autorizada is None:
        avisos.append(
            "O arquivo veio sem o protocolo de autorização da SEFAZ: não dá para saber por ele "
            "se a nota foi autorizada."
        )
    elif not autorizada:
        avisos.append(
            f"A SEFAZ não autorizou esta nota (situação {situacao}). Confira antes de dar entrada."
        )
    if (_texto(ide, "tpNF") or "1") != "1":
        avisos.append("Esta é uma nota de entrada emitida pelo fornecedor (não é uma venda dele).")
    nota = Nota(
        chave=chave,
        numero=numero,
        serie=serie,
        emitida_em=_data_de_emissao(ide),
        natureza=_texto(ide, "natOp"),
        emitente_documento=emitente_documento,
        emitente_nome=emitente_nome[:120],
        destinatario_documento=documentos.limpar(_texto(dest, "CNPJ") or _texto(dest, "CPF") or "")
        or None,
        destinatario_nome=_texto(dest, "xNome"),
        total_centavos=total,
        autorizada=autorizada,
        itens=itens,
        parcelas=tuple(parcelas),
        avisos=(),
    )
    diferenca = total - nota.custo_dos_itens_centavos
    if diferenca != 0:
        avisos.append(
            f"A soma do custo dos itens ({dinheiro.formatar(nota.custo_dos_itens_centavos)}) é "
            f"diferente do total da nota ({dinheiro.formatar(total)}). A diferença de "
            f"{dinheiro.formatar(abs(diferenca))} não entra no custo dos produtos."
        )
    for item in itens:
        if not item.compoe_o_total:
            avisos.append(
                f"O item {item.numero} não entra no total da nota (bonificação ou brinde): "
                "ele dá entrada no estoque com custo zero."
            )
    if parcelas and sum(p.valor_centavos for p in parcelas) != total:
        avisos.append(
            "A soma das parcelas é diferente do total da nota. As contas a pagar seguem as "
            "parcelas."
        )
    return replace(nota, avisos=tuple(avisos))

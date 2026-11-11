"""Gerador de XML de NF-e FICTÍCIA, só para os testes.

Nenhuma destas notas, empresas ou produtos existe. O formato segue o da NF-e 4.00 (modelo 55)
no que o leitor do sistema usa: identificação, emitente, itens com impostos, total, parcelas e
o protocolo da SEFAZ.
"""

from datetime import date, timedelta
from decimal import Decimal

from app import tempo

FORNECEDOR = "11222333000181"  # CNPJ fictício, com os dígitos verificadores certos
NOME_DO_FORNECEDOR = "FORNECEDOR FICTICIO DE TESTE LTDA"
LOJA = "11444777000161"  # idem


def dv_da_chave(base: str) -> str:
    """Dígito verificador da chave pela regra do manual da NF-e, escrita de outro jeito que o
    do sistema: pesos 2 a 9 da direita para a esquerda, módulo 11; 10 e 11 viram 0."""
    pesos = "23456789" * 6
    soma = sum((ord(c) - 48) * int(peso) for c, peso in zip(reversed(base), pesos, strict=False))
    dv = 11 - soma % 11
    return "0" if dv >= 10 else str(dv)


def chave(numero: int, emitida: date, emitente: str = FORNECEDOR, modelo: str = "55") -> str:
    base = f"35{emitida:%y%m}{emitente}{modelo}001{numero:09d}1{numero + 11:08d}"
    assert len(base) == 43, base
    return base + dv_da_chave(base)


def item(
    codigo,
    descricao,
    unidade,
    quantidade,
    valor,
    *,
    ean="SEM GTIN",
    ean_trib="SEM GTIN",
    unidade_trib=None,
    quantidade_trib=None,
    desconto="0",
    frete="0",
    seguro="0",
    outras="0",
    ipi="0",
    st="0",
    fcp_st="0",
    entra_no_total=True,
    ncm="21050010",
):
    """Um item da nota. Valores em reais, como texto ("96.00")."""
    return {
        "codigo": codigo,
        "descricao": descricao,
        "unidade": unidade,
        "quantidade": Decimal(str(quantidade)),
        "valor": Decimal(valor),
        "ean": ean,
        "ean_trib": ean_trib,
        "unidade_trib": unidade_trib or unidade,
        "quantidade_trib": Decimal(str(quantidade_trib if quantidade_trib else quantidade)),
        "desconto": Decimal(desconto),
        "frete": Decimal(frete),
        "seguro": Decimal(seguro),
        "outras": Decimal(outras),
        "ipi": Decimal(ipi),
        "st": Decimal(st),
        "fcp_st": Decimal(fcp_st),
        "entra_no_total": entra_no_total,
        "ncm": ncm,
    }


def custo(i) -> Decimal:
    if not i["entra_no_total"]:
        return Decimal(0)
    return (
        i["valor"]
        - i["desconto"]
        + i["frete"]
        + i["seguro"]
        + i["outras"]
        + i["ipi"]
        + i["st"]
        + i["fcp_st"]
    )


def _marca(nome: str, valor: Decimal) -> str:
    return f"<{nome}>{valor:.2f}</{nome}>" if valor else ""


def _det(numero: int, i) -> str:
    unitario = i["valor"] / i["quantidade"]
    unitario_trib = i["valor"] / i["quantidade_trib"]
    # vBC, vICMS e vBCST estão aqui de propósito: o leitor NÃO pode somá-los ao custo.
    return f"""
      <det nItem="{numero}">
        <prod>
          <cProd>{i["codigo"]}</cProd><cEAN>{i["ean"]}</cEAN><xProd>{i["descricao"]}</xProd>
          <NCM>{i["ncm"]}</NCM><CFOP>5102</CFOP>
          <uCom>{i["unidade"]}</uCom><qCom>{i["quantidade"]:.4f}</qCom>
          <vUnCom>{unitario:.10f}</vUnCom><vProd>{i["valor"]:.2f}</vProd>
          <cEANTrib>{i["ean_trib"]}</cEANTrib><uTrib>{i["unidade_trib"]}</uTrib>
          <qTrib>{i["quantidade_trib"]:.4f}</qTrib><vUnTrib>{unitario_trib:.10f}</vUnTrib>
          {_marca("vFrete", i["frete"])}{_marca("vSeg", i["seguro"])}
          {_marca("vDesc", i["desconto"])}{_marca("vOutro", i["outras"])}
          <indTot>{1 if i["entra_no_total"] else 0}</indTot>
        </prod>
        <imposto>
          <ICMS><ICMS10><orig>0</orig><CST>10</CST><vBC>{i["valor"]:.2f}</vBC>
            <vICMS>{i["valor"] * Decimal("0.12"):.2f}</vICMS><vBCST>{i["valor"]:.2f}</vBCST>
            {_marca("vICMSST", i["st"])}{_marca("vFCPST", i["fcp_st"])}</ICMS10></ICMS>
          <IPI><cEnq>999</cEnq><IPITrib><CST>50</CST>{_marca("vIPI", i["ipi"])}</IPITrib></IPI>
        </imposto>
      </det>"""


def nota_xml(
    numero=123,
    itens=None,
    *,
    parcelas="duas",
    emitida=None,
    emitente=FORNECEDOR,
    nome=NOME_DO_FORNECEDOR,
    modelo="55",
    situacao="100",
    total=None,
    chave_de_acesso=None,
):
    """O texto do XML. `parcelas`: "duas" (metade em 30 e metade em 60 dias), uma lista de
    (número, vencimento, "valor") ou None. `situacao`: o cStat do protocolo, ou None para um
    arquivo sem protocolo."""
    emitida = emitida or tempo.hoje() - timedelta(days=5)
    itens = itens if itens is not None else itens_da_nota_123()
    total = Decimal(total) if total is not None else sum((custo(i) for i in itens), Decimal(0))
    numero_da_chave = chave_de_acesso or chave(numero, emitida, emitente, modelo)
    if parcelas == "duas":
        metade = (total / 2).quantize(Decimal("0.01"))
        parcelas = [
            ("001", emitida + timedelta(days=30), metade),
            ("002", emitida + timedelta(days=60), total - metade),
        ]
    cobranca = ""
    if parcelas:
        duplicatas = "".join(
            f"<dup><nDup>{n}</nDup><dVenc>{venc.isoformat()}</dVenc>"
            f"<vDup>{Decimal(valor):.2f}</vDup></dup>"
            for n, venc, valor in parcelas
        )
        cobranca = f"<cobr><fat><nFat>{numero}</nFat></fat>{duplicatas}</cobr>"
    nfe = f"""<NFe xmlns="http://www.portalfiscal.inf.br/nfe">
    <infNFe Id="NFe{numero_da_chave}" versao="4.00">
      <ide>
        <cUF>35</cUF><natOp>VENDA DE MERCADORIA (FICTICIA)</natOp><mod>{modelo}</mod>
        <serie>1</serie><nNF>{numero}</nNF><dhEmi>{emitida.isoformat()}T10:15:00-03:00</dhEmi>
        <tpNF>1</tpNF>
      </ide>
      <emit><CNPJ>{emitente}</CNPJ><xNome>{nome}</xNome></emit>
      <dest><CNPJ>{LOJA}</CNPJ><xNome>LOJA FICTICIA DE TESTE</xNome></dest>
      {"".join(_det(n, i) for n, i in enumerate(itens, start=1))}
      <total><ICMSTot><vProd>{sum(i["valor"] for i in itens):.2f}</vProd>
        <vNF>{total:.2f}</vNF></ICMSTot></total>
      {cobranca}
    </infNFe>
  </NFe>"""
    cabecalho = '<?xml version="1.0" encoding="UTF-8"?>\n'
    if situacao is None:
        return cabecalho + nfe
    return f"""{cabecalho}<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
  {nfe}
  <protNFe versao="4.00"><infProt><chNFe>{numero_da_chave}</chNFe>
    <cStat>{situacao}</cStat><xMotivo>Situacao ficticia de teste</xMotivo></infProt></protNFe>
</nfeProc>"""


def itens_da_nota_123():
    """A nota de teste padrão. Contas feitas à mão (o que cada item custou de fato):

    1. 2 caixas de picolé a 48,00 = 96,00 + frete 4,00 + ICMS-ST 9,60       = 109,60
       (a nota diz que são 48 unidades: 24 por caixa, com o código de barras da unidade)
    2. 3 baldes de sorvete a 150,00 = 450,00 - desconto 22,50 + IPI 13,50   = 441,00
       (a nota diz que são 30 kg: 10 por balde)
    3. 5 pacotes de copo a 6,00                                             =  30,00
                                                         total da nota      = 580,60
    """
    return [
        item(
            "PIC-24",
            "PICOLE FICTICIO DE TESTE CX 24",
            "CX",
            2,
            "96.00",
            ean_trib="7890000000017",
            unidade_trib="UN",
            quantidade_trib=48,
            frete="4.00",
            st="9.60",
        ),
        item(
            "SORV-10",
            "SORVETE FICTICIO DE TESTE BALDE 10 KG",
            "BD",
            3,
            "450.00",
            unidade_trib="KG",
            quantidade_trib=30,
            desconto="22.50",
            ipi="13.50",
        ),
        item(
            "COPO-200",
            "COPO FICTICIO DE TESTE 200 ML C/100",
            "PCT",
            5,
            "30.00",
            ean="7890000000994",
        ),
    ]

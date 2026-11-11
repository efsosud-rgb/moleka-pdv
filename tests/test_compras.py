"""Entrada de compras pelo XML da NF-e: leitura, conferência, importação e estorno.

As notas são fictícias (tests/nota_ficticia.py) e as contas estão feitas à mão nos comentários.
"""

from datetime import date, timedelta
from decimal import Decimal

from nota_ficticia import FORNECEDOR, NOME_DO_FORNECEDOR, chave, item, nota_xml
from sqlalchemy import func, select

from app import config, db, nfe_xml, tempo
from app.models import DeParaFornecedor, MovimentoEstoque, NotaEntrada, Produto
from app.operadores import RegraError

DIA = date(2026, 11, 3)  # data fixa para os testes que conferem a chave


def _decisoes(loja, *, picole=24, sorvete=10, copo="criar"):
    """As decisões do gerente para a nota 123: picolé e sorvete ligados, copo criado."""
    return [
        {"numero": 1, "acao": "vincular", "produto_id": loja["picole"], "fator": picole},
        {"numero": 2, "acao": "vincular", "produto_id": loja["sorvete"], "fator": sorvete},
        {"numero": 3, "acao": copo, "fator": 1},
    ]


def _importar(cliente, xml, itens, **mais):
    return cliente.post("/api/compras/importar", json={"xml": xml, "itens": itens, **mais})


def _estoque(cliente, produto_id):
    itens = cliente.get("/api/estoque", params={"inativos": True}).json()["itens"]
    return next(i for i in itens if i["produto_id"] == produto_id)


def _contas(cliente, **filtros):
    periodo = {
        "inicio": (tempo.hoje() - timedelta(days=90)).isoformat(),
        "fim": (tempo.hoje() + timedelta(days=90)).isoformat(),
    }
    resposta = cliente.get("/api/financeiro/lancamentos", params={**periodo, **filtros})
    assert resposta.status_code == 200, resposta.text
    return resposta.json()["itens"]


def _nada_foi_gravado(cliente, tmp_path):
    with db.nova_sessao() as sessao:
        assert sessao.scalar(select(func.count(NotaEntrada.id))) == 0
        assert sessao.scalar(select(func.count(MovimentoEstoque.id))) == 0
        assert sessao.scalar(select(func.count(DeParaFornecedor.id))) == 0
        assert sessao.scalar(select(func.count(Produto.id))) == 3  # só os da loja de teste
    assert _contas(cliente) == []
    assert not (tmp_path / "xml").exists()


# ---------------------------------------------------------------- a chave de acesso


def test_chave_de_acesso_confere_o_digito_verificador():
    # As duas chaves abaixo foram conferidas com uma biblioteca independente (erpbrasil.base).
    assert nfe_xml.chave_valida("35261111222333000181550010000001231000000122")
    assert not nfe_xml.chave_valida("35261111222333000181550010000001231000000123")  # DV errado
    assert not nfe_xml.chave_valida("35261111222333000181550010000001241000000122")  # nº trocado
    # CNPJ com letras (existe desde julho de 2026): a chave também tem letras.
    assert nfe_xml.chave_valida("35261112ABC34501DE35550010000001241000000139")
    assert not nfe_xml.chave_valida("35261112ABC34501DE35550010000001241000000130")
    # Letra fora das 12 primeiras posições do CNPJ, tamanho errado e texto solto.
    assert not nfe_xml.chave_valida("3A261111222333000181550010000001231000000122")
    assert not nfe_xml.chave_valida("3526111122233300018155001000000123100000012")
    assert not nfe_xml.chave_valida("")
    # O gerador de notas dos testes calcula o dígito por outro caminho e chega ao mesmo.
    assert chave(123, DIA) == "35261111222333000181550010000001231000001340"
    assert nfe_xml.chave_valida(chave(123, DIA))


# ---------------------------------------------------------------- a leitura do XML


def test_le_a_nota_com_o_custo_de_cada_item():
    nota = nfe_xml.ler(nota_xml(emitida=DIA))
    assert (nota.chave, nota.numero, nota.serie) == (chave(123, DIA), 123, 1)
    assert (nota.emitente_documento, nota.emitente_nome) == (FORNECEDOR, NOME_DO_FORNECEDOR)
    assert nota.destinatario_nome == "LOJA FICTICIA DE TESTE"
    assert nota.emitida_em.isoformat() == "2026-11-03T13:15:00"  # 10:15 de Brasília, em UTC
    assert nota.autorizada is True and nota.avisos == ()
    assert nota.total_centavos == 58060 and nota.custo_dos_itens_centavos == 58060

    picole, sorvete, copo = nota.itens
    # 96,00 + frete 4,00 + ICMS-ST 9,60 = 109,60. O ICMS próprio (dentro do preço) não soma.
    assert (picole.codigo, picole.unidade, picole.quantidade) == ("PIC-24", "CX", Decimal("2"))
    assert (picole.valor_unitario_centavos, picole.valor_total_centavos) == (4800, 9600)
    assert (picole.frete_centavos, picole.st_centavos, picole.custo_total_centavos) == (
        400,
        960,
        10960,
    )
    assert picole.ean is None and picole.ean_tributavel == "7890000000017"  # "SEM GTIN" não vale
    assert picole.fator_da_nota == Decimal("24")  # 48 UN em 2 CX
    # 450,00 - desconto 22,50 + IPI 13,50 = 441,00.
    assert (sorvete.desconto_centavos, sorvete.ipi_centavos, sorvete.custo_total_centavos) == (
        2250,
        1350,
        44100,
    )
    assert sorvete.fator_da_nota == Decimal("10")  # 30 KG em 3 BD
    assert (copo.custo_total_centavos, copo.ean, copo.fator_da_nota) == (
        3000,
        "7890000000994",
        None,
    )

    assert [(p.numero, p.vencimento, p.valor_centavos) for p in nota.parcelas] == [
        ("001", date(2026, 12, 3), 29030),
        ("002", date(2027, 1, 2), 29030),
    ]


def test_recusa_o_que_nao_e_o_xml_de_uma_nota_de_compra():
    def motivo(texto):
        try:
            nfe_xml.ler(texto)
        except RegraError as erro:
            return str(erro)
        return "leu"

    boa = nota_xml(emitida=DIA)
    assert motivo("") == "O arquivo está vazio."
    assert "não é um XML válido" in motivo("isto não é um XML")
    assert "não é um XML válido" in motivo(boa[: len(boa) // 2])  # arquivo cortado
    assert "não achei os dados da nota" in motivo("<?xml version='1.0'?><pedido><x>1</x></pedido>")
    assert "cupom (NFC-e)" in motivo(nota_xml(emitida=DIA, modelo="65"))
    assert "evento da nota" in motivo("<procEventoNFe><evento/></procEventoNFe>")
    # Chave com o dígito verificador errado (arquivo adulterado ou corrompido).
    errada = chave(123, DIA)[:43] + "9"
    assert "chave de acesso da nota não confere" in motivo(nota_xml(chave_de_acesso=errada))
    assert motivo(nota_xml(itens=[])) == "A nota não tem itens."
    # DOCTYPE e ENTITY não existem numa NF-e e servem para ataques: nem chegam a ser lidos.
    ataque = boa.replace("<nfeProc", '<!DOCTYPE x [<!ENTITY e "x">]><nfeProc', 1)
    assert "traz comandos que a nota não usa" in motivo(ataque)
    assert "grande demais" in motivo(boa + " " * nfe_xml.TAMANHO_MAXIMO)
    zerado = [item("X", "ITEM FICTICIO ZERADO", "UN", 1, "10.00")]
    assert "quantidade zero" in motivo(nota_xml(itens=zerado).replace("1.0000</qCom>", "0</qCom>"))


def test_avisa_o_que_o_gerente_precisa_saber_antes_de_dar_entrada():
    sem_protocolo = nfe_xml.ler(nota_xml(situacao=None))
    assert sem_protocolo.autorizada is None
    assert any("sem o protocolo de autorização" in a for a in sem_protocolo.avisos)

    negada = nfe_xml.ler(nota_xml(situacao="110"))
    assert negada.autorizada is False
    assert any("não autorizou esta nota (situação 110)" in a for a in negada.avisos)

    # Brinde: o item não entra no total da nota e dá entrada com custo zero.
    itens = [
        item("PIC-24", "PICOLE FICTICIO DE TESTE CX 24", "CX", 1, "48.00"),
        item("BRINDE", "BRINDE FICTICIO DE TESTE", "UN", 10, "10.00", entra_no_total=False),
    ]
    com_brinde = nfe_xml.ler(nota_xml(itens=itens, parcelas=None))
    assert com_brinde.total_centavos == 4800
    assert [i.custo_total_centavos for i in com_brinde.itens] == [4800, 0]
    assert com_brinde.avisos == (
        "O item 2 não entra no total da nota (bonificação ou brinde): "
        "ele dá entrada no estoque com custo zero.",
    )

    # Total da nota diferente da soma dos itens (58060): a diferença é dita, com os valores.
    diferente = nfe_xml.ler(nota_xml(total="585.60", parcelas=None))
    assert diferente.avisos == (
        "A soma do custo dos itens (R$ 580,60) é diferente do total da nota (R$ 585,60). "
        "A diferença de R$ 5,00 não entra no custo dos produtos.",
    )

    parcelas = [("1", DIA + timedelta(days=30), "500.00")]
    com_parcela_menor = nfe_xml.ler(nota_xml(parcelas=parcelas))
    assert any("soma das parcelas é diferente" in a for a in com_parcela_menor.avisos)


# ---------------------------------------------------------------- conferir (não grava)


def test_conferir_sugere_o_produto_e_nao_grava_nada(cliente, loja, tmp_path):
    resposta = cliente.post("/api/compras/conferir", json={"xml": nota_xml()})
    assert resposta.status_code == 200, resposta.text
    nota = resposta.json()
    assert (nota["numero"], nota["fornecedor_nome"]) == (123, NOME_DO_FORNECEDOR)
    assert nota["fornecedor_documento"] == "11.222.333/0001-81"
    assert (nota["total_centavos"], nota["custo_dos_itens_centavos"]) == (58060, 58060)
    assert nota["autorizada"] is True and nota["avisos"] == []
    assert (nota["ja_importada"], nota["importada_em"]) == (False, None)
    assert [p["valor_centavos"] for p in nota["parcelas"]] == [29030, 29030]

    picole, sorvete, copo = nota["itens"]
    # O picolé é achado pelo código de barras da unidade; a nota diz que a caixa tem 24.
    assert (picole["sugestao_produto_id"], picole["sugestao_origem"]) == (loja["picole"], "ean")
    assert (
        picole["sugestao_codigo"],
        picole["sugestao_descricao"],
        picole["sugestao_unidade"],
    ) == (
        "1",
        "Picolé de teste",
        "UN",
    )
    assert (float(picole["sugestao_fator"]), picole["custo_total_centavos"]) == (24.0, 10960)
    # Sem código de barras conhecido não há sugestão de produto: o gerente escolhe.
    assert (sorvete["sugestao_produto_id"], sorvete["sugestao_origem"]) == (None, None)
    assert float(sorvete["sugestao_fator"]) == 10.0  # o fator que a própria nota informa
    assert (copo["sugestao_produto_id"], float(copo["sugestao_fator"])) == (None, 1.0)
    _nada_foi_gravado(cliente, tmp_path)

    ruim = cliente.post("/api/compras/conferir", json={"xml": "<x/>"})
    assert ruim.status_code == 422 and "não achei os dados da nota" in ruim.json()["detail"]


# ---------------------------------------------------------------- importar


def test_importar_da_entrada_no_estoque_faz_o_custo_e_as_contas(cliente, loja, tmp_path):
    xml = nota_xml()
    resposta = _importar(cliente, xml, _decisoes(loja))
    assert resposta.status_code == 201, resposta.text
    feito = resposta.json()
    nota = feito["nota"]
    assert (nota["numero"], nota["itens_quantidade"], nota["contas_a_pagar"]) == (123, 3, 2)
    assert nota["estornada_em"] is None and nota["total_centavos"] == 58060
    # Entrou: 2 CX x 24 = 48 picolés; 3 BD x 10 = 30 kg; 5 pacotes.
    # Custo de cada unidade: 109,60 / 48 = 2,283 -> 2,28; 441,00 / 30 = 14,70; 30,00 / 5 = 6,00.
    assert [
        (float(i["entrou"]), i["produto_unidade"], i["custo_unitario_centavos"])
        for i in nota["itens"]
    ] == [
        (48.0, "UN", 228),
        (30.0, "KG", 1470),
        (5.0, "PCT", 600),
    ]
    assert feito["contas_a_pagar"] == 2
    assert [(p["codigo"], p["descricao"]) for p in feito["produtos_criados"]] == [
        ("4", "COPO FICTICIO DE TESTE 200 ML C/100")
    ]
    copo_id = feito["produtos_criados"][0]["id"]

    picole = _estoque(cliente, loja["picole"])
    assert (float(picole["saldo"]), picole["custo_centavos"], picole["ultimo_custo_centavos"]) == (
        48.0,
        228,
        228,
    )
    assert picole["valor_centavos"] == 10944  # 48 x 2,28 (o custo é arredondado ao centavo)
    sorvete = _estoque(cliente, loja["sorvete"])
    assert (float(sorvete["saldo"]), sorvete["custo_centavos"], sorvete["valor_centavos"]) == (
        30.0,
        1470,
        44100,
    )
    copo = _estoque(cliente, copo_id)
    assert (float(copo["saldo"]), copo["custo_centavos"], copo["unidade"]) == (5.0, 600, "PCT")
    cadastro = cliente.get(f"/api/produtos/{copo_id}").json()
    assert (cadastro["ean"], cadastro["ncm"], cadastro["precos"]) == (
        "7890000000994",
        "21050010",
        [],
    )

    historico = cliente.get(f"/api/estoque/{loja['picole']}/movimentos").json()
    assert [
        (m["rotulo"], float(m["quantidade"]), m["custo_unitario_centavos"]) for m in historico
    ] == [("Entrada de nota", 48.0, 228)]
    assert historico[0]["motivo"] == f"NF 123 de {NOME_DO_FORNECEDOR}"
    assert historico[0]["referencia"] == f"nota:{nota['id']}"

    # Uma conta a pagar por parcela, fora do resultado (o custo vai para o DRE quando vender).
    emitida = tempo.hoje() - timedelta(days=5)
    assert [
        (c["descricao"], c["valor_centavos"], c["vencimento"], c["situacao"])
        for c in _contas(cliente)
    ] == [
        (
            f"NF 123 de {NOME_DO_FORNECEDOR}, parcela 001",
            29030,
            (emitida + timedelta(days=30)).isoformat(),
            "aberto",
        ),
        (
            f"NF 123 de {NOME_DO_FORNECEDOR}, parcela 002",
            29030,
            (emitida + timedelta(days=60)).isoformat(),
            "aberto",
        ),
    ]
    conta = _contas(cliente)[0]
    assert (conta["tipo"], conta["origem"], conta["grupo"]) == ("despesa", "compra", "fora_do_dre")
    assert conta["categoria"] == "Compra de mercadorias para revenda"
    assert conta["competencia"] == emitida.isoformat()

    # O arquivo da nota fica guardado na pasta de dados, igual ao que foi enviado.
    assert config.pasta_dados() == tmp_path
    guardado = tmp_path / "xml" / "entrada" / f"{nota['chave']}.xml"
    assert guardado.read_text(encoding="utf-8") == xml

    # A mesma nota não entra duas vezes.
    de_novo = _importar(cliente, xml, _decisoes(loja))
    assert de_novo.status_code == 409 and "já foi importada em" in de_novo.json()["detail"]
    conferida = cliente.post("/api/compras/conferir", json={"xml": xml}).json()
    assert conferida["ja_importada"] is True and conferida["importada_em"] is not None
    assert float(_estoque(cliente, loja["picole"])["saldo"]) == 48.0
    assert [n["numero"] for n in cliente.get("/api/compras").json()] == [123]


def test_o_sistema_lembra_a_ligacao_e_a_segunda_nota_refaz_o_custo_medio(cliente, loja, vender):
    _importar(cliente, nota_xml(), _decisoes(loja))
    vender([(loja["picole"], 8)])  # sobram 40 picolés, a 2,28

    # Outra nota do mesmo fornecedor, só com a caixa de picolé, agora a 62,40.
    caixa = item(
        "PIC-24",
        "PICOLE FICTICIO DE TESTE CX 24",
        "CX",
        1,
        "62.40",
        unidade_trib="UN",
        quantidade_trib=24,
    )
    xml = nota_xml(124, [caixa], parcelas=None)
    lida = cliente.post("/api/compras/conferir", json={"xml": xml}).json()["itens"][0]
    # Sem código de barras na nota, mas o sistema lembra: este código do fornecedor é o picolé.
    assert (lida["sugestao_produto_id"], lida["sugestao_origem"]) == (loja["picole"], "memoria")
    assert float(lida["sugestao_fator"]) == 24.0

    decisao = [{"numero": 1, "acao": "vincular", "produto_id": loja["picole"], "fator": 24}]
    feito = _importar(cliente, xml, decisao)
    assert feito.status_code == 201, feito.text
    assert feito.json()["contas_a_pagar"] == 0  # a nota não traz parcelas
    picole = _estoque(cliente, loja["picole"])
    # 40 a 2,28 = 91,20; + 24 a 2,60 = 62,40; total 153,60 em 64 unidades = 2,40.
    assert (float(picole["saldo"]), picole["custo_centavos"], picole["ultimo_custo_centavos"]) == (
        64.0,
        240,
        260,
    )

    # Estorno logo depois: o custo volta exatamente ao que era (2,28) e o saldo a 40.
    nota_id = feito.json()["nota"]["id"]
    estorno = cliente.post(
        f"/api/compras/{nota_id}/estornar", json={"motivo": "nota de outra loja"}
    )
    assert estorno.status_code == 200, estorno.text
    assert estorno.json()["custos_para_conferir"] == []
    assert estorno.json()["nota"]["motivo_estorno"] == "nota de outra loja"
    picole = _estoque(cliente, loja["picole"])
    assert (float(picole["saldo"]), picole["custo_centavos"], picole["ultimo_custo_centavos"]) == (
        40.0,
        228,
        228,
    )
    historico = cliente.get(f"/api/estoque/{loja['picole']}/movimentos").json()
    assert (historico[0]["rotulo"], float(historico[0]["quantidade"])) == ("Entrada de nota", -24.0)
    assert historico[0]["motivo"] == (
        f"Estorno da NF 124 de {NOME_DO_FORNECEDOR}: nota de outra loja"
    )


def test_estorno_com_outra_entrada_no_meio_faz_a_conta_inversa(cliente, loja):
    _importar(cliente, nota_xml(), _decisoes(loja))  # 48 picolés a 2,28
    entrada = cliente.post(
        "/api/estoque/ajustes",
        json={
            "produto_id": loja["picole"],
            "tipo": "entrada",
            "quantidade": 52,
            "motivo": "compra sem nota",
            "custo_unitario_centavos": 300,
        },
    ).json()
    # 48 a 2,28 = 109,44; + 52 a 3,00 = 156,00; total 265,44 em 100 = 2,6544 -> 2,65.
    assert (float(entrada["saldo"]), entrada["custo_centavos"]) == (100.0, 265)

    nota_id = cliente.get("/api/compras").json()[0]["id"]
    estorno = cliente.post(f"/api/compras/{nota_id}/estornar", json={"motivo": "devolução"})
    assert estorno.status_code == 200, estorno.text
    picole = _estoque(cliente, loja["picole"])
    # Conta inversa: 100 a 2,65 = 265,00; - 48 a 2,28 = 109,44; sobram 155,56 em 52 = 2,9915
    # -> 2,99 (o custo exato seria 3,00: a diferença de 1 centavo vem dos arredondamentos).
    assert (float(picole["saldo"]), picole["custo_centavos"]) == (52.0, 299)
    assert picole["ultimo_custo_centavos"] == 300  # a última entrada que continua valendo
    assert estorno.json()["custos_para_conferir"] == []


def test_estorno_cancela_as_contas_e_a_nota_pode_entrar_de_novo(cliente, loja):
    xml = nota_xml()
    nota_id = _importar(cliente, xml, _decisoes(loja)).json()["nota"]["id"]
    copo_id = next(
        p["id"] for p in cliente.get("/api/produtos").json() if p["descricao"].startswith("COPO")
    )
    primeira, _segunda = _contas(cliente)

    sem_motivo = cliente.post(f"/api/compras/{nota_id}/estornar", json={"motivo": " "})
    assert sem_motivo.status_code == 422 and "motivo" in sem_motivo.json()["detail"]
    # Conta de nota não é cancelada à mão: o caminho é estornar a nota.
    a_mao = cliente.post(f"/api/financeiro/lancamentos/{primeira['id']}/cancelar")
    assert a_mao.status_code == 409 and "estorne a nota" in a_mao.json()["detail"]

    # Parcela já paga segura o estorno, até a baixa ser desfeita.
    hoje = tempo.hoje().isoformat()
    baixa = cliente.post(
        f"/api/financeiro/lancamentos/{primeira['id']}/baixa", json={"data": hoje, "forma": "pix"}
    )
    assert baixa.status_code == 200, baixa.text
    paga = cliente.post(f"/api/compras/{nota_id}/estornar", json={"motivo": "devolução"})
    assert paga.status_code == 409 and "já paga" in paga.json()["detail"]
    assert float(_estoque(cliente, loja["picole"])["saldo"]) == 48.0  # nada foi desfeito
    assert cliente.delete(f"/api/financeiro/lancamentos/{primeira['id']}/baixa").status_code == 200

    estorno = cliente.post(f"/api/compras/{nota_id}/estornar", json={"motivo": "devolução total"})
    assert estorno.status_code == 200, estorno.text
    nota = estorno.json()["nota"]
    assert nota["estornada_em"] is not None and nota["contas_a_pagar"] == 0
    for produto_id in (loja["picole"], loja["sorvete"], copo_id):
        produto = _estoque(cliente, produto_id)  # tudo volta: saldo zero e sem custo, como antes
        assert (float(produto["saldo"]), produto["custo_centavos"]) == (0.0, None), produto
        assert produto["ultimo_custo_centavos"] is None
    assert _contas(cliente) == []
    assert [c["situacao"] for c in _contas(cliente, situacao="cancelado")] == ["cancelado"] * 2
    de_novo = cliente.post(f"/api/compras/{nota_id}/estornar", json={"motivo": "outra vez"})
    assert de_novo.status_code == 409 and "já está estornada" in de_novo.json()["detail"]

    # A nota estornada pode entrar de novo, e o sistema lembra as três ligações (inclusive a do
    # produto que ele mesmo criou na primeira vez).
    lida = cliente.post("/api/compras/conferir", json={"xml": xml}).json()
    assert lida["ja_importada"] is False
    assert [i["sugestao_origem"] for i in lida["itens"]] == ["memoria"] * 3
    decisoes = [
        {"numero": i["numero"], "acao": "vincular", "produto_id": i["sugestao_produto_id"],
         "fator": i["sugestao_fator"]}
        for i in lida["itens"]
    ]  # fmt: skip
    outra_vez = _importar(cliente, xml, decisoes)
    assert outra_vez.status_code == 201, outra_vez.text
    assert outra_vez.json()["nota"]["id"] == nota_id and outra_vez.json()["produtos_criados"] == []
    assert [n["estornada_em"] for n in cliente.get("/api/compras").json()] == [None]  # uma só
    picole = _estoque(cliente, loja["picole"])
    assert (float(picole["saldo"]), picole["custo_centavos"]) == (48.0, 228)
    assert len(_contas(cliente)) == 2


def test_estorno_avisa_quando_nao_consegue_refazer_o_custo(cliente, loja):
    agua = item("AGUA-1", "AGUA FICTICIA DE TESTE 500 ML", "UN", 10, "15.00")
    decisao = [{"numero": 1, "acao": "vincular", "produto_id": loja["agua"], "fator": 1}]
    nota_id = _importar(cliente, nota_xml(125, [agua], parcelas=None), decisao).json()["nota"]["id"]
    assert _estoque(cliente, loja["agua"])["custo_centavos"] == 150
    # O gerente corrige o custo à mão depois da entrada...
    cadastro = cliente.get(f"/api/produtos/{loja['agua']}").json()
    cliente.put(f"/api/produtos/{loja['agua']}", json={**cadastro, "custo_centavos": 160})
    # ...e a nota estornada era o saldo todo: não há conta que diga o custo de antes.
    estorno = cliente.post(f"/api/compras/{nota_id}/estornar", json={"motivo": "engano"}).json()
    assert estorno["custos_para_conferir"] == ["Água de teste"]
    agua_no_estoque = _estoque(cliente, loja["agua"])
    assert (float(agua_no_estoque["saldo"]), agua_no_estoque["custo_centavos"]) == (0.0, 160)


def test_importar_confere_tudo_antes_de_gravar(cliente, loja, tmp_path):
    xml = nota_xml()

    def recusa(itens, trecho, **mais):
        resposta = _importar(cliente, xml, itens, **mais)
        assert resposta.status_code == 422, resposta.text
        assert trecho in resposta.json()["detail"], resposta.json()["detail"]

    recusa(_decisoes(loja)[:2], "Falta decidir o que fazer com o item 3")
    recusa(_decisoes(loja) + [{"numero": 9, "acao": "ignorar"}], "item que não existe")
    recusa(_decisoes(loja) + [{"numero": 3, "acao": "ignorar"}], "mais de uma decisão")
    recusa(_decisoes(loja, copo="talvez"), "Item 3: escolha o que fazer")
    recusa(_decisoes(loja, picole=0), "Item 1: o fator de conversão precisa ser maior que zero")
    sem_produto = _decisoes(loja)
    sem_produto[0]["produto_id"] = None
    recusa(sem_produto, "Item 1: escolha o produto")
    # 2 caixas x 0,25 = meio picolé: produto por unidade não aceita.
    recusa(_decisoes(loja, picole="0.25"), "Item 1:")
    recusa(_decisoes(loja, picole="0.25"), "Confira o fator de conversão")
    # Produto novo: 5 pacotes x 0,5 = 2,5 pacotes também não.
    quebrado = _decisoes(loja)
    quebrado[2]["fator"] = "0.5"
    recusa(quebrado, "Item 3: entrariam 2,5 UN")
    recusa(_decisoes(loja), "não serve para despesa", categoria_id=_categoria(cliente, "receita"))
    recusa(_decisoes(loja), "Escolha a categoria", categoria_id=999)

    cadastro = cliente.get(f"/api/produtos/{loja['sorvete']}").json()
    cliente.put(f"/api/produtos/{loja['sorvete']}", json={**cadastro, "ativo": False})
    recusa(_decisoes(loja), "Item 2: o produto “Sorvete de teste por quilo” está inativo")
    _nada_foi_gravado(cliente, tmp_path)


def _categoria(cliente, tipo):
    """Cria uma categoria de teste: de receita ("Outras receitas") ou do grupo de custo."""
    grupo = {"receita": "outras_receitas", "custo": "cmv"}[tipo]
    resposta = cliente.post(
        "/api/financeiro/categorias", json={"nome": f"Categoria de teste ({tipo})", "grupo": grupo}
    )
    assert resposta.status_code == 201, resposta.text
    return resposta.json()["id"]


def test_item_sem_entrada_brinde_e_nota_sem_parcelas(cliente, loja):
    itens = [
        item("LEITE", "LEITE FICTICIO DE TESTE 1 L", "UN", 12, "60.00"),
        item("PIC-UN", "PICOLE FICTICIO DE TESTE AVULSO", "UN", 10, "10.00", entra_no_total=False),
    ]
    xml = nota_xml(126, itens, parcelas=None)
    # O leite é matéria-prima: não dá entrada no estoque. O brinde entra no picolé.
    cliente.post(
        "/api/estoque/ajustes",
        json={
            "produto_id": loja["picole"],
            "tipo": "entrada",
            "quantidade": 10,
            "motivo": "produção",
            "custo_unitario_centavos": 200,
        },
    )
    decisoes = [
        {"numero": 1, "acao": "ignorar"},
        {"numero": 2, "acao": "vincular", "produto_id": loja["picole"], "fator": 1},
    ]
    materia_prima = _categoria(cliente, "custo")
    vencimento = tempo.hoje() + timedelta(days=10)
    feito = _importar(
        cliente,
        xml,
        decisoes,
        categoria_id=materia_prima,
        vencimento_sem_parcelas=vencimento.isoformat(),
    )
    assert feito.status_code == 201, feito.text
    leite, brinde = feito.json()["nota"]["itens"]
    assert (leite["produto_id"], leite["entrou"], leite["custo_unitario_centavos"]) == (
        None,
        None,
        None,
    )
    assert (float(brinde["entrou"]), brinde["custo_unitario_centavos"]) == (10.0, 0)
    picole = _estoque(cliente, loja["picole"])
    # 10 a 2,00 + 10 de brinde a 0,00 = 20,00 em 20 unidades = 1,00.
    assert (float(picole["saldo"]), picole["custo_centavos"]) == (20.0, 100)

    # Nota sem parcelas: uma conta com o total, no vencimento e na categoria escolhidos.
    assert [
        (c["descricao"], c["valor_centavos"], c["vencimento"], c["categoria"], c["grupo"])
        for c in _contas(cliente)
    ] == [
        (
            f"NF 126 de {NOME_DO_FORNECEDOR}",
            6000,
            vencimento.isoformat(),
            "Categoria de teste (custo)",
            "cmv",
        )
    ]

    # Sem pedir a conta (ou sem o vencimento), nenhuma conta nasce.
    outra = nota_xml(
        127, [item("LEITE", "LEITE FICTICIO DE TESTE 1 L", "UN", 1, "5.00")], parcelas=None
    )
    so_ignora = [{"numero": 1, "acao": "ignorar"}]
    assert _importar(cliente, outra, so_ignora).json()["contas_a_pagar"] == 0
    com_parcelas = nota_xml(128, [item("LEITE", "LEITE FICTICIO DE TESTE 1 L", "UN", 1, "5.00")])
    sem_contas = _importar(cliente, com_parcelas, so_ignora, gerar_contas=False)
    assert sem_contas.status_code == 201 and sem_contas.json()["contas_a_pagar"] == 0
    assert len(_contas(cliente)) == 1


def test_fornecedor_com_cnpj_de_letras(cliente, loja):
    xml = nota_xml(
        129,
        [item("AGUA-1", "AGUA FICTICIA DE TESTE 500 ML", "UN", 10, "15.00")],
        emitente="12ABC34501DE35",
        nome="FORNECEDOR FICTICIO COM LETRAS LTDA",
        parcelas=None,
    )
    lida = cliente.post("/api/compras/conferir", json={"xml": xml})
    assert lida.status_code == 200, lida.text
    assert lida.json()["fornecedor_documento"] == "12.ABC.345/01DE-35"
    assert "12ABC34501DE35" in lida.json()["chave"]
    decisao = [{"numero": 1, "acao": "vincular", "produto_id": loja["agua"], "fator": 1}]
    assert _importar(cliente, xml, decisao).status_code == 201
    assert cliente.get("/api/compras").json()[0]["fornecedor_documento"] == "12.ABC.345/01DE-35"


def test_so_o_gerente_da_entrada_em_nota(anonimo, caixa, loja, tmp_path):
    xml = nota_xml()
    pedidos = (
        ("get", "/api/compras", None),
        ("get", "/api/compras/1", None),
        ("post", "/api/compras/conferir", {"xml": xml}),
        ("post", "/api/compras/importar", {"xml": xml, "itens": _decisoes(loja)}),
        ("post", "/api/compras/1/estornar", {"motivo": "x"}),
    )
    for metodo, caminho, corpo in pedidos:
        assert caixa.request(metodo, caminho, json=corpo).status_code == 403, caminho
        assert anonimo.request(metodo, caminho, json=corpo).status_code == 401, caminho
    assert not (tmp_path / "xml").exists()

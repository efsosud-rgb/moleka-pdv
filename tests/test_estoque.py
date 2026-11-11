"""Estoque: saldo pelos movimentos, custo médio, ajuste com motivo, contagem e permissões."""

from decimal import Decimal

from sqlalchemy import func, select

from app import db, estoque
from app.models import MovimentoEstoque, TipoMovimentoEstoque, VendaItem


def _ajuste(cliente, produto_id, tipo, quantidade, motivo="teste", custo=None):
    dados = {"produto_id": produto_id, "tipo": tipo, "quantidade": quantidade, "motivo": motivo}
    if custo is not None:
        dados["custo_unitario_centavos"] = custo
    return cliente.post("/api/estoque/ajustes", json=dados)


def _item(cliente, produto_id, **filtros):
    itens = cliente.get("/api/estoque", params={"inativos": True, **filtros}).json()["itens"]
    return next(i for i in itens if i["produto_id"] == produto_id)


def _resumo(cliente):
    return cliente.get("/api/estoque").json()["resumo"]


# ---------------------------------------------------------------- a conta do custo médio


def test_custo_medio_ponderado_em_centavos():
    d = Decimal
    # Primeira entrada (sem custo anterior): o custo da entrada vira o custo médio.
    assert estoque.custo_medio(d(0), None, d(10), 200) == 200
    # 10 a 2,00 + 30 a 3,00 = 110,00 em 40 unidades = 2,75.
    assert estoque.custo_medio(d(10), 200, d(30), 300) == 275
    # 3 a 1,00 + 1 a 1,02 = 4,02 em 4 = 1,005 -> arredonda para cima: 1,01.
    assert estoque.custo_medio(d(3), 100, d(1), 102) == 101
    # Quilo: 1,500 kg a 20,00 + 0,500 kg a 30,00 = 45,00 em 2 kg = 22,50.
    assert estoque.custo_medio(d("1.500"), 2000, d("0.500"), 3000) == 2250
    # Saldo zerado ou negativo não entra na média: vale o custo da entrada.
    assert estoque.custo_medio(d(0), 200, d(5), 300) == 300
    assert estoque.custo_medio(d(-5), 200, d(10), 300) == 300


def test_custo_medio_volta_no_estorno_quando_da_para_calcular():
    d = Decimal
    # O inverso da conta acima: 40 a 2,75 = 110,00; tirando 30 a 3,00 sobram 20,00 em 10 = 2,00.
    assert estoque.custo_medio_sem_a_entrada(d(40), 275, d(30), 300) == 200
    # A entrada estornada era o saldo todo (ou mais): não há como saber o custo de antes.
    assert estoque.custo_medio_sem_a_entrada(d(30), 300, d(30), 300) is None
    assert estoque.custo_medio_sem_a_entrada(d(10), 300, d(30), 300) is None
    # Produto sem custo, ou conta que daria custo negativo: também não.
    assert estoque.custo_medio_sem_a_entrada(d(40), None, d(30), 300) is None
    assert estoque.custo_medio_sem_a_entrada(d(40), 100, d(30), 300) is None


# ---------------------------------------------------------------- saldos e valor


def test_estoque_comeca_zerado_e_sem_valor(cliente, loja):
    estado = cliente.get("/api/estoque").json()
    assert [(i["descricao"], float(i["saldo"]), i["situacao"]) for i in estado["itens"]] == [
        ("Água de teste", 0.0, "zerado"),  # ordem alfabética, sem contar o acento
        ("Picolé de teste", 0.0, "zerado"),
        ("Sorvete de teste por quilo", 0.0, "zerado"),
    ]
    assert all(i["valor_centavos"] is None and i["custo_centavos"] is None for i in estado["itens"])
    assert estado["resumo"] == {
        "produtos": 3,
        "com_saldo": 0,
        "abaixo_do_minimo": 0,
        "negativos": 0,
        "valor_centavos": None,  # sem saldo, a tela mostra "—" e o motivo
        "sem_custo": 0,
        "motivo_do_valor": "nenhum produto com saldo",
    }


def test_ajustes_fazem_o_saldo_o_custo_medio_e_o_valor(cliente, loja):
    picole, sorvete, agua = loja["picole"], loja["sorvete"], loja["agua"]

    entrada = _ajuste(cliente, picole, "entrada", "10", "produção do dia", custo=200)
    assert entrada.status_code == 201, entrada.text
    item = entrada.json()
    assert (float(item["saldo"]), item["custo_centavos"], item["ultimo_custo_centavos"]) == (
        10.0,
        200,
        200,
    )
    assert item["valor_centavos"] == 2000 and item["situacao"] == "ok"

    item = _ajuste(cliente, picole, "entrada", 30, "compra sem nota", custo=300).json()
    # 10 a 2,00 + 30 a 3,00 = 110,00 em 40 = 2,75 de custo médio; o último custo é 3,00.
    assert (float(item["saldo"]), item["custo_centavos"], item["ultimo_custo_centavos"]) == (
        40.0,
        275,
        300,
    )
    assert item["valor_centavos"] == 11000

    item = _ajuste(cliente, picole, "saida", "4", "quebra no freezer").json()
    # A saída não mexe no custo: 36 a 2,75 = 99,00.
    assert (float(item["saldo"]), item["custo_centavos"], item["valor_centavos"]) == (
        36.0,
        275,
        9900,
    )

    # Entrada sem custo: o saldo sobe e o custo médio fica como estava.
    item = _ajuste(cliente, picole, "entrada", 4, "achados na contagem").json()
    assert (float(item["saldo"]), item["custo_centavos"], item["valor_centavos"]) == (
        40.0,
        275,
        11000,
    )

    # Produto por quilo aceita quantidade quebrada: 2,350 kg a 25,00 = 58,75.
    item = _ajuste(cliente, sorvete, "entrada", "2,350", "produção", custo=2500).json()
    assert (float(item["saldo"]), item["valor_centavos"]) == (2.35, 5875)

    resumo = _resumo(cliente)
    assert (resumo["com_saldo"], resumo["valor_centavos"], resumo["sem_custo"]) == (2, 16875, 0)
    assert resumo["motivo_do_valor"] == ""

    # Água com saldo e sem custo: fica fora do valor, e o resumo diz isso.
    assert _ajuste(cliente, agua, "entrada", 5, "doação").status_code == 201
    resumo = _resumo(cliente)
    assert (resumo["com_saldo"], resumo["valor_centavos"], resumo["sem_custo"]) == (3, 16875, 1)
    assert resumo["motivo_do_valor"] == (
        "1 produto(s) com saldo estão sem custo e ficaram fora desta soma"
    )


def test_ajuste_recusa_o_que_nao_faz_sentido(cliente, loja):
    picole = loja["picole"]
    sem_motivo = _ajuste(cliente, picole, "entrada", 1, motivo="  ")
    assert sem_motivo.status_code == 422 and "motivo" in sem_motivo.json()["detail"]
    quebrado = _ajuste(cliente, picole, "entrada", "1,5")
    assert quebrado.status_code == 422 and "unidade inteira" in quebrado.json()["detail"]
    for quantidade in ("0", "-3", "abc", "1000000"):
        assert _ajuste(cliente, picole, "entrada", quantidade).status_code == 422, quantidade
    custo_na_saida = _ajuste(cliente, picole, "saida", 1, custo=100)
    assert custo_na_saida.status_code == 422 and "entrada" in custo_na_saida.json()["detail"]
    assert _ajuste(cliente, picole, "entrada", 1, custo=-1).status_code == 422
    assert _ajuste(cliente, picole, "troca", 1).status_code == 422
    assert _ajuste(cliente, 999, "entrada", 1).status_code == 404
    with db.nova_sessao() as sessao:  # nada disso gravou movimento
        assert sessao.scalar(select(func.count(MovimentoEstoque.id))) == 0


# ---------------------------------------------------------------- venda e estoque


def test_venda_baixa_o_estoque_e_guarda_o_custo_do_dia(cliente, loja, vender):
    picole = loja["picole"]
    _ajuste(cliente, picole, "entrada", 10, "produção", custo=200)
    venda = vender([(picole, 3)])
    assert float(_item(cliente, picole)["saldo"]) == 7.0

    # Uma entrada mais cara depois da venda muda o custo médio do produto...
    item = _ajuste(cliente, picole, "entrada", 7, "compra", custo=300).json()
    assert item["custo_centavos"] == 250  # 7 a 2,00 + 7 a 3,00 = 35,00 em 14
    with db.nova_sessao() as sessao:  # ...mas a venda antiga continua com o custo daquele dia.
        vendido = sessao.scalars(select(VendaItem)).one()
        assert vendido.custo_unitario_centavos == 200

    cancelada = cliente.post(f"/api/vendas/{venda['id']}/cancelar", json={"motivo": "engano"})
    assert cancelada.status_code == 200, cancelada.text
    item = _item(cliente, picole)
    assert (float(item["saldo"]), item["custo_centavos"]) == (
        17.0,
        250,
    )  # volta, sem mexer no custo

    historico = cliente.get(f"/api/estoque/{picole}/movimentos").json()
    assert [(m["rotulo"], float(m["quantidade"]), float(m["saldo_depois"])) for m in historico] == [
        ("Venda cancelada", 3.0, 17.0),  # do mais novo para o mais antigo
        ("Ajuste", 7.0, 14.0),
        ("Venda", -3.0, 7.0),
        ("Ajuste", 10.0, 10.0),
    ]
    assert historico[0]["motivo"] == "engano" and historico[0]["operador"] == "Gerente de Teste"
    assert historico[1]["custo_unitario_centavos"] == 300
    assert historico[2]["referencia"] == f"venda:{venda['id']}"


def test_vender_sem_estoque_nao_e_bloqueado_e_o_saldo_fica_negativo(cliente, loja, vender):
    vender([(loja["agua"], 2)])
    item = _item(cliente, loja["agua"])
    assert (float(item["saldo"]), item["situacao"], item["valor_centavos"]) == (
        -2.0,
        "negativo",
        None,
    )
    assert _resumo(cliente)["negativos"] == 1
    negativos = cliente.get("/api/estoque", params={"situacao": "negativo"}).json()["itens"]
    assert [i["produto_id"] for i in negativos] == [loja["agua"]]
    # Produto vendido sem custo cadastrado: a venda fica sem custo (o lucro não é inventado).
    with db.nova_sessao() as sessao:
        assert sessao.scalars(select(VendaItem)).one().custo_unitario_centavos is None


# ---------------------------------------------------------------- contagem (inventário)


def test_contagem_grava_so_a_diferenca(cliente, loja):
    picole = loja["picole"]
    _ajuste(cliente, picole, "entrada", 10, "produção", custo=200)

    contagem = cliente.post(
        "/api/estoque/contagens",
        json={"produto_id": picole, "contado": "8", "motivo": "inventário de novembro"},
    )
    assert contagem.status_code == 201, contagem.text
    dados = contagem.json()
    assert (float(dados["saldo_antes"]), float(dados["diferenca"])) == (10.0, -2.0)
    assert (float(dados["item"]["saldo"]), dados["item"]["custo_centavos"]) == (8.0, 200)

    # Contou e bateu: nada é gravado.
    igual = cliente.post("/api/estoque/contagens", json={"produto_id": picole, "contado": 8})
    assert igual.status_code == 201 and float(igual.json()["diferenca"]) == 0.0
    with db.nova_sessao() as sessao:
        movimentos = sessao.scalars(select(MovimentoEstoque).order_by(MovimentoEstoque.id)).all()
        assert [(m.tipo, Decimal(m.quantidade)) for m in movimentos] == [
            (TipoMovimentoEstoque.AJUSTE, Decimal("10")),
            (TipoMovimentoEstoque.INVENTARIO, Decimal("-2")),
        ]
        assert movimentos[1].motivo == (
            "Contagem: o sistema tinha 10 e foram contados 8. inventário de novembro"
        )

    # Contar zero vale (acabou); negativo e quebrado em produto por unidade, não.
    zero = cliente.post("/api/estoque/contagens", json={"produto_id": picole, "contado": "0"})
    assert zero.status_code == 201 and float(zero.json()["item"]["saldo"]) == 0.0
    for contado in ("-1", "2,5", "x"):
        resposta = cliente.post(
            "/api/estoque/contagens", json={"produto_id": picole, "contado": contado}
        )
        assert resposta.status_code == 422, contado

    # A contagem também acerta um saldo negativo (vendeu sem dar entrada).
    agua = loja["agua"]
    _ajuste(cliente, agua, "saida", 3, "consumo")
    acerto = cliente.post("/api/estoque/contagens", json={"produto_id": agua, "contado": 12})
    assert (float(acerto.json()["saldo_antes"]), float(acerto.json()["diferenca"])) == (-3.0, 15.0)
    assert float(_item(cliente, agua)["saldo"]) == 12.0


# ---------------------------------------------------------------- mínimo, pesquisa e permissão


def test_estoque_minimo_pesquisa_e_inativos(cliente, loja):
    casquinha = cliente.post(
        "/api/produtos", json={"descricao": "Casquinha de teste", "estoque_minimo": "5"}
    ).json()["id"]
    _ajuste(cliente, casquinha, "entrada", 3, "compra")
    assert _item(cliente, casquinha)["situacao"] == "abaixo"
    assert _resumo(cliente)["abaixo_do_minimo"] == 1
    abaixo = cliente.get("/api/estoque", params={"situacao": "abaixo"}).json()["itens"]
    assert [i["descricao"] for i in abaixo] == ["Casquinha de teste"]
    _ajuste(cliente, casquinha, "entrada", 2, "compra")
    assert _item(cliente, casquinha)["situacao"] == "ok"  # chegou ao mínimo
    com_saldo = cliente.get("/api/estoque", params={"situacao": "com_saldo"}).json()["itens"]
    assert [i["descricao"] for i in com_saldo] == ["Casquinha de teste"]

    def achados(**filtros):
        itens = cliente.get("/api/estoque", params=filtros).json()["itens"]
        return [i["descricao"] for i in itens]

    assert achados(busca="agua") == ["Água de teste"]  # sem acento, como se digita no caixa
    assert achados(busca="PICOLES") == ["Picolé de teste"]  # pela categoria
    assert achados(busca="7890000000017") == ["Picolé de teste"]  # pelo código de barras (leitor)
    assert achados(busca="não existe") == []

    # Produto inativo some da lista e do resumo, mas aparece quando pedido.
    produto = cliente.get(f"/api/produtos/{casquinha}").json()
    inativar = cliente.put(f"/api/produtos/{casquinha}", json={**produto, "ativo": False})
    assert inativar.status_code == 200, inativar.text
    assert "Casquinha de teste" not in achados()
    assert "Casquinha de teste" in achados(inativos=True)
    assert _resumo(cliente)["produtos"] == 3


def test_so_o_gerente_ve_e_mexe_no_estoque(anonimo, caixa, loja):
    pedidos = (
        ("get", "/api/estoque", None),
        ("get", f"/api/estoque/{loja['picole']}/movimentos", None),
        (
            "post",
            "/api/estoque/ajustes",
            {"produto_id": loja["picole"], "tipo": "entrada", "quantidade": 1, "motivo": "x"},
        ),
        ("post", "/api/estoque/contagens", {"produto_id": loja["picole"], "contado": 1}),
    )
    for metodo, caminho, corpo in pedidos:
        assert caixa.request(metodo, caminho, json=corpo).status_code == 403, caminho
        assert anonimo.request(metodo, caminho, json=corpo).status_code == 401, caminho
    with db.nova_sessao() as sessao:
        assert sessao.scalar(select(func.count(MovimentoEstoque.id))) == 0

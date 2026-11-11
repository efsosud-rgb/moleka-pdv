"""Cadastros: produtos e preços, tabelas, formas de pagamento e clientes."""

from conftest import OPERADOR

CPF = "529.982.247-25"  # número de teste, gerado pela regra dos dígitos
CNPJ = "11.222.333/0001-81"


def _produto(cliente, **dados):
    return cliente.post("/api/produtos", json={"descricao": "Produto de teste", **dados})


# ---------------------------------------------------------------- produtos


def test_produto_sem_codigo_recebe_o_proximo_numero(cliente):
    assert _produto(cliente).json()["codigo"] == "1"
    assert _produto(cliente, codigo="ABC").json()["codigo"] == "ABC"
    assert _produto(cliente, codigo="7").json()["codigo"] == "7"
    assert _produto(cliente).json()["codigo"] == "8"  # depois do maior código numérico


def test_produto_valida_o_que_foi_digitado(cliente):
    assert _produto(cliente, descricao="   ").status_code == 422
    resposta = _produto(cliente, ean="789-abc")
    assert resposta.status_code == 422 and "Código de barras" in resposta.json()["detail"]
    assert _produto(cliente, ncm="123").status_code == 422
    assert _produto(cliente, custo_centavos=-1).status_code == 422
    ok = _produto(cliente, descricao="  Picolé   de  uva ", unidade="kg", ean="7890000000017")
    assert ok.status_code == 201
    assert (ok.json()["descricao"], ok.json()["unidade"]) == ("Picolé de uva", "KG")
    repetido = _produto(cliente, ean="7890000000017")
    assert repetido.status_code == 409 and "Picolé de uva" in repetido.json()["detail"]


def test_precos_por_tabela_e_por_quantidade(cliente, loja):
    varejo, atacado = loja["varejo"], loja["atacado"]

    def com_precos(precos):
        return _produto(cliente, precos=precos)

    sem_faixa_1 = com_precos([{"tabela_id": varejo, "qtd_min": "10", "preco_centavos": 450}])
    assert sem_faixa_1.status_code == 422 and "a partir de 1" in sem_faixa_1.json()["detail"]
    duplicada = com_precos(
        [
            {"tabela_id": varejo, "qtd_min": "1", "preco_centavos": 500},
            {"tabela_id": varejo, "qtd_min": "1.000", "preco_centavos": 480},
        ]
    )
    assert duplicada.status_code == 422 and "mesma quantidade" in duplicada.json()["detail"]
    assert com_precos([{"tabela_id": 999, "preco_centavos": 1}]).status_code == 422
    assert com_precos([{"tabela_id": varejo, "preco_centavos": -5}]).status_code == 422

    criado = com_precos(
        [
            {"tabela_id": varejo, "qtd_min": "1", "preco_centavos": 500},
            {"tabela_id": atacado, "qtd_min": "1", "preco_centavos": 400},
        ]
    ).json()
    # Alterar regrava as faixas: troca um preço, acrescenta uma faixa e tira o atacado.
    alterado = cliente.put(
        f"/api/produtos/{criado['id']}",
        json={
            "codigo": criado["codigo"],
            "descricao": "Produto de teste alterado",
            "categoria": " Picolés ",
            "precos": [
                {"tabela_id": varejo, "qtd_min": "1", "preco_centavos": 550},
                {"tabela_id": varejo, "qtd_min": "12", "preco_centavos": 500},
            ],
        },
    )
    assert alterado.status_code == 200, alterado.text
    corpo = alterado.json()
    assert corpo["categoria"] == "Picolés"
    assert [
        (p["tabela_id"], float(p["qtd_min"]), p["preco_centavos"]) for p in corpo["precos"]
    ] == [
        (varejo, 1.0, 550),
        (varejo, 12.0, 500),
    ]
    assert cliente.get(f"/api/produtos/{criado['id']}").json()["descricao"].endswith("alterado")
    assert cliente.get("/api/produtos/999").status_code == 404
    assert "Picolés" in cliente.get("/api/produtos/categorias").json()
    assert len(cliente.get("/api/produtos", params={"busca": "picolés"}).json()) == 2


def test_produto_inativo_some_da_lista_e_libera_o_codigo_de_barras(cliente):
    produto = _produto(cliente, ean="7890000000017").json()
    dados = {"codigo": produto["codigo"], "descricao": produto["descricao"], "ean": produto["ean"]}
    inativo = cliente.put(f"/api/produtos/{produto['id']}", json={**dados, "ativo": False})
    assert inativo.status_code == 200 and inativo.json()["ativo"] is False
    assert cliente.get("/api/produtos").json() == []
    assert len(cliente.get("/api/produtos", params={"inativos": True}).json()) == 1
    assert _produto(cliente, ean="7890000000017").status_code == 201  # o código ficou livre


# ---------------------------------------------------------------- tabelas e formas


def test_tabelas_de_preco(cliente):
    primeira = cliente.post("/api/tabelas-preco", json={"nome": " varejo "}).json()
    assert (primeira["nome"], primeira["padrao"]) == ("VAREJO", True)  # a primeira vira padrão
    atacado = cliente.post("/api/tabelas-preco", json={"nome": "Atacado"}).json()
    assert atacado["padrao"] is False
    assert cliente.post("/api/tabelas-preco", json={"nome": "ATACADO"}).status_code == 409
    assert cliente.post("/api/tabelas-preco", json={"nome": "  "}).status_code == 422

    def alterar(tabela, **mudancas):
        corpo = {"nome": tabela["nome"], "padrao": tabela["padrao"], "ativo": tabela["ativo"]}
        return cliente.put(f"/api/tabelas-preco/{tabela['id']}", json={**corpo, **mudancas})

    assert alterar(primeira, ativo=False).status_code == 409  # a padrão não fica inativa
    assert alterar(primeira, padrao=False).status_code == 409  # nem deixa de ser padrão sozinha
    assert alterar(atacado, nome="varejo").status_code == 409
    assert alterar(atacado, nome="Revenda", padrao=True).json() == {
        "id": atacado["id"],
        "nome": "REVENDA",
        "padrao": True,
        "ativo": True,
    }
    tabelas = {t["nome"]: t for t in cliente.get("/api/tabelas-preco").json()}
    assert tabelas["VAREJO"]["padrao"] is False  # só uma padrão por vez
    assert alterar(tabelas["VAREJO"], ativo=False).status_code == 200
    assert [t["nome"] for t in cliente.get("/api/tabelas-preco").json()] == ["REVENDA"]
    assert len(cliente.get("/api/tabelas-preco", params={"todas": True}).json()) == 2


def test_formas_de_pagamento(cliente, caixa):
    formas = cliente.get("/api/formas-pagamento").json()
    assert [(f["forma"], f["ajuste_bp"], f["ativo"]) for f in formas] == [
        ("dinheiro", 0, True),
        ("pix", 0, True),
        ("debito", 0, True),
        ("credito", 0, True),
    ]
    pix = cliente.put("/api/formas-pagamento/pix", json={"ajuste_bp": -500, "ativo": True})
    assert pix.status_code == 200 and pix.json()["ajuste_bp"] == -500
    assert (
        cliente.put(
            "/api/formas-pagamento/credito", json={"ajuste_bp": 5001, "ativo": True}
        ).status_code
        == 422
    )
    # O operador comum consulta (precisa para vender), mas não altera.
    assert caixa.get("/api/formas-pagamento").json()[1]["ajuste_bp"] == -500
    assert (
        caixa.put("/api/formas-pagamento/pix", json={"ajuste_bp": 0, "ativo": True}).status_code
        == 403
    )
    for forma in ("dinheiro", "pix", "debito"):
        resposta = cliente.put(
            f"/api/formas-pagamento/{forma}", json={"ajuste_bp": 0, "ativo": False}
        )
        assert resposta.status_code == 200
    ultima = cliente.put("/api/formas-pagamento/credito", json={"ajuste_bp": 0, "ativo": False})
    assert ultima.status_code == 409 and "Pelo menos uma" in ultima.json()["detail"]


def test_pesquisa_ignora_acentos_e_maiusculas(cliente):
    """No caixa ninguém digita acento: "agua" acha "Água" e "joao" acha "João"."""
    from app.pesquisa import sem_acento

    assert sem_acento("Água de CÔCO com Limão") == "agua de coco com limao"
    assert sem_acento(None) == "" and sem_acento("") == ""

    for descricao in ("Banana de teste", "Água de teste", "açaí de teste"):
        assert _produto(cliente, descricao=descricao, categoria="Geladíssimos").status_code == 201

    def produtos(texto=None):
        filtro = {"busca": texto} if texto else {}
        return [p["descricao"] for p in cliente.get("/api/produtos", params=filtro).json()]

    assert produtos("agua") == ["Água de teste"]
    assert produtos("ÁGUA") == ["Água de teste"]
    assert produtos("acai") == ["açaí de teste"]
    assert len(produtos("geladissimos")) == 3  # pela categoria
    # A lista sai em ordem alfabética de verdade (o "Á" não vai para o fim).
    assert produtos() == ["açaí de teste", "Água de teste", "Banana de teste"]

    for nome in ("João de Teste", "Ângela de Teste"):
        assert cliente.post("/api/clientes", json={"nome": nome}).status_code == 201

    def clientes(texto=None):
        filtro = {"busca": texto} if texto else {}
        return [c["nome"] for c in cliente.get("/api/clientes", params=filtro).json()]

    assert clientes("joao") == ["João de Teste"]
    assert clientes("ANGELA") == ["Ângela de Teste"]
    assert clientes() == ["Ângela de Teste", "João de Teste"]


# ---------------------------------------------------------------- clientes


def test_cliente_com_cpf_ou_cnpj(cliente, loja):
    assert cliente.post("/api/clientes", json={"nome": " "}).status_code == 422
    invalido = cliente.post("/api/clientes", json={"nome": "Maria", "cpf_cnpj": "111.111.111-11"})
    assert invalido.status_code == 422 and "inválido" in invalido.json()["detail"]

    maria = cliente.post("/api/clientes", json={"nome": "Maria de Teste", "cpf_cnpj": CPF}).json()
    assert (maria["cpf_cnpj"], maria["documento"], maria["tipo_pessoa"]) == (
        "52998224725",
        CPF,
        "cpf",
    )
    mercado = cliente.post(
        "/api/clientes",
        json={"nome": "Mercado de Teste", "cpf_cnpj": CNPJ, "tabela_id": loja["atacado"]},
    ).json()
    assert (mercado["tipo_pessoa"], mercado["tabela_nome"]) == ("cnpj", "ATACADO")
    com_letras = cliente.post(
        "/api/clientes", json={"nome": "Empresa Nova de Teste", "cpf_cnpj": "12.abc.345/01de-35"}
    ).json()
    assert com_letras["documento"] == "12.ABC.345/01DE-35"

    repetido = cliente.post("/api/clientes", json={"nome": "Outra Maria", "cpf_cnpj": CPF})
    assert repetido.status_code == 409 and "Maria de Teste" in repetido.json()["detail"]

    def buscar(texto):
        return [c["nome"] for c in cliente.get("/api/clientes", params={"busca": texto}).json()]

    assert buscar("mercado") == ["Mercado de Teste"]
    assert buscar("529.982") == ["Maria de Teste"]  # pelo documento, com ou sem pontuação
    assert buscar("11222333") == ["Mercado de Teste"]
    assert buscar("ninguém") == []


def test_tabela_e_situacao_do_cliente_sao_do_gerente(cliente, caixa, loja):
    assert caixa.get("/api/sessao").json()["operador"]["login"] == OPERADOR["login"]
    recusado = caixa.post(
        "/api/clientes", json={"nome": "Amigo do Caixa", "tabela_id": loja["atacado"]}
    )
    assert recusado.status_code == 403 and "Só o gerente" in recusado.json()["detail"]
    criado = caixa.post("/api/clientes", json={"nome": "Cliente do Balcão"}).json()

    def alterar(quem, **mudancas):
        corpo = {"nome": criado["nome"], "tabela_id": None, "ativo": True, **mudancas}
        return quem.put(f"/api/clientes/{criado['id']}", json=corpo)

    assert alterar(caixa, telefone="(21) 99999-0000").json()["telefone"] == "(21) 99999-0000"
    assert alterar(caixa, tabela_id=loja["atacado"]).status_code == 403
    assert alterar(caixa, ativo=False).status_code == 403
    assert alterar(cliente, tabela_id=loja["atacado"]).json()["tabela_nome"] == "ATACADO"
    assert alterar(cliente, tabela_id=loja["atacado"], ativo=False).json()["ativo"] is False
    assert cliente.get("/api/clientes").json() == []
    assert len(cliente.get("/api/clientes", params={"inativos": True}).json()) == 1
    assert cliente.put("/api/clientes/999", json={"nome": "x"}).status_code == 404

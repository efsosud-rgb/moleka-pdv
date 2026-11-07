def test_status_sem_nada_configurado_e_honesto(cliente):
    r = cliente.get("/api/status")
    assert r.status_code == 200
    s = r.json()
    assert s["app"] == "Moleka PDV"
    assert s["banco"]["ok"] is True
    for chave in ("fiscal", "certificado", "impressora_cupom", "impressora_a4", "caixa"):
        assert s[chave]["ok"] is False, chave
        assert s[chave]["motivo"], f"{chave} precisa dizer o motivo"
    assert "não configurado" in s["fiscal"]["motivo"]
    assert s["caixa"]["motivo"] == "nenhum caixa aberto"


def test_interface_e_marca_sao_servidas(cliente):
    assert cliente.get("/").status_code == 200
    assert "Moleka" in cliente.get("/").text
    for pagina in (
        "inicio.html",
        "caixa.html",
        "financeiro.html",
        "css/moleka.css",
        "js/moleka.js",
    ):
        assert cliente.get(f"/{pagina}").status_code == 200, pagina
    assert cliente.get("/assets/brand/mascote.png").headers["content-type"] == "image/png"


def test_cadastro_de_tabela_produto_e_cliente(cliente):
    varejo = cliente.post("/api/tabelas-preco", json={"nome": "varejo", "padrao": True})
    assert varejo.status_code == 201 and varejo.json()["nome"] == "VAREJO"
    atacado = cliente.post("/api/tabelas-preco", json={"nome": "Atacado"})
    assert atacado.status_code == 201
    assert cliente.post("/api/tabelas-preco", json={"nome": "VAREJO"}).status_code == 409

    produto = cliente.post(
        "/api/produtos",
        json={
            "codigo": "PIC-MANGA",
            "descricao": "Picolé de fruta — Manga",
            "ean": "7891000000021",
            "ncm": "21050010",
            "precos": [
                {"tabela_id": varejo.json()["id"], "qtd_min": "1", "preco_centavos": 500},
                {"tabela_id": varejo.json()["id"], "qtd_min": "10", "preco_centavos": 450},
                {"tabela_id": atacado.json()["id"], "qtd_min": "1", "preco_centavos": 400},
            ],
        },
    )
    assert produto.status_code == 201, produto.text
    assert len(produto.json()["precos"]) == 3
    assert (
        cliente.post("/api/produtos", json={"codigo": "PIC-MANGA", "descricao": "x"}).status_code
        == 409
    )
    assert (
        cliente.post(
            "/api/produtos",
            json={
                "codigo": "X",
                "descricao": "x",
                "precos": [{"tabela_id": 999, "preco_centavos": 1}],
            },
        ).status_code
        == 422
    )

    assert len(cliente.get("/api/produtos", params={"busca": "manga"}).json()) == 1
    assert cliente.get("/api/produtos", params={"busca": "nada"}).json() == []

    c = cliente.post("/api/clientes", json={"nome": "  Maria  ", "tabela_id": atacado.json()["id"]})
    assert c.status_code == 201 and c.json()["nome"] == "Maria"
    assert cliente.post("/api/clientes", json={"nome": "João", "tabela_id": 999}).status_code == 422
    assert [x["nome"] for x in cliente.get("/api/clientes").json()] == ["Maria"]

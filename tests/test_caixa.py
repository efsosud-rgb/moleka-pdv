"""Controle de caixa: abrir, sangria, suprimento, totais e fechamento com conferência."""

import pytest


def _vender(cliente, produto_id, quantidade, forma, valor=None):
    """Faz uma venda inteira de um produto e paga numa forma só."""
    item = cliente.post(
        "/api/venda/itens", json={"produto_id": produto_id, "quantidade": quantidade}
    )
    assert item.status_code == 201, item.text
    pago = cliente.post("/api/venda/pagamentos", json={"forma": forma, "valor_centavos": valor})
    assert pago.status_code == 201, pago.text
    final = cliente.post("/api/venda/finalizar", json={"emitir_nfce": False})
    assert final.status_code == 200, final.text
    return final.json()["venda"]


def test_abrir_o_caixa(cliente):
    assert cliente.get("/api/caixa").json() == {"aberto": False, "sessao": None}
    assert cliente.get("/api/status").json()["caixa"]["ok"] is False
    assert cliente.post("/api/caixa/abrir", json={"fundo_troco_centavos": -1}).status_code == 422

    aberto = cliente.post("/api/caixa/abrir", json={"fundo_troco_centavos": 15000})
    assert aberto.status_code == 201
    sessao = aberto.json()["sessao"]
    assert (sessao["caixa"], sessao["operador"]) == ("Caixa 01", "Gerente de Teste")
    assert sessao["fundo_troco_centavos"] == sessao["dinheiro_esperado_centavos"] == 15000
    assert sessao["vendas_quantidade"] == 0 and sessao["fechado_em"] is None

    de_novo = cliente.post("/api/caixa/abrir", json={"fundo_troco_centavos": 0})
    assert de_novo.status_code == 409 and "já está aberto" in de_novo.json()["detail"]
    indicador = cliente.get("/api/status").json()["caixa"]
    assert indicador["ok"] is True and indicador["texto"].startswith("Caixa 01 · aberto ")


def test_sangria_e_suprimento(cliente, loja):
    def mover(tipo, valor, motivo="motivo de teste"):
        return cliente.post(
            "/api/caixa/movimentos", json={"tipo": tipo, "valor_centavos": valor, "motivo": motivo}
        )

    assert mover("sangria", 0).status_code == 422
    sem_motivo = mover("suprimento", 5000, "  ")
    assert sem_motivo.status_code == 422 and "motivo" in sem_motivo.json()["detail"]
    demais = mover("sangria", 10001)  # só há o fundo de 100,00 na gaveta
    assert demais.status_code == 422 and "maior que o dinheiro" in demais.json()["detail"]

    sessao = mover("suprimento", 5000, "troco trazido do banco").json()["sessao"]
    assert sessao["suprimentos_centavos"] == 5000
    sessao = mover("sangria", 12000, "pagamento do fornecedor").json()["sessao"]
    assert sessao["sangrias_centavos"] == 12000
    assert sessao["dinheiro_esperado_centavos"] == 10000 + 5000 - 12000
    assert [m["tipo"] for m in sessao["movimentos"]] == ["suprimento", "sangria"]
    assert "(Gerente de Teste)" in sessao["movimentos"][0]["motivo"]  # fica o nome de quem fez


def test_totais_e_fechamento_com_conferencia(cliente, caixa, loja):
    _vender(cliente, loja["picole"], 4, "dinheiro", 5000)  # 20,00 em dinheiro (troco de 30,00)
    _vender(cliente, loja["agua"], 2, "pix")  # 6,00 no Pix
    _vender(caixa, loja["agua"], 1, "credito")  # 3,00 no crédito, vendido pelo operador comum
    cliente.post(
        "/api/caixa/movimentos",
        json={"tipo": "sangria", "valor_centavos": 2500, "motivo": "troco para a padaria"},
    )
    sessao = cliente.get("/api/caixa").json()["sessao"]
    assert (sessao["vendas_quantidade"], sessao["vendas_total_centavos"]) == (3, 2900)
    esperado = {f["forma"]: f["esperado_centavos"] for f in sessao["formas"]}
    assert esperado == {"dinheiro": 10000 + 2000 - 2500, "pix": 600, "debito": 0, "credito": 300}

    # Com venda aberta, o caixa não fecha.
    cliente.post("/api/venda/itens", json={"produto_id": loja["agua"]})
    contado = {"dinheiro": 9400, "pix": 600, "debito": 0, "credito": 300}
    preso = cliente.post("/api/caixa/fechar", json={"contado": contado})
    assert preso.status_code == 409 and "está aberta" in preso.json()["detail"]
    assert cliente.post("/api/venda/cancelar", json={}).status_code == 200

    fechado = caixa.post(
        "/api/caixa/fechar", json={"contado": contado, "observacao": " faltaram 1,00 "}
    )
    assert fechado.status_code == 200, fechado.text
    corpo = fechado.json()
    assert corpo["fechado_por"] == "Caixa de Teste" and corpo["observacao"] == "faltaram 1,00"
    diferencas = {f["forma"]: f["diferenca_centavos"] for f in corpo["formas"]}
    assert diferencas == {"dinheiro": -100, "pix": 0, "debito": 0, "credito": 0}
    assert cliente.get("/api/caixa").json()["aberto"] is False
    assert cliente.post("/api/caixa/fechar", json={"contado": contado}).status_code == 409
    assert cliente.post("/api/venda/itens", json={"produto_id": loja["agua"]}).status_code == 409

    historico = cliente.get("/api/caixa/historico")
    assert historico.status_code == 200 and len(historico.json()) == 1
    assert historico.json()[0]["formas"][0]["contado_centavos"] == 9400
    assert caixa.get("/api/caixa/historico").status_code == 403  # histórico é do gerente
    # Dá para abrir de novo, e a sessão nova começa zerada.
    nova = cliente.post("/api/caixa/abrir", json={"fundo_troco_centavos": 5000}).json()["sessao"]
    assert (nova["vendas_quantidade"], nova["dinheiro_esperado_centavos"]) == (0, 5000)


@pytest.mark.parametrize("caminho", ["/api/caixa", "/api/caixa/historico", "/api/venda"])
def test_caixa_e_venda_exigem_login(anonimo, caminho):
    assert anonimo.get(caminho).status_code == 401

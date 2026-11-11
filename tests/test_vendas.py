"""A venda no caixa: preços, quantidades, cliente, desconto, pagamentos e encerramento."""

from decimal import Decimal

import pytest
from sqlalchemy import select

from app import db, vendas
from app.models import MovimentoEstoque


def _item(cliente, **dados):
    return cliente.post("/api/venda/itens", json=dados)


def _venda(cliente):
    return cliente.get("/api/venda").json()["venda"]


def _pagar(cliente, forma, valor=None):
    return cliente.post("/api/venda/pagamentos", json={"forma": forma, "valor_centavos": valor})


def _ajustar_formas(cliente, **percentuais):
    """Ex.: _ajustar_formas(cliente, pix=-500, credito=300) = Pix -5% e crédito +3%."""
    for forma, bp in percentuais.items():
        resposta = cliente.put(
            f"/api/formas-pagamento/{forma}", json={"ajuste_bp": bp, "ativo": True}
        )
        assert resposta.status_code == 200, resposta.text


# ---------------------------------------------------------------- itens e preços


def test_sem_caixa_aberto_nao_vende(cliente):
    assert cliente.get("/api/venda").json()["caixa_aberto"] is False
    resposta = _item(cliente, codigo="1")
    assert resposta.status_code == 409 and "caixa está fechado" in resposta.json()["detail"]


def test_item_por_codigo_e_por_codigo_de_barras_com_faixa_por_quantidade(cliente, loja):
    assert cliente.get("/api/venda").json() == {
        "caixa_aberto": True,
        "venda": None,
        "nfce_disponivel": False,
        "nfce_motivo": cliente.get("/api/status").json()["fiscal"]["motivo"],
        "aviso": None,
    }
    venda = _item(cliente, codigo="7890000000017", quantidade=4).json()["venda"]  # pelo leitor
    assert (venda["numero"], venda["status"], venda["tabela"]) == (1, "aberta", "VAREJO")
    assert venda["operador"] == "Gerente de Teste" and venda["cliente"] is None
    venda = _item(cliente, codigo="1", quantidade="5").json()["venda"]  # o mesmo, pelo código
    assert len(venda["itens"]) == 1  # repetido soma na mesma linha
    item = venda["itens"][0]
    assert (float(item["quantidade"]), item["preco_unitario_centavos"], item["total_centavos"]) == (
        9.0,
        500,
        4500,
    )
    # Ao chegar a 10, o preço unitário muda sozinho para o da faixa.
    item = _item(cliente, produto_id=loja["picole"]).json()["venda"]["itens"][0]
    assert (float(item["quantidade"]), item["preco_unitario_centavos"], item["total_centavos"]) == (
        10.0,
        450,
        4500,
    )
    assert float(item["faixa_qtd_min"]) == 10.0
    assert _item(cliente, codigo="não existe").status_code == 404


def test_editar_quantidade_e_remover_item(cliente, loja):
    venda = _item(cliente, produto_id=loja["picole"], quantidade=12).json()["venda"]
    picole = venda["itens"][0]["id"]
    venda = cliente.put(f"/api/venda/itens/{picole}", json={"quantidade": "3"}).json()["venda"]
    assert venda["itens"][0]["total_centavos"] == 1500  # voltou para o preço de 1 a 9
    assert cliente.put(f"/api/venda/itens/{picole}", json={"quantidade": 0}).status_code == 422
    inteiro = cliente.put(f"/api/venda/itens/{picole}", json={"quantidade": "1,5"})
    assert inteiro.status_code == 422 and "unidade inteira" in inteiro.json()["detail"]
    assert cliente.put("/api/venda/itens/999", json={"quantidade": 1}).status_code == 404

    # Produto por quilo aceita casas decimais: 0,350 kg x 59,90 = 20,965 -> 20,97.
    venda = _item(cliente, produto_id=loja["sorvete"], quantidade="0,350").json()["venda"]
    sorvete = venda["itens"][1]
    assert (sorvete["unidade"], sorvete["total_centavos"]) == ("KG", 2097)
    assert venda["subtotal_centavos"] == 1500 + 2097

    venda = cliente.delete(f"/api/venda/itens/{picole}").json()["venda"]
    assert [i["codigo"] for i in venda["itens"]] == ["2"]
    assert venda["subtotal_centavos"] == venda["total_centavos"] == 2097


def test_cliente_troca_a_tabela_e_recalcula_os_precos(cliente, loja):
    atacadista = cliente.post(
        "/api/clientes", json={"nome": "Mercado de Teste", "tabela_id": loja["atacado"]}
    ).json()
    comum = cliente.post("/api/clientes", json={"nome": "Maria de Teste"}).json()
    _item(cliente, produto_id=loja["picole"], quantidade=2)
    _item(cliente, produto_id=loja["agua"], quantidade=1)
    _pagar(cliente, "pix", 500)

    estado = cliente.put("/api/venda/cliente", json={"cliente_id": atacadista["id"]}).json()
    venda = estado["venda"]
    assert venda["cliente"]["nome"] == "Mercado de Teste" and venda["tabela"] == "ATACADO"
    # Picolé no preço de atacado (4,00); a água não tem preço no atacado e fica no varejo.
    assert [i["preco_unitario_centavos"] for i in venda["itens"]] == [400, 300]
    assert venda["subtotal_centavos"] == 1100
    assert "recalculados pela tabela ATACADO" in estado["aviso"]
    assert venda["pagamentos"] == [] and "pagamentos foram desfeitos" in estado["aviso"]

    # Trocar por um cliente sem tabela própria volta para o varejo.
    estado = cliente.put("/api/venda/cliente", json={"cliente_id": comum["id"]}).json()
    assert estado["venda"]["tabela"] == "VAREJO" and estado["venda"]["subtotal_centavos"] == 1300
    # Tirar o cliente (consumidor final) não muda o preço, então não há aviso.
    estado = cliente.put("/api/venda/cliente", json={"cliente_id": None}).json()
    assert estado["venda"]["cliente"] is None and estado["aviso"] is None
    assert cliente.put("/api/venda/cliente", json={"cliente_id": 999}).status_code == 404


def test_desconto_so_do_gerente(cliente, caixa, loja):
    _item(caixa, produto_id=loja["picole"], quantidade=4)  # 20,00, lançado pelo operador comum
    recusado = caixa.put("/api/venda/desconto", json={"centavos": 100})
    assert recusado.status_code == 403 and recusado.json()["detail"] == "Só o gerente dá desconto."

    venda = cliente.put("/api/venda/desconto", json={"centavos": 250}).json()["venda"]
    assert (venda["desconto_centavos"], venda["base_centavos"], venda["total_centavos"]) == (
        250,
        1750,
        1750,
    )
    venda = cliente.put("/api/venda/desconto", json={"percentual": "10"}).json()["venda"]
    assert venda["desconto_centavos"] == 200
    assert cliente.put("/api/venda/desconto", json={"centavos": 2001}).status_code == 422
    assert cliente.put("/api/venda/desconto", json={"percentual": 101}).status_code == 422
    assert (
        cliente.put("/api/venda/desconto", json={"centavos": 0}).json()["venda"][
            "desconto_centavos"
        ]
        == 0
    )


# ---------------------------------------------------------------- pagamentos


def test_uma_forma_com_desconto_percentual(cliente, loja):
    _ajustar_formas(cliente, pix=-500)
    venda = _item(cliente, produto_id=loja["picole"], quantidade=20).json()["venda"]  # 90,00
    a_pagar = {f["forma"]: f["a_pagar_centavos"] for f in venda["formas"]}
    assert a_pagar == {"dinheiro": 9000, "pix": 8550, "debito": 9000, "credito": 9000}
    assert venda["pode_finalizar"] is False

    venda = _pagar(cliente, "pix").json()["venda"]  # sem valor = todo o restante no Pix
    assert venda["pagamentos"][0]["valor_centavos"] == 8550
    assert venda["pagamentos"][0]["ajuste_centavos"] == -450
    assert (venda["restante_centavos"], venda["total_centavos"]) == (0, 8550)
    assert venda["pode_finalizar"] is True
    quitado = _pagar(cliente, "dinheiro", 100)
    assert quitado.status_code == 422 and "já está toda paga" in quitado.json()["detail"]


def test_duas_formas_o_percentual_vale_so_sobre_a_parte_de_cada_uma(cliente, loja):
    """Pedido do Eric: parte no débito e parte no crédito, cada parte com a sua regra."""
    _ajustar_formas(cliente, pix=-500, credito=300)
    _item(cliente, produto_id=loja["picole"], quantidade=20)  # 90,00
    _item(cliente, produto_id=loja["agua"], quantidade=1)  # 3,00 -> base de 93,00

    venda = _pagar(cliente, "debito", 4000).json()["venda"]  # 40,00 no débito, sem ajuste
    assert venda["restante_centavos"] == 5300
    credito = next(f for f in venda["formas"] if f["forma"] == "credito")
    assert credito["a_pagar_centavos"] == 5300 + 159  # 3% só sobre os 53,00 que faltam

    venda = _pagar(cliente, "credito", 3090).json()["venda"]  # 30,90 no crédito quitam 30,00
    assert venda["pagamentos"][1]["ajuste_centavos"] == 90
    assert venda["restante_centavos"] == 2300

    venda = _pagar(cliente, "pix").json()["venda"]  # o resto no Pix: 23,00 - 5% = 21,85
    assert venda["pagamentos"][2]["valor_centavos"] == 2185
    assert venda["restante_centavos"] == 0 and venda["pode_finalizar"] is True
    assert venda["ajuste_pagamento_centavos"] == 90 - 115
    assert venda["total_centavos"] == 4000 + 3090 + 2185 == 9300 + 90 - 115


def test_dinheiro_tem_troco_e_cartao_nao(cliente, loja):
    _item(cliente, produto_id=loja["picole"], quantidade=3)  # 15,00
    passou = _pagar(cliente, "debito", 2000)
    assert passou.status_code == 422 and "Só o dinheiro tem troco" in passou.json()["detail"]
    assert _pagar(cliente, "pix", 0).status_code == 422

    venda = _pagar(cliente, "pix", 500).json()["venda"]
    venda = _pagar(cliente, "dinheiro", 5000).json()["venda"]  # faltavam 10,00; deu 50,00
    assert venda["pagamentos"][1]["valor_centavos"] == 1000  # só o que ficou no caixa
    assert venda["pagamentos"][1]["troco_centavos"] == venda["troco_centavos"] == 4000
    assert venda["total_centavos"] == 1500 and venda["pode_finalizar"] is True


def test_trocar_a_forma_depois_de_escolhida_e_remover_pagamento(cliente, loja):
    _ajustar_formas(cliente, pix=-500, credito=300)
    _item(cliente, produto_id=loja["picole"], quantidade=20)  # 90,00
    venda = _pagar(cliente, "debito", 4000).json()["venda"]
    debito = venda["pagamentos"][0]["id"]

    # Era débito, o cliente resolveu pagar no Pix: a parte quitada (40,00) continua a mesma.
    venda = cliente.put(f"/api/venda/pagamentos/{debito}", json={"forma": "pix"}).json()["venda"]
    pagamento = venda["pagamentos"][0]
    assert (pagamento["forma"], pagamento["valor_centavos"], pagamento["ajuste_centavos"]) == (
        "pix",
        3800,
        -200,
    )
    assert venda["restante_centavos"] == 5000
    venda = cliente.put(f"/api/venda/pagamentos/{debito}", json={"forma": "credito"}).json()[
        "venda"
    ]
    assert venda["pagamentos"][0]["valor_centavos"] == 4120

    venda = cliente.delete(f"/api/venda/pagamentos/{debito}").json()["venda"]
    assert venda["pagamentos"] == [] and venda["restante_centavos"] == 9000
    assert cliente.delete("/api/venda/pagamentos/999").status_code == 404

    # Mexer nos itens depois de pagar desfaz os pagamentos (os valores mudam).
    _pagar(cliente, "dinheiro")
    venda = _item(cliente, produto_id=loja["agua"]).json()["venda"]
    assert venda["pagamentos"] == [] and venda["restante_centavos"] == 9300


def test_forma_desativada_nao_recebe(cliente, loja):
    cliente.put("/api/formas-pagamento/credito", json={"ajuste_bp": 0, "ativo": False})
    _item(cliente, produto_id=loja["agua"])
    recusado = _pagar(cliente, "credito")
    assert recusado.status_code == 422 and "desativada" in recusado.json()["detail"]


@pytest.mark.parametrize("bp", [-5000, -1234, -500, -1, 0, 1, 250, 333, 4999, 5000])
@pytest.mark.parametrize("base", [1, 7, 99, 100, 1999, 9300, 123457])
def test_contas_do_percentual_nunca_perdem_nem_criam_centavos(base, bp):
    """Pagar uma parte e depois o resto na mesma forma quita exatamente a base."""
    inteiro = base + vendas.ajuste_sobre(base, bp)
    for parte in {1, inteiro // 3, inteiro // 2, inteiro - 1}:
        if not 0 < parte < inteiro:
            continue
        quita = min(vendas.base_de_um_valor(parte, bp), base)
        resto = base - quita
        segundo = resto + vendas.ajuste_sobre(resto, bp)
        assert quita + resto == base
        assert 0 <= quita <= base
        assert abs((parte + segundo) - inteiro) <= 1  # no máximo 1 centavo de arredondamento


# ---------------------------------------------------------------- encerrar


def test_finalizar_baixa_o_estoque_e_soma_no_dia(cliente, loja):
    assert cliente.get("/api/vendas/resumo-hoje").json() == {
        "dia": cliente.get("/api/vendas/resumo-hoje").json()["dia"],
        "quantidade": 0,
        "total_centavos": None,  # sem venda, a tela mostra "—" e o motivo
        "ticket_medio_centavos": None,
        "recebido": {},
        "motivo": "sem vendas finalizadas hoje",
    }
    assert cliente.post("/api/venda/finalizar", json={}).status_code == 409  # não há venda

    _item(cliente, produto_id=loja["picole"], quantidade=3)
    _item(cliente, produto_id=loja["sorvete"], quantidade="0.5")  # 29,95
    falta = cliente.post("/api/venda/finalizar", json={})
    assert falta.status_code == 422 and "Ainda falta pagar R$ 44,95" in falta.json()["detail"]
    _pagar(cliente, "dinheiro", 5000)
    com_nota = cliente.post("/api/venda/finalizar", json={"emitir_nfce": True})
    assert (
        com_nota.status_code == 409
        and "NFC-e ainda não pode ser emitida" in com_nota.json()["detail"]
    )

    final = cliente.post("/api/venda/finalizar", json={"emitir_nfce": False}).json()["venda"]
    assert (final["status"], final["quer_nfce"], final["total_centavos"]) == (
        "finalizada",
        False,
        4495,
    )
    assert final["troco_centavos"] == 505 and final["finalizada_em"] is not None
    assert cliente.get("/api/venda").json()["venda"] is None  # o caixa fica livre para a próxima

    with db.nova_sessao() as sessao:
        baixas = sessao.scalars(select(MovimentoEstoque).order_by(MovimentoEstoque.id)).all()
        assert [(m.produto_id, Decimal(m.quantidade), m.tipo.value) for m in baixas] == [
            (loja["picole"], Decimal("-3"), "venda"),
            (loja["sorvete"], Decimal("-0.5"), "venda"),
        ]
        assert baixas[0].referencia == f"venda:{final['id']}"

    _item(cliente, produto_id=loja["agua"], quantidade=2)
    _pagar(cliente, "pix")
    cliente.post("/api/venda/finalizar", json={})
    resumo = cliente.get("/api/vendas/resumo-hoje").json()
    assert (resumo["quantidade"], resumo["total_centavos"]) == (2, 4495 + 600)
    assert resumo["ticket_medio_centavos"] == 2548  # 50,95 / 2 = 25,475 -> 25,48
    assert resumo["recebido"] == {"dinheiro": 4495, "pix": 600} and resumo["motivo"] == ""
    assert [v["numero"] for v in cliente.get("/api/vendas").json()] == [2, 1]


def test_cancelar_venda_aberta(caixa, loja):
    _item(caixa, produto_id=loja["agua"])
    cancelada = caixa.post("/api/venda/cancelar", json={"motivo": "cliente desistiu"})
    assert cancelada.status_code == 200
    venda = cancelada.json()["venda"]
    assert (venda["status"], venda["motivo_cancelamento"]) == ("cancelada", "cliente desistiu")
    assert caixa.get("/api/venda").json()["venda"] is None
    assert caixa.get("/api/vendas/resumo-hoje").json()["quantidade"] == 0
    nova = _item(caixa, produto_id=loja["agua"]).json()["venda"]
    assert nova["numero"] == 2  # o número da cancelada não é reaproveitado
    with db.nova_sessao() as sessao:
        assert sessao.scalars(select(MovimentoEstoque)).all() == []  # nada saiu do estoque


def test_cancelar_venda_finalizada_e_do_gerente_e_estorna(cliente, caixa, loja):
    _item(caixa, produto_id=loja["picole"], quantidade=2)
    _pagar(caixa, "dinheiro")
    venda = caixa.post("/api/venda/finalizar", json={}).json()["venda"]
    caminho = f"/api/vendas/{venda['id']}/cancelar"

    assert caixa.post(caminho, json={"motivo": "engano"}).status_code == 403
    sem_motivo = cliente.post(caminho, json={"motivo": " "})
    assert sem_motivo.status_code == 422 and "motivo" in sem_motivo.json()["detail"]
    cancelada = cliente.post(caminho, json={"motivo": "produto devolvido"})
    assert cancelada.status_code == 200 and cancelada.json()["status"] == "cancelada"
    assert cliente.post(caminho, json={"motivo": "de novo"}).status_code == 409
    assert cliente.post("/api/vendas/999/cancelar", json={"motivo": "x"}).status_code == 404

    assert cliente.get("/api/vendas/resumo-hoje").json()["quantidade"] == 0
    sessao_caixa = cliente.get("/api/caixa").json()["sessao"]
    assert sessao_caixa["vendas_total_centavos"] == 0
    assert sessao_caixa["dinheiro_esperado_centavos"] == 10000  # só o fundo de troco
    with db.nova_sessao() as sessao:
        saldo = sum(Decimal(m.quantidade) for m in sessao.scalars(select(MovimentoEstoque)))
        assert saldo == 0  # a baixa da venda e o estorno do cancelamento se anulam


def test_produto_sem_preco_ou_inativo_nao_entra_na_venda(cliente, loja):
    sem_preco = cliente.post("/api/produtos", json={"descricao": "Brinde de teste"}).json()
    recusado = _item(cliente, produto_id=sem_preco["id"])
    assert recusado.status_code == 422 and "está sem preço" in recusado.json()["detail"]
    assert cliente.get("/api/venda").json()["venda"] is None  # nem chega a abrir venda vazia
    agua = cliente.get(f"/api/produtos/{loja['agua']}").json()
    cliente.put(f"/api/produtos/{loja['agua']}", json={**agua, "ativo": False})
    inativo = _item(cliente, produto_id=loja["agua"])
    assert inativo.status_code == 422 and "inativo" in inativo.json()["detail"]
    assert _item(cliente, codigo="3").status_code == 404  # pelo código, inativo nem é achado

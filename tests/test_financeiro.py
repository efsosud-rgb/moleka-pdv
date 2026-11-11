"""Financeiro: categorias, lançamentos, fluxo de caixa, DRE e rentabilidade.

Todos os valores esperados estão calculados à mão nos comentários.
"""

from datetime import timedelta

from sqlalchemy import func, select

from app import db, financeiro, tempo
from app.api import financeiro as api_financeiro
from app.models import CategoriaFinanceira, Lancamento


def _categorias(cliente):
    """Cria o plano de contas inicial e devolve {nome: id}."""
    with db.nova_sessao() as sessao:
        financeiro.semear_categorias(sessao)
        sessao.commit()
    todas = cliente.get("/api/financeiro/categorias", params={"todas": True}).json()
    return {c["nome"]: c["id"] for c in todas}


def _lancar(cliente, tipo, categoria_id, descricao, valor, vencimento, **mais):
    dados = {
        "tipo": tipo,
        "categoria_id": categoria_id,
        "descricao": descricao,
        "valor_centavos": valor,
        "vencimento": vencimento.isoformat(),
    }
    for campo, conteudo in mais.items():
        dados[campo] = conteudo.isoformat() if hasattr(conteudo, "isoformat") else conteudo
    return cliente.post("/api/financeiro/lancamentos", json=dados)


def _lancado(cliente, *args, **mais):
    resposta = _lancar(cliente, *args, **mais)
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def _periodo(inicio, fim):
    return {"inicio": inicio.isoformat(), "fim": fim.isoformat()}


def _entrada(cliente, produto_id, quantidade, custo):
    resposta = cliente.post(
        "/api/estoque/ajustes",
        json={
            "produto_id": produto_id,
            "tipo": "entrada",
            "quantidade": quantidade,
            "motivo": "produção de teste",
            "custo_unitario_centavos": custo,
        },
    )
    assert resposta.status_code == 201, resposta.text


def _cancelar_venda(cliente, venda):
    resposta = cliente.post(f"/api/vendas/{venda['id']}/cancelar", json={"motivo": "teste"})
    assert resposta.status_code == 200, resposta.text


# ---------------------------------------------------------------- categorias


def test_plano_de_contas_inicial_e_so_de_nomes(cliente):
    db.semear_padroes()
    db.semear_padroes()  # chamar de novo não duplica nada
    categorias = cliente.get("/api/financeiro/categorias").json()
    assert len(categorias) == 17 == len(financeiro.CATEGORIAS_INICIAIS)
    nomes = [c["nome"] for c in categorias]
    assert nomes[:3] == ["Água", "Aluguel", "Aporte dos sócios e empréstimos"]  # alfabética
    por_nome = {c["nome"]: c for c in categorias}
    assert por_nome["Aluguel"]["grupo"] == "despesa_operacional"
    assert por_nome["Aluguel"]["grupo_rotulo"] == "Despesas operacionais"
    assert por_nome["Aluguel"]["serve_para"] == ["despesa"]
    assert por_nome["Outras receitas"]["serve_para"] == ["receita"]
    # Fora do resultado: as saídas (compra de mercadoria, retirada) só servem para despesa, e
    # as entradas (aporte, empréstimo) só para receita.
    assert por_nome["Retirada dos sócios"]["serve_para"] == ["despesa"]
    assert por_nome["Compra de mercadorias para revenda"]["serve_para"] == ["despesa"]
    assert por_nome["Aporte dos sócios e empréstimos"]["serve_para"] == ["receita"]
    with db.nova_sessao() as sessao:  # são só nomes: nenhum lançamento nasce junto
        assert sessao.scalar(select(func.count(Lancamento.id))) == 0
    grupos = cliente.get("/api/financeiro/grupos").json()
    assert [g["grupo"] for g in grupos] == [
        "receita_bruta",
        "deducao",
        "cmv",
        "despesa_operacional",
        "outras_receitas",
        "outras_despesas",
        "fora_do_dre",
        "entrada_fora_do_dre",
    ]


def test_cadastro_de_categorias(cliente):
    criar = cliente.post(
        "/api/financeiro/categorias",
        json={"nome": "  Marketing  e anúncios ", "grupo": "despesa_operacional"},
    )
    assert criar.status_code == 201, criar.text
    categoria = criar.json()
    assert (categoria["nome"], categoria["ativo"]) == ("Marketing e anúncios", True)

    repetida = cliente.post(
        "/api/financeiro/categorias", json={"nome": "marketing e anuncios", "grupo": "cmv"}
    )
    assert repetida.status_code == 409 and "Já existe" in repetida.json()["detail"]
    vazia = cliente.post("/api/financeiro/categorias", json={"nome": " ", "grupo": "cmv"})
    assert vazia.status_code == 422
    grupo_errado = cliente.post("/api/financeiro/categorias", json={"nome": "X", "grupo": "nenhum"})
    assert grupo_errado.status_code == 422

    caminho = f"/api/financeiro/categorias/{categoria['id']}"
    mudou = cliente.put(caminho, json={"nome": "Propaganda", "grupo": "outras_despesas"})
    assert mudou.status_code == 200 and mudou.json()["grupo"] == "outras_despesas"

    # Com lançamento, o grupo não muda mais (os relatórios antigos mudariam); o nome pode.
    _lancado(cliente, "despesa", categoria["id"], "Panfletos", 1000, tempo.hoje())
    travado = cliente.put(caminho, json={"nome": "Propaganda", "grupo": "despesa_operacional"})
    assert travado.status_code == 409 and "grupo não pode mudar" in travado.json()["detail"]
    assert (
        cliente.put(caminho, json={"nome": "Divulgação", "grupo": "outras_despesas"}).status_code
        == 200
    )

    inativa = cliente.put(
        caminho, json={"nome": "Divulgação", "grupo": "outras_despesas", "ativo": False}
    )
    assert inativa.status_code == 200 and inativa.json()["ativo"] is False
    assert cliente.get("/api/financeiro/categorias").json() == []
    assert len(cliente.get("/api/financeiro/categorias", params={"todas": True}).json()) == 1
    em_inativa = _lancar(cliente, "despesa", categoria["id"], "Outro panfleto", 500, tempo.hoje())
    assert em_inativa.status_code == 422 and "inativa" in em_inativa.json()["detail"]
    assert (
        cliente.put(
            "/api/financeiro/categorias/999", json={"nome": "X", "grupo": "cmv"}
        ).status_code
        == 404
    )


# ---------------------------------------------------------------- lançamentos


def test_lancamento_baixa_alteracao_e_cancelamento(cliente):
    cat = _categorias(cliente)
    hoje = tempo.hoje()
    periodo = _periodo(hoje - timedelta(days=40), hoje + timedelta(days=40))

    luz = _lancado(
        cliente,
        "despesa",
        cat["Energia elétrica"],
        " Conta de luz  de outubro ",
        35000,
        hoje + timedelta(days=5),
    )
    assert (luz["descricao"], luz["situacao"], luz["origem"]) == (
        "Conta de luz de outubro",
        "aberto",
        "manual",
    )
    assert luz["competencia"] == luz["vencimento"]  # sem competência informada, vale o vencimento
    assert (luz["pago_em"], luz["forma"], luz["categoria"]) == (None, None, "Energia elétrica")
    atrasada = _lancado(
        cliente,
        "receita",
        cat["Outras receitas"],
        "Aluguel do freezer",
        12000,
        hoje - timedelta(days=3),
    )
    assert atrasada["situacao"] == "vencido"
    # Vence hoje: ainda está em dia. Só fica vencido a partir de amanhã.
    de_hoje = _lancado(cliente, "despesa", cat["Água"], "Conta de água", 100, hoje)
    de_ontem = _lancado(
        cliente, "despesa", cat["Água"], "Conta de água", 100, hoje - timedelta(days=1)
    )
    assert (de_hoje["situacao"], de_ontem["situacao"]) == ("aberto", "vencido")
    for conta in (de_hoje, de_ontem):
        assert (
            cliente.post(f"/api/financeiro/lancamentos/{conta['id']}/cancelar").status_code == 200
        )

    lista = cliente.get("/api/financeiro/lancamentos", params=periodo).json()
    assert [i["descricao"] for i in lista["itens"]] == [
        "Aluguel do freezer",
        "Conta de luz de outubro",
    ]
    assert lista["totais"] == {
        "a_pagar": 35000,
        "a_receber": 12000,  # o vencido também está a receber
        "pago": 0,
        "recebido": 0,
        "vencido_a_pagar": 0,
        "vencido_a_receber": 12000,
    }

    caminho = f"/api/financeiro/lancamentos/{luz['id']}"
    futuro = cliente.post(f"{caminho}/baixa", json={"data": (hoje + timedelta(days=1)).isoformat()})
    assert futuro.status_code == 422 and "futuro" in futuro.json()["detail"]
    paga = cliente.post(f"{caminho}/baixa", json={"data": hoje.isoformat(), "forma": "pix"})
    assert paga.status_code == 200, paga.text
    assert (paga.json()["situacao"], paga.json()["pago_em"], paga.json()["forma_rotulo"]) == (
        "pago",
        hoje.isoformat(),
        "Pix",
    )
    assert cliente.post(f"{caminho}/baixa", json={"data": hoje.isoformat()}).status_code == 409
    totais = cliente.get("/api/financeiro/lancamentos", params=periodo).json()["totais"]
    assert (totais["a_pagar"], totais["pago"]) == (0, 35000)

    # Baixado não se altera nem se cancela: primeiro desfaz a baixa.
    novo = {
        "categoria_id": cat["Energia elétrica"],
        "descricao": "Conta de luz de outubro (corrigida)",
        "valor_centavos": 36000,
        "vencimento": (hoje + timedelta(days=6)).isoformat(),
        "competencia": (hoje - timedelta(days=20)).isoformat(),
    }
    assert cliente.put(caminho, json=novo).status_code == 409
    assert cliente.post(f"{caminho}/cancelar").status_code == 409
    desfeita = cliente.delete(f"{caminho}/baixa")
    assert desfeita.status_code == 200 and desfeita.json()["situacao"] == "aberto"
    assert (desfeita.json()["pago_em"], desfeita.json()["forma"]) == (None, None)
    assert cliente.delete(f"{caminho}/baixa").status_code == 409  # já não está baixado

    alterado = cliente.put(caminho, json=novo)
    assert alterado.status_code == 200, alterado.text
    assert (alterado.json()["valor_centavos"], alterado.json()["competencia"]) == (
        36000,
        (hoje - timedelta(days=20)).isoformat(),
    )

    cancelado = cliente.post(f"{caminho}/cancelar")
    assert cancelado.status_code == 200 and cancelado.json()["situacao"] == "cancelado"
    for pedido in (
        cliente.put(caminho, json=novo),
        cliente.post(f"{caminho}/baixa", json={"data": hoje.isoformat()}),
        cliente.post(f"{caminho}/cancelar"),
    ):
        assert pedido.status_code == 409 and "cancelado" in pedido.json()["detail"]
    # Cancelado não é apagado: sai da lista e dos totais, e aparece quando pedido.
    lista = cliente.get("/api/financeiro/lancamentos", params=periodo).json()
    assert [i["descricao"] for i in lista["itens"]] == ["Aluguel do freezer"]
    assert lista["totais"]["a_pagar"] == 0
    cancelados = cliente.get(
        "/api/financeiro/lancamentos", params={**periodo, "situacao": "cancelado"}
    )
    assert [i["id"] for i in cancelados.json()["itens"]] == [  # em ordem de vencimento
        de_ontem["id"],
        de_hoje["id"],
        luz["id"],
    ]
    with db.nova_sessao() as sessao:
        assert sessao.get(Lancamento, luz["id"]).cancelado_por_id is not None

    # Filtros: por tipo; e "vencido" traz os atrasados de qualquer data, fora do período também.
    so_despesas = cliente.get("/api/financeiro/lancamentos", params={**periodo, "tipo": "despesa"})
    assert so_despesas.json()["itens"] == []
    assert so_despesas.json()["motivo"] == "nenhum lançamento com este filtro"
    longe = _periodo(hoje + timedelta(days=100), hoje + timedelta(days=130))
    vencidos = cliente.get("/api/financeiro/lancamentos", params={**longe, "situacao": "vencido"})
    assert [i["descricao"] for i in vencidos.json()["itens"]] == ["Aluguel do freezer"]
    assert cliente.get("/api/financeiro/lancamentos", params=longe).json()["itens"] == []


def test_contas_em_aberto_fora_do_periodo(cliente, monkeypatch):
    """O que vence fora do período não aparece na lista, mas a resposta diz que existe (a tela
    avisa); "todas_em_aberto" traz tudo o que falta pagar ou receber, de qualquer data."""
    cat = _categorias(cliente)
    hoje = tempo.hoje()
    so_hoje = _periodo(hoje, hoje)
    _lancado(
        cliente, "despesa", cat["Aluguel"], "Aluguel atrasado", 100000, hoje - timedelta(days=10)
    )
    _lancado(cliente, "despesa", cat["Água"], "Conta de água", 9000, hoje)
    _lancado(
        cliente,
        "despesa",
        cat["Energia elétrica"],
        "Conta de luz",
        30000,
        hoje + timedelta(days=45),
    )
    _lancado(
        cliente,
        "receita",
        cat["Outras receitas"],
        "Aluguel do freezer",
        12000,
        hoje + timedelta(days=50),
    )
    # Paga e cancelada, as duas com vencimento fora do período: não são contas em aberto.
    _lancado(
        cliente,
        "despesa",
        cat["Água"],
        "Água do mês passado",
        8000,
        hoje - timedelta(days=30),
        pago_em=hoje,
        forma="pix",
    )
    cancelada = _lancado(
        cliente, "despesa", cat["Aluguel"], "Lançada por engano", 500, hoje + timedelta(days=20)
    )
    caminho = f"/api/financeiro/lancamentos/{cancelada['id']}/cancelar"
    assert cliente.post(caminho).status_code == 200

    def lista(**filtros):
        resposta = cliente.get("/api/financeiro/lancamentos", params={**so_hoje, **filtros})
        assert resposta.status_code == 200, resposta.text
        return resposta.json()

    do_dia = lista()
    assert [i["descricao"] for i in do_dia["itens"]] == ["Conta de água"]
    assert do_dia["em_aberto_fora_do_periodo"] == 3  # o atrasado, a luz e o freezer
    assert lista(tipo="receita")["itens"] == []
    assert lista(tipo="receita")["em_aberto_fora_do_periodo"] == 1
    assert lista(tipo="despesa", situacao="aberto")["em_aberto_fora_do_periodo"] == 2

    todas = lista(situacao="todas_em_aberto")
    assert [(i["descricao"], i["situacao"]) for i in todas["itens"]] == [  # ordem de vencimento
        ("Aluguel atrasado", "vencido"),
        ("Conta de água", "aberto"),
        ("Conta de luz", "aberto"),
        ("Aluguel do freezer", "aberto"),
    ]
    assert todas["em_aberto_fora_do_periodo"] == 0  # já estão todas na lista
    assert (
        todas["totais"]["a_pagar"],
        todas["totais"]["a_receber"],
        todas["totais"]["vencido_a_pagar"],
        todas["totais"]["pago"],
    ) == (139000, 12000, 100000, 0)
    so_receitas = lista(situacao="todas_em_aberto", tipo="receita")
    assert [i["descricao"] for i in so_receitas["itens"]] == ["Aluguel do freezer"]
    # Os outros filtros não falam de contas em aberto: sem aviso.
    for situacao in ("pago", "cancelado", "vencido"):
        assert lista(situacao=situacao)["em_aberto_fora_do_periodo"] == 0, situacao

    desconhecido = cliente.get(
        "/api/financeiro/lancamentos", params={**so_hoje, "situacao": "qualquer"}
    )
    assert desconhecido.status_code == 422 and "desconhecido" in desconhecido.json()["detail"]

    # Lista grande demais não vem cortada (os totais sairiam errados sem ninguém perceber).
    monkeypatch.setattr(api_financeiro, "LIMITE_DA_LISTA", 3)
    grande = cliente.get(
        "/api/financeiro/lancamentos", params={**so_hoje, "situacao": "todas_em_aberto"}
    )
    assert grande.status_code == 422 and "mais de 3 lançamentos" in grande.json()["detail"]
    assert len(lista()["itens"]) == 1  # a lista pequena continua saindo


def test_lancamento_ja_pago_e_recusas(cliente):
    cat = _categorias(cliente)
    hoje = tempo.hoje()
    pago = _lancado(
        cliente,
        "despesa",
        cat["Aluguel"],
        "Aluguel de novembro",
        150000,
        hoje,
        pago_em=hoje,
        forma="dinheiro",
    )
    assert (pago["situacao"], pago["pago_em"], pago["forma"]) == (
        "pago",
        hoje.isoformat(),
        "dinheiro",
    )

    def recusa(trecho, *args, **mais):
        resposta = _lancar(cliente, *args, **mais)
        assert resposta.status_code == 422, resposta.text
        assert trecho in resposta.json()["detail"], resposta.json()["detail"]

    recusa("maior que zero", "despesa", cat["Aluguel"], "Aluguel", 0, hoje)
    recusa("maior que zero", "despesa", cat["Aluguel"], "Aluguel", -100, hoje)
    recusa("descrição", "despesa", cat["Aluguel"], "   ", 100, hoje)
    recusa("Escolha a categoria", "despesa", 999, "Aluguel", 100, hoje)
    recusa("não serve para receita", "receita", cat["Aluguel"], "Aluguel", 100, hoje)
    recusa("não serve para despesa", "despesa", cat["Outras receitas"], "Estorno", 100, hoje)
    recusa(
        "futuro", "despesa", cat["Aluguel"], "Aluguel", 100, hoje, pago_em=hoje + timedelta(days=1)
    )
    sem_data = cliente.post("/api/financeiro/lancamentos", json={"tipo": "despesa"})
    assert sem_data.status_code == 422
    with db.nova_sessao() as sessao:
        assert sessao.scalar(select(func.count(Lancamento.id))) == 1


# ---------------------------------------------------------------- fluxo de caixa


def test_fluxo_de_caixa_por_dia(cliente, loja, vender):
    cat = _categorias(cliente)
    hoje = tempo.hoje()
    ontem, amanha, anteontem = (
        hoje - timedelta(days=1),
        hoje + timedelta(days=1),
        hoje - timedelta(days=2),
    )

    vender([(loja["picole"], 2)])  # 2 x 5,00 = 10,00 em dinheiro
    vender([(loja["agua"], 1)], forma="pix")  # 3,00 no Pix
    _cancelar_venda(cliente, vender([(loja["agua"], 5)]))  # cancelada: não entra em nada
    _lancado(
        cliente,
        "receita",
        cat["Outras receitas"],
        "Venda de caixas vazias",
        5000,
        hoje,
        pago_em=hoje,
        forma="pix",
    )
    _lancado(cliente, "despesa", cat["Energia elétrica"], "Conta de luz", 2000, hoje, pago_em=hoje)
    _lancado(cliente, "despesa", cat["Água"], "Conta de água", 1000, ontem, pago_em=ontem)
    _lancado(cliente, "despesa", cat["Aluguel"], "Aluguel", 7000, amanha)
    _lancado(cliente, "receita", cat["Outras receitas"], "Reembolso a receber", 500, amanha)
    _lancado(cliente, "despesa", cat["Internet e telefone"], "Internet atrasada", 300, anteontem)
    engano = _lancado(
        cliente, "despesa", cat["Aluguel"], "Lançado por engano", 9900, hoje, pago_em=hoje
    )
    cliente.delete(f"/api/financeiro/lancamentos/{engano['id']}/baixa")
    cliente.post(f"/api/financeiro/lancamentos/{engano['id']}/cancelar")

    fluxo = cliente.get("/api/financeiro/fluxo", params=_periodo(ontem, amanha)).json()
    assert [
        (
            d["dia"],
            d["vendas_centavos"],
            d["recebimentos_centavos"],
            d["pagamentos_centavos"],
            d["saldo_centavos"],
            d["acumulado_centavos"],
            d["a_receber_centavos"],
            d["a_pagar_centavos"],
        )
        for d in fluxo["dias"]
    ] == [
        (ontem.isoformat(), 0, 0, 1000, -1000, -1000, 0, 0),
        # hoje: 13,00 de vendas + 50,00 recebidos - 20,00 pagos = 43,00; acumulado 33,00
        (hoje.isoformat(), 1300, 5000, 2000, 4300, 3300, 0, 0),
        (amanha.isoformat(), 0, 0, 0, 0, 3300, 500, 7000),
    ]
    assert (fluxo["vendas_centavos"], fluxo["recebimentos_centavos"]) == (1300, 5000)
    assert fluxo["entradas_centavos"] == 6300  # 13,00 de vendas + 50,00 recebidos
    assert (fluxo["pagamentos_centavos"], fluxo["saldo_centavos"]) == (3000, 3300)
    assert (fluxo["a_receber_centavos"], fluxo["a_pagar_centavos"]) == (500, 7000)
    # A internet atrasada venceu antes do período: não está nos dias, mas está nos vencidos.
    assert (fluxo["vencidos_a_pagar_centavos"], fluxo["vencidos_a_receber_centavos"]) == (300, 0)
    assert fluxo["recebido_por_forma"] == {"dinheiro": 1000, "pix": 300}
    assert fluxo["motivo"] == ""

    mais_largo = cliente.get("/api/financeiro/fluxo", params=_periodo(anteontem, amanha)).json()
    assert (
        mais_largo["dias"][0]["a_pagar_centavos"] == 300 and mais_largo["a_pagar_centavos"] == 7300
    )

    # A lista de lançamentos do mesmo período fecha com o fluxo.
    totais = cliente.get("/api/financeiro/lancamentos", params=_periodo(anteontem, amanha)).json()[
        "totais"
    ]
    assert totais == {
        "a_pagar": 7300,
        "a_receber": 500,
        "pago": 3000,
        "recebido": 5000,
        "vencido_a_pagar": 300,
        "vencido_a_receber": 0,
    }


def test_fluxo_sem_movimento_mostra_o_motivo_e_recusa_periodo_errado(cliente):
    hoje = tempo.hoje()
    vazio = cliente.get("/api/financeiro/fluxo", params=_periodo(hoje, hoje)).json()
    assert vazio["dias"] == []
    assert (vazio["vendas_centavos"], vazio["saldo_centavos"]) == (None, None)  # a tela mostra "—"
    assert vazio["entradas_centavos"] is None
    assert vazio["motivo"] == "sem vendas nem pagamentos no período"
    padrao = cliente.get("/api/financeiro/fluxo").json()  # sem datas: o mês corrente inteiro
    assert padrao["inicio"] == hoje.replace(day=1).isoformat()
    assert padrao["fim"][:8] == hoje.isoformat()[:8]

    invertido = cliente.get(
        "/api/financeiro/fluxo", params=_periodo(hoje, hoje - timedelta(days=1))
    )
    assert invertido.status_code == 422 and "anterior" in invertido.json()["detail"]
    longo = cliente.get("/api/financeiro/dre", params=_periodo(hoje - timedelta(days=400), hoje))
    assert longo.status_code == 422 and "até um ano" in longo.json()["detail"]


# ---------------------------------------------------------------- DRE e rentabilidade


def _cenario_de_vendas(cliente, loja, vender):
    """Três vendas com custo conhecido (e uma cancelada). Contas:

    Custos: picolé 2,00 a unidade; sorvete 25,00 o quilo. Pix dá 5% de desconto; crédito, +3%.

    1. 4 picolés a 5,00 = 20,00 em dinheiro                         total 20,00   custo  8,00
    2. 10 picolés a 4,50 (preço de 10 ou mais) = 45,00
       + 0,5 kg de sorvete a 59,90 = 29,95; subtotal 74,95
       - desconto do gerente 4,95 = 70,00; no Pix (-5% = -3,50)     total 66,50   custo 32,50
    3. 2 picolés a 5,00 = 10,00 no crédito (+3% = +0,30)            total 10,30   custo  4,00
    4. 1 picolé, cancelada depois de finalizada                     (não conta)
    """
    for forma, bp in (("pix", -500), ("credito", 300)):
        regra = cliente.put(f"/api/formas-pagamento/{forma}", json={"ajuste_bp": bp, "ativo": True})
        assert regra.status_code == 200, regra.text
    _entrada(cliente, loja["picole"], 100, 200)
    _entrada(cliente, loja["sorvete"], 10, 2500)
    assert vender([(loja["picole"], 4)])["total_centavos"] == 2000
    segunda = vender(
        [(loja["picole"], 10), (loja["sorvete"], "0.5")], forma="pix", desconto_centavos=495
    )
    assert (segunda["subtotal_centavos"], segunda["total_centavos"]) == (7495, 6650)
    assert vender([(loja["picole"], 2)], forma="credito")["total_centavos"] == 1030
    _cancelar_venda(cliente, vender([(loja["picole"], 1)]))


def test_dre_do_periodo(cliente, loja, vender):
    cat = _categorias(cliente)
    hoje = tempo.hoje()
    _cenario_de_vendas(cliente, loja, vender)
    depois = hoje + timedelta(days=20)
    # Pela competência (hoje), não pelo vencimento nem pelo pagamento:
    _lancado(
        cliente,
        "despesa",
        cat["Impostos sobre a venda (DAS)"],
        "DAS",
        600,
        depois,
        competencia=hoje,
    )
    _lancado(cliente, "despesa", cat["Aluguel"], "Aluguel", 3000, depois, competencia=hoje)
    _lancado(cliente, "despesa", cat["Energia elétrica"], "Luz", 1500, hoje)
    _lancado(cliente, "despesa", cat["Embalagens e descartáveis"], "Copos", 250, hoje)
    _lancado(cliente, "receita", cat["Outras receitas"], "Reembolso", 400, hoje)
    _lancado(cliente, "despesa", cat["Outras despesas"], "Multa", 100, hoje)
    _lancado(cliente, "receita", cat["Outras vendas (fora do caixa)"], "Encomenda", 2000, hoje)
    # O que NÃO entra: compra de mercadoria e aporte dos sócios (fora do resultado),
    # competência de outro mês e lançamento cancelado.
    _lancado(cliente, "despesa", cat["Compra de mercadorias para revenda"], "Boleto", 9999, hoje)
    _lancado(cliente, "receita", cat["Aporte dos sócios e empréstimos"], "Aporte", 8888, hoje)
    _lancado(
        cliente,
        "despesa",
        cat["Energia elétrica"],
        "Luz antiga",
        4444,
        hoje,
        competencia=hoje - timedelta(days=40),
    )
    engano = _lancado(cliente, "despesa", cat["Aluguel"], "Engano", 7777, hoje)
    cliente.post(f"/api/financeiro/lancamentos/{engano['id']}/cancelar")

    dre = cliente.get("/api/financeiro/dre", params=_periodo(hoje, hoje)).json()
    assert (dre["tem_dados"], dre["vendas_quantidade"], dre["avisos"], dre["motivo"]) == (
        True,
        3,
        [],
        "",
    )
    assert [
        (linha["rotulo"], linha["valor_centavos"], linha["nivel"]) for linha in dre["linhas"]
    ] == [
        # itens 20,00 + 74,95 + 10,00 = 104,95; + acréscimo do crédito 0,30; + encomenda 20,00
        ("Receita bruta", 12525, "total"),
        ("Vendas no caixa", 10495, "detalhe"),
        ("Acréscimos das formas de pagamento", 30, "detalhe"),
        ("Outras vendas (fora do caixa)", 2000, "detalhe"),
        ("(−) Descontos concedidos", -845, "linha"),  # 4,95 do gerente + 3,50 do Pix
        ("Descontos na venda", -495, "detalhe"),
        ("Descontos das formas de pagamento", -350, "detalhe"),
        ("(−) Deduções", -600, "linha"),
        ("Impostos sobre a venda (DAS)", -600, "detalhe"),
        ("= Receita líquida", 11080, "total"),  # 125,25 - 8,45 - 6,00
        # custo das vendas 8,00 + 32,50 + 4,00 = 44,50; + copos 2,50
        ("(−) Custo das mercadorias vendidas (CMV)", -4700, "linha"),
        ("Custo dos itens vendidos", -4450, "detalhe"),
        ("Embalagens e descartáveis", -250, "detalhe"),
        ("= Lucro bruto", 6380, "total"),  # 110,80 - 47,00
        ("(−) Despesas operacionais", -4500, "linha"),
        ("Aluguel", -3000, "detalhe"),
        ("Energia elétrica", -1500, "detalhe"),
        ("(+) Outras receitas", 400, "linha"),
        ("Outras receitas", 400, "detalhe"),
        ("(−) Outras despesas", -100, "linha"),
        ("Outras despesas", -100, "detalhe"),
        ("= Resultado do período", 2180, "total"),  # 63,80 - 45,00 + 4,00 - 1,00
    ]
    percentuais = {
        linha["rotulo"]: linha["percentual"] for linha in dre["linhas"] if linha["percentual"]
    }
    assert percentuais == {  # sobre a receita líquida (110,80)
        "(−) Deduções": "5,4%",  # 6,00 / 110,80 = 5,415
        "= Receita líquida": "100,0%",
        "(−) Custo das mercadorias vendidas (CMV)": "42,4%",  # 47,00 / 110,80 = 42,418
        "= Lucro bruto": "57,6%",  # 63,80 / 110,80 = 57,581
        "(−) Despesas operacionais": "40,6%",  # 45,00 / 110,80 = 40,614
        "(+) Outras receitas": "3,6%",  # 4,00 / 110,80 = 3,610
        "(−) Outras despesas": "0,9%",  # 1,00 / 110,80 = 0,902
        "= Resultado do período": "19,7%",  # 21,80 / 110,80 = 19,675
    }
    assert all(linha["motivo"] == "" for linha in dre["linhas"])
    # As linhas principais têm uma chave fixa, para a tela achar sem depender do texto.
    chaves = {linha["chave"]: linha["valor_centavos"] for linha in dre["linhas"] if linha["chave"]}
    assert chaves == {
        "receita_bruta": 12525,
        "descontos": -845,
        "deducoes": -600,
        "receita_liquida": 11080,
        "cmv": -4700,
        "lucro_bruto": 6380,
        "despesas": -4500,
        "resultado": 2180,
    }

    # O total das vendas do fluxo de caixa fecha com o DRE: 20,00 + 66,50 + 10,30 = 96,80,
    # que é a receita bruta do caixa (104,95 + 0,30) menos os descontos (8,45).
    fluxo = cliente.get("/api/financeiro/fluxo", params=_periodo(hoje, hoje)).json()
    assert fluxo["vendas_centavos"] == 9680 == 10495 + 30 - 845


def test_dre_sem_custo_nao_inventa_lucro(cliente, loja, vender):
    cat = _categorias(cliente)
    hoje = tempo.hoje()
    vazio = cliente.get("/api/financeiro/dre", params=_periodo(hoje, hoje)).json()
    assert (vazio["tem_dados"], vazio["motivo"]) == (
        False,
        "sem vendas nem lançamentos de resultado no período",
    )
    assert all(
        linha["valor_centavos"] is None and linha["motivo"] == vazio["motivo"]
        for linha in vazio["linhas"]
    )
    assert vazio["linhas"][0]["rotulo"] == "Receita bruta" and len(vazio["linhas"]) == 8

    # Só uma compra de mercadoria no período: ela é do fluxo de caixa, não do resultado.
    _lancado(cliente, "despesa", cat["Compra de mercadorias para revenda"], "Boleto", 5000, hoje)
    so_compra = cliente.get("/api/financeiro/dre", params=_periodo(hoje, hoje)).json()
    assert (so_compra["tem_dados"], so_compra["linhas"][0]["valor_centavos"]) == (False, None)

    vender([(loja["agua"], 2)])  # água está sem custo cadastrado
    dre = cliente.get("/api/financeiro/dre", params=_periodo(hoje, hoje)).json()
    linhas = {linha["rotulo"]: linha for linha in dre["linhas"]}
    assert linhas["= Receita líquida"]["valor_centavos"] == 600
    sem_custo = "as vendas do período não têm custo gravado nem lançado"
    for rotulo in (
        "(−) Custo das mercadorias vendidas (CMV)",
        "= Lucro bruto",
        "= Resultado do período",
    ):
        assert (linhas[rotulo]["valor_centavos"], linhas[rotulo]["motivo"]) == (None, sem_custo)
    assert len(dre["avisos"]) == 1
    assert dre["avisos"][0].startswith(
        "1 item(ns) vendido(s), somando R$ 6,00, estão sem custo gravado (Água de teste): o "
        "produto estava sem custo na hora da venda, ou a venda é de antes da versão 0.4.0. "
        "Sem custo nenhum, o lucro bruto e o resultado não podem ser calculados."
    )

    # Loja que fabrica lança a matéria-prima como custo: aí há custo, e o demonstrativo diz
    # que ele pode estar incompleto.
    _lancado(cliente, "despesa", cat["Matéria-prima e insumos"], "Leite e açúcar", 200, hoje)
    dre = cliente.get("/api/financeiro/dre", params=_periodo(hoje, hoje)).json()
    linhas = {linha["rotulo"]: linha for linha in dre["linhas"]}
    parcial = "parcial: 1 item(ns) vendido(s) sem custo gravado"
    assert (
        linhas["(−) Custo das mercadorias vendidas (CMV)"]["valor_centavos"],
        linhas["(−) Custo das mercadorias vendidas (CMV)"]["motivo"],
    ) == (-200, parcial)
    assert (linhas["= Lucro bruto"]["valor_centavos"], linhas["= Lucro bruto"]["motivo"]) == (
        400,
        parcial,
    )
    assert linhas["= Resultado do período"]["valor_centavos"] == 400
    assert "só está neste demonstrativo se foi lançado como despesa de custo" in dre["avisos"][0]


def test_rentabilidade_por_produto(cliente, loja, vender):
    hoje = tempo.hoje()
    vazia = cliente.get("/api/financeiro/rentabilidade", params=_periodo(hoje, hoje)).json()
    assert (vazia["linhas"], vazia["receita_centavos"], vazia["motivo"]) == (
        [],
        None,
        "sem vendas no período",
    )
    assert (vazia["receita_com_custo_centavos"], vazia["margem_centavos"]) == (None, None)

    _cenario_de_vendas(cliente, loja, vender)
    quadro = cliente.get("/api/financeiro/rentabilidade", params=_periodo(hoje, hoje)).json()
    assert [
        (
            linha["descricao"],
            float(linha["quantidade"]),
            linha["receita_centavos"],
            linha["custo_centavos"],
            linha["margem_centavos"],
            linha["margem_percentual"],
        )
        for linha in quadro["linhas"]
    ] == [
        # Picolé: 20,00 + a parte dele na venda 2 + 10,30. Na venda 2 os 66,50 são divididos
        # na proporção 45,00 : 29,95 -> 39,926 e 26,573; o centavo que sobra vai para a maior
        # fração: 39,93 e 26,57. Receita 20,00 + 39,93 + 10,30 = 70,23; custo 16 x 2,00.
        ("Picolé de teste", 16.0, 7023, 3200, 3823, "54,4%"),  # 38,23 / 70,23 = 54,43
        ("Sorvete de teste por quilo", 0.5, 2657, 1250, 1407, "53,0%"),  # 14,07 / 26,57 = 52,95
    ]
    # A soma das receitas dos produtos é o total das vendas: 20,00 + 66,50 + 10,30.
    assert (quadro["receita_centavos"], quadro["custo_centavos"], quadro["margem_centavos"]) == (
        9680,
        4450,
        5230,
    )
    assert (quadro["margem_percentual"], quadro["produtos_sem_custo"], quadro["motivo"]) == (
        "54,0%",  # 52,30 / 96,80 = 54,03
        0,
        "",
    )
    assert (quadro["receita_com_custo_centavos"], quadro["receita_sem_custo_centavos"]) == (9680, 0)

    vender([(loja["agua"], 2)])  # sem custo: receita sim, margem não
    quadro = cliente.get("/api/financeiro/rentabilidade", params=_periodo(hoje, hoje)).json()
    agua = quadro["linhas"][-1]
    assert (agua["descricao"], agua["receita_centavos"]) == ("Água de teste", 600)
    assert (agua["custo_centavos"], agua["margem_centavos"], agua["margem_percentual"]) == (
        None,
        None,
        None,
    )
    assert agua["motivo"] == "vendido sem custo gravado na venda"
    assert (quadro["receita_centavos"], quadro["custo_centavos"], quadro["margem_centavos"]) == (
        10280,
        4450,
        5230,  # só dos produtos com custo: 96,80 - 44,50
    )
    assert (quadro["margem_percentual"], quadro["produtos_sem_custo"]) == ("54,0%", 1)
    # A margem é sobre a receita de quem tem custo (96,80); os 6,00 da água ficam à parte.
    assert (quadro["receita_com_custo_centavos"], quadro["receita_sem_custo_centavos"]) == (
        9680,
        600,
    )
    assert (
        quadro["motivo"] == "o custo e a margem somam só os produtos com o custo gravado nas vendas"
    )


def test_rentabilidade_sem_custo_nenhum_nao_mostra_margem(cliente, loja, vender):
    """Só o produto sem custo foi vendido: há receita, e o custo e a margem ficam sem número."""
    hoje = tempo.hoje()
    vender([(loja["agua"], 2)])  # 2 x 3,00
    quadro = cliente.get("/api/financeiro/rentabilidade", params=_periodo(hoje, hoje)).json()
    assert [(linha["descricao"], linha["receita_centavos"]) for linha in quadro["linhas"]] == [
        ("Água de teste", 600)
    ]
    assert (quadro["receita_centavos"], quadro["receita_sem_custo_centavos"]) == (600, 600)
    assert (
        quadro["receita_com_custo_centavos"],
        quadro["custo_centavos"],
        quadro["margem_centavos"],
        quadro["margem_percentual"],
    ) == (None, None, None, None)
    assert (quadro["produtos_sem_custo"], quadro["motivo"]) == (
        1,
        "nenhuma venda do período tem o custo gravado",
    )


# ---------------------------------------------------------------- permissão


def test_so_o_gerente_ve_o_financeiro(anonimo, caixa):
    with db.nova_sessao() as sessao:
        financeiro.semear_categorias(sessao)
        sessao.commit()
        aluguel = sessao.scalar(
            select(CategoriaFinanceira.id).where(CategoriaFinanceira.nome == "Aluguel")
        )
    lancamento = {
        "tipo": "despesa",
        "categoria_id": aluguel,
        "descricao": "Aluguel",
        "valor_centavos": 100,
        "vencimento": tempo.hoje().isoformat(),
    }
    pedidos = (
        ("get", "/api/financeiro/grupos", None),
        ("get", "/api/financeiro/categorias", None),
        ("post", "/api/financeiro/categorias", {"nome": "X", "grupo": "cmv"}),
        ("put", f"/api/financeiro/categorias/{aluguel}", {"nome": "X", "grupo": "cmv"}),
        ("get", "/api/financeiro/lancamentos", None),
        ("post", "/api/financeiro/lancamentos", lancamento),
        ("put", "/api/financeiro/lancamentos/1", lancamento),
        ("post", "/api/financeiro/lancamentos/1/baixa", {"data": tempo.hoje().isoformat()}),
        ("delete", "/api/financeiro/lancamentos/1/baixa", None),
        ("post", "/api/financeiro/lancamentos/1/cancelar", None),
        ("get", "/api/financeiro/fluxo", None),
        ("get", "/api/financeiro/dre", None),
        ("get", "/api/financeiro/rentabilidade", None),
    )
    for metodo, caminho, corpo in pedidos:
        assert caixa.request(metodo, caminho, json=corpo).status_code == 403, caminho
        assert anonimo.request(metodo, caminho, json=corpo).status_code == 401, caminho
    with db.nova_sessao() as sessao:
        assert sessao.scalar(select(func.count(Lancamento.id))) == 0
        assert sessao.get(CategoriaFinanceira, aluguel).nome == "Aluguel"

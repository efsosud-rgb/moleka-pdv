"""Relatório de vendas por período (ESPECIFICACAO §16). Valores esperados calculados à mão."""

from datetime import UTC, date, datetime, timedelta

import pytest

from app import db, relatorios, tempo
from app.models import Venda

# ---------------------------------------------------------------- ajudantes


def _utc(na_loja: datetime) -> datetime:
    """Hora da loja (sem fuso) -> hora do banco (UTC sem fuso)."""
    return na_loja.replace(tzinfo=tempo.FUSO).astimezone(UTC).replace(tzinfo=None)


def _mover(venda_id, *, finalizada=None, cancelada=None):
    """Põe a venda num dia e numa hora conhecidos (horário da loja)."""
    with db.nova_sessao() as sessao:
        venda = sessao.get(Venda, venda_id)
        if finalizada is not None:
            venda.finalizada_em = _utc(finalizada)
        if cancelada is not None:
            venda.cancelada_em = _utc(cancelada)
        sessao.commit()


def _periodo(inicio, fim, **mais):
    return {"inicio": inicio.isoformat(), "fim": fim.isoformat(), **mais}


def _as(dia: date, hora: int, minuto: int) -> datetime:
    return datetime(dia.year, dia.month, dia.day, hora, minuto)


D1 = tempo.hoje() - timedelta(days=10)
D2 = D1 + timedelta(days=1)
D3 = D1 + timedelta(days=2)


def _cenario(cliente, caixa, loja, vender):
    """Seis vendas em três dias (horário da loja). Pix dá 5% de desconto; crédito, +3%.

    1. D1 14:10, gerente: 4 picolés a 5,00 = 20,00 em dinheiro                  total  20,00
    2. D1 23:30, gerente: 10 picolés a 4,50 = 45,00 + 0,5 kg de sorvete = 29,95;
       subtotal 74,95 - desconto do gerente 4,95 = 70,00; Pix -5% (-3,50)       total  66,50
       (no banco a hora é D1+1 02:30 UTC: tem de contar no dia D1, às 23 h)
    3. D2 09:05, gerente: 2 picolés = 10,00 no crédito (+3% = +0,30)            total  10,30
    4. gerente: 1 picolé = 5,00, finalizada D2 10:00, cancelada D3 15:00        (não soma)
    5. D2 20:15, caixa: 2 águas = 6,00 + 1 picolé = 5,00; 5,00 em dinheiro e o
       resto (6,00) no Pix (-5% = -0,30, paga 5,70)                             total  10,70
    6. caixa: 1 kg de sorvete = 59,90, cancelada antes de finalizar, D2 16:00   (não soma)
    """
    for forma, bp in (("pix", -500), ("credito", 300)):
        regra = cliente.put(f"/api/formas-pagamento/{forma}", json={"ajuste_bp": bp, "ativo": True})
        assert regra.status_code == 200, regra.text
    v1 = vender([(loja["picole"], 4)])
    v2 = vender(
        [(loja["picole"], 10), (loja["sorvete"], "0.5")], forma="pix", desconto_centavos=495
    )
    v3 = vender([(loja["picole"], 2)], forma="credito")
    v4 = vender([(loja["picole"], 1)])
    assert [v["total_centavos"] for v in (v1, v2, v3, v4)] == [2000, 6650, 1030, 500]
    cancelada = cliente.post(f"/api/vendas/{v4['id']}/cancelar", json={"motivo": "teste"})
    assert cancelada.status_code == 200, cancelada.text

    for produto_id, quantidade in ((loja["agua"], 2), (loja["picole"], 1)):
        item = caixa.post(
            "/api/venda/itens", json={"produto_id": produto_id, "quantidade": quantidade}
        )
        assert item.status_code == 201, item.text
    assert (
        caixa.post(
            "/api/venda/pagamentos", json={"forma": "dinheiro", "valor_centavos": 500}
        ).status_code
        == 201
    )
    assert caixa.post("/api/venda/pagamentos", json={"forma": "pix"}).status_code == 201
    fim = caixa.post("/api/venda/finalizar", json={})
    assert fim.status_code == 200, fim.text
    v5 = fim.json()["venda"]
    assert v5["total_centavos"] == 1070

    item = caixa.post("/api/venda/itens", json={"produto_id": loja["sorvete"], "quantidade": "1"})
    assert item.status_code == 201, item.text
    v6_id = item.json()["venda"]["id"]
    desistiu = caixa.post("/api/venda/cancelar", json={"motivo": "cliente desistiu"})
    assert desistiu.status_code == 200, desistiu.text

    _mover(v1["id"], finalizada=_as(D1, 14, 10))
    _mover(v2["id"], finalizada=_as(D1, 23, 30))
    _mover(v3["id"], finalizada=_as(D2, 9, 5))
    _mover(v4["id"], finalizada=_as(D2, 10, 0), cancelada=_as(D3, 15, 0))
    _mover(v5["id"], finalizada=_as(D2, 20, 15))
    _mover(v6_id, cancelada=_as(D2, 16, 0))
    return {
        "v1": v1["id"],
        "v2": v2["id"],
        "v3": v3["id"],
        "v4": v4["id"],
        "v5": v5["id"],
        "v6": v6_id,
    }


def _operadores(cliente):
    return {o["nome"]: o["id"] for o in cliente.get("/api/operadores").json()}


# ---------------------------------------------------------------- o relatório


def test_relatorio_sem_vendas_nao_inventa_numero(cliente, loja):
    hoje = tempo.hoje()
    r = cliente.get("/api/relatorios/vendas", params=_periodo(hoje, hoje)).json()
    assert (r["vendas"], r["faturamento_centavos"], r["ticket_medio_centavos"]) == (0, None, None)
    assert (r["itens_centavos"], r["desconto_gerente_centavos"]) == (None, None)
    assert (r["sem_documento_fiscal"], r["sem_documento_fiscal_centavos"]) == (0, None)
    assert r["descontos_centavos"] is None
    assert (r["dias"], r["meses"], r["operadores"], r["horarios"], r["produtos"]) == (
        [],
        [],
        [],
        [],
        [],
    )
    assert (r["classes"], r["por_hora"]) == ([], [])
    assert [(s["vendas"], s["faturamento_centavos"]) for s in r["por_dia_da_semana"]] == [
        (0, None)
    ] * 7
    assert r["motivo"] == "sem vendas no período"
    assert [(f["rotulo"], f["recebido_centavos"], f["motivo"]) for f in r["formas"]] == [
        ("Dinheiro", None, "nenhuma venda nesta forma"),
        ("Pix", None, "nenhuma venda nesta forma"),
        ("Débito", None, "nenhuma venda nesta forma"),
        ("Crédito", None, "nenhuma venda nesta forma"),
    ]
    # Sem datas, vale o dia de hoje.
    sem_datas = cliente.get("/api/relatorios/vendas").json()
    assert (sem_datas["inicio"], sem_datas["fim"]) == (hoje.isoformat(), hoje.isoformat())


def test_relatorio_de_vendas_do_periodo(cliente, caixa, loja, vender):
    _cenario(cliente, caixa, loja, vender)
    r = cliente.get("/api/relatorios/vendas", params=_periodo(D1, D3)).json()

    # Vendas 1, 2, 3 e 5: 20,00 + 66,50 + 10,30 + 10,70 = 107,50. Ticket 107,50 / 4 = 26,875.
    assert (r["vendas"], r["faturamento_centavos"], r["ticket_medio_centavos"]) == (4, 10750, 2688)
    # Itens 20,00 + 74,95 + 10,00 + 11,00 = 115,95; - 4,95 do gerente - (3,50 + 0,30) do Pix
    # + 0,30 do crédito = 107,50.
    assert (
        r["itens_centavos"],
        r["desconto_gerente_centavos"],
        r["descontos_formas_centavos"],
        r["acrescimos_formas_centavos"],
    ) == (11595, 495, 380, 30)
    assert 11595 - 495 - 380 + 30 == r["faturamento_centavos"]
    assert r["descontos_centavos"] == 495 + 380  # gerente + formas
    assert (r["sem_documento_fiscal"], r["sem_documento_fiscal_centavos"]) == (4, 10750)
    assert r["marcadas_para_nfce"] == 0
    assert r["motivo_fiscal"].startswith("o sistema ainda não emite NFC-e")
    assert (r["canceladas_antes"], r["canceladas_antes_centavos"]) == (1, 5990)
    assert (r["canceladas_depois"], r["canceladas_depois_centavos"]) == (1, 500)
    assert (r["canceladas"], r["canceladas_centavos"]) == (2, 5990 + 500)
    assert r["motivo"] == ""

    # Por dia da loja: a venda das 23:30 fica no D1 (no banco ela está no dia seguinte, em UTC).
    assert [
        (
            d["dia"],
            d["vendas"],
            d["faturamento_centavos"],
            d["ticket_medio_centavos"],
            d["canceladas"],
        )
        for d in r["dias"]
    ] == [
        (D1.isoformat(), 2, 8650, 4325, 0),  # 20,00 + 66,50
        (D2.isoformat(), 2, 2100, 1050, 1),  # 10,30 + 10,70; a venda 6 cancelada às 16:00
        (D3.isoformat(), 0, None, None, 1),  # só o cancelamento da venda 4
    ]

    # Formas: dinheiro 20,00 + 5,00; Pix 66,50 + 5,70; crédito 10,30.
    assert [
        (
            f["rotulo"],
            f["vendas"],
            f["recebido_centavos"],
            f["ajuste_centavos"],
            f["participacao"],
            f["motivo"],
        )
        for f in r["formas"]
    ] == [
        ("Dinheiro", 2, 2500, 0, "23,3%", ""),  # 25,00 / 107,50 = 23,26
        ("Pix", 2, 7220, -380, "67,2%", ""),  # 72,20 / 107,50 = 67,16
        ("Débito", 0, None, None, None, "nenhuma venda nesta forma"),
        ("Crédito", 1, 1030, 30, "9,6%", ""),  # 10,30 / 107,50 = 9,58
    ]

    # Operadores: o gerente vendeu 1, 2 e 3 (a 4 foi cancelada); o caixa vendeu a 5.
    assert [
        (
            o["nome"],
            o["vendas"],
            o["faturamento_centavos"],
            o["ticket_medio_centavos"],
            o["participacao"],
            o["desconto_gerente_centavos"],
            o["canceladas_antes"],
            o["canceladas_depois"],
            o["valor_cancelado_centavos"],
        )
        for o in r["operadores"]
    ] == [
        # 96,80 / 3 = 32,266...; 96,80 / 107,50 = 90,05%
        ("Gerente de Teste", 3, 9680, 3227, "90,0%", 495, 0, 1, 500),
        # 10,70 / 107,50 = 9,95%
        ("Caixa de Teste", 1, 1070, 1070, "10,0%", 0, 1, 0, 5990),
    ]

    # Horário da loja: dia da semana (0 = segunda) e hora.
    assert [
        (h["dia_semana"], h["hora"], h["vendas"], h["faturamento_centavos"]) for h in r["horarios"]
    ] == sorted(
        [
            (D1.weekday(), 14, 1, 2000),
            (D1.weekday(), 23, 1, 6650),
            (D2.weekday(), 9, 1, 1030),
            (D2.weekday(), 20, 1, 1070),
        ]
    )
    # Somas da mesma grade por dia da semana (sempre os 7) e por hora (só as com venda).
    esperado = {D1.weekday(): (2, 8650, 4325), D2.weekday(): (2, 2100, 1050)}
    assert [
        (
            s["dia_semana"],
            s["rotulo"],
            s["dias_no_periodo"],
            s["vendas"],
            s["faturamento_centavos"],
            s["ticket_medio_centavos"],
        )
        for s in r["por_dia_da_semana"]
    ] == [
        (
            i,
            nome,
            1 if i in {D1.weekday(), D2.weekday(), D3.weekday()} else 0,
            *esperado.get(i, (0, None, None)),
        )
        for i, nome in enumerate(
            ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")
        )
    ]
    assert [
        (h["hora"], h["vendas"], h["faturamento_centavos"], h["ticket_medio_centavos"])
        for h in r["por_hora"]
    ] == [(9, 1, 1030, 1030), (14, 1, 2000, 2000), (20, 1, 1070, 1070), (23, 1, 6650, 6650)]

    # Produtos. Venda 2: 66,50 dividido 45,00 : 29,95 -> 39,926 e 26,573 -> 39,93 e 26,57.
    # Venda 5: 10,70 dividido 6,00 : 5,00 -> 5,836 e 4,863 -> 5,84 e 4,86.
    # Picolé: 20,00 + 39,93 + 10,30 + 4,86 = 75,09 (4 + 10 + 2 + 1 = 17 unidades, em 4 vendas).
    assert [
        (
            p["descricao"],
            float(p["quantidade"]),
            p["vendas"],
            p["faturamento_centavos"],
            p["participacao"],
            p["acumulado"],
            p["classe"],
        )
        for p in r["produtos"]
    ] == [
        ("Picolé de teste", 17.0, 4, 7509, "69,9%", "69,9%", "A"),  # 75,09 / 107,50 = 69,85
        # Antes dele, 69,85% (< 80%): ainda é A, mesmo passando dos 80% (101,66 = 94,57%).
        ("Sorvete de teste por quilo", 0.5, 1, 2657, "24,7%", "94,6%", "A"),
        # Antes dela, 94,57% (< 95%): é B.
        ("Água de teste", 2.0, 1, 584, "5,4%", "100,0%", "B"),
    ]
    assert sum(p["faturamento_centavos"] for p in r["produtos"]) == r["faturamento_centavos"]
    assert [
        (c["classe"], c["produtos"], c["faturamento_centavos"], c["participacao"])
        for c in r["classes"]
    ] == [
        ("A", 2, 10166, "94,6%"),
        ("B", 1, 584, "5,4%"),
    ]


def test_o_relatorio_bate_com_a_rentabilidade_e_o_fluxo_de_caixa(cliente, caixa, loja, vender):
    _cenario(cliente, caixa, loja, vender)
    params = _periodo(D1, D3)
    r = cliente.get("/api/relatorios/vendas", params=params).json()
    rent = cliente.get("/api/financeiro/rentabilidade", params=params).json()
    fluxo = cliente.get("/api/financeiro/fluxo", params=params).json()
    assert rent["receita_centavos"] == fluxo["vendas_centavos"] == r["faturamento_centavos"]
    assert {(p["produto_id"], p["faturamento_centavos"]) for p in r["produtos"]} == {
        (linha["produto_id"], linha["receita_centavos"]) for linha in rent["linhas"]
    }
    por_forma = {f["forma"]: f["recebido_centavos"] for f in r["formas"] if f["vendas"]}
    assert por_forma == fluxo["recebido_por_forma"]
    # No DRE: receita bruta (itens + acréscimos das formas) - descontos concedidos. Sem outros
    # lançamentos de receita ou de dedução (como aqui), a receita líquida é o faturamento.
    dre = cliente.get("/api/financeiro/dre", params=params).json()
    linhas = {linha["chave"]: linha["valor_centavos"] for linha in dre["linhas"] if linha["chave"]}
    assert linhas["receita_bruta"] == r["itens_centavos"] + r["acrescimos_formas_centavos"]
    assert linhas["descontos"] == -r["descontos_centavos"]
    assert linhas["receita_liquida"] == r["faturamento_centavos"]


def test_filtro_por_operador(cliente, caixa, loja, vender):
    _cenario(cliente, caixa, loja, vender)
    do_caixa = _operadores(cliente)["Caixa de Teste"]
    r = cliente.get("/api/relatorios/vendas", params=_periodo(D1, D3, operador_id=do_caixa)).json()
    assert (r["operador_nome"], r["vendas"], r["faturamento_centavos"]) == (
        "Caixa de Teste",
        1,
        1070,
    )
    assert (r["canceladas_antes"], r["canceladas_depois"]) == (1, 0)
    assert [(p["descricao"], p["faturamento_centavos"]) for p in r["produtos"]] == [
        ("Água de teste", 584),
        ("Picolé de teste", 486),
    ]
    assert [(f["rotulo"], f["recebido_centavos"]) for f in r["formas"] if f["vendas"]] == [
        ("Dinheiro", 500),
        ("Pix", 570),
    ]
    assert [o["nome"] for o in r["operadores"]] == ["Caixa de Teste"]
    desconhecido = cliente.get("/api/relatorios/vendas", params=_periodo(D1, D3, operador_id=999))
    assert (desconhecido.status_code, desconhecido.json()["detail"]) == (
        404,
        "Operador não encontrado.",
    )


def test_venda_antiga_sem_operador_conta_para_quem_abriu_o_caixa(cliente, caixa, loja, vender):
    """As vendas da versão 0.2 não guardavam o operador: nelas vale quem abriu o caixa."""
    venda = vender([(loja["picole"], 2)], quem=caixa)  # 10,00, feita pelo caixa
    with db.nova_sessao() as sessao:
        sessao.get(Venda, venda["id"]).operador_id = None  # como ficou gravada na versão 0.2
        sessao.commit()
    hoje = tempo.hoje()
    r = cliente.get("/api/relatorios/vendas", params=_periodo(hoje, hoje)).json()
    # O caixa foi aberto pelo gerente (fixture `loja`).
    assert [(o["nome"], o["vendas"], o["faturamento_centavos"]) for o in r["operadores"]] == [
        ("Gerente de Teste", 1, 1000)
    ]
    ids = _operadores(cliente)
    filtro = _periodo(hoje, hoje, operador_id=ids["Gerente de Teste"])
    assert (
        cliente.get("/api/relatorios/vendas", params=filtro).json()["faturamento_centavos"] == 1000
    )
    lista = cliente.get("/api/relatorios/vendas/lista", params=_periodo(hoje, hoje)).json()
    assert [v["operador"] for v in lista["vendas"]] == ["Gerente de Teste"]


def test_curva_abc_nos_limites():
    def produtos(*faturamentos):
        return [
            relatorios.ProdutoVendido(i, str(i), f"P{i}", "UN", faturamento=f)
            for i, f in enumerate(faturamentos)
        ]

    # 80 + 15 + 5: o segundo começa exatamente em 80% (não é menos de 80%): B; o terceiro
    # começa exatamente em 95%: C.
    lista = produtos(80, 15, 5)
    relatorios.classificar_abc(lista)
    assert [p.classe for p in lista] == ["A", "B", "C"]
    # 79 + 16 + 5: o segundo começa em 79% (< 80%): A; o terceiro começa em 95%: C.
    lista = produtos(79, 16, 5)
    relatorios.classificar_abc(lista)
    assert [p.classe for p in lista] == ["A", "A", "C"]
    # Um produto só: A. Nada faturado: sem classe.
    lista = produtos(1)
    relatorios.classificar_abc(lista)
    assert [p.classe for p in lista] == ["A"]
    lista = produtos(0, 0)
    relatorios.classificar_abc(lista)
    assert [p.classe for p in lista] == ["", ""]


def test_dias_da_semana_no_periodo():
    """Quantas segundas, terças... o período tem (cada linha da grade de horários soma todas)."""
    contar = relatorios.dias_da_semana_no_periodo
    assert date(2026, 11, 1).weekday() == 6  # domingo
    # Novembro de 2026: 4 semanas inteiras, mais o domingo 1º e a segunda 30.
    assert contar(date(2026, 11, 1), date(2026, 11, 30)) == [5, 4, 4, 4, 4, 4, 5]
    assert contar(date(2026, 11, 12), date(2026, 11, 12)) == [0, 0, 0, 1, 0, 0, 0]  # uma quinta
    assert contar(date(2026, 11, 9), date(2026, 11, 15)) == [1] * 7
    # 2026 começa numa quinta: 52 semanas e mais uma quinta.
    assert contar(date(2026, 1, 1), date(2026, 12, 31)) == [52, 52, 52, 53, 52, 52, 52]
    assert contar(date(2026, 11, 2), date(2026, 11, 1)) == [0] * 7


def _vendas_em_dois_meses(cliente, loja, vender):
    """Setembro: 20,00, às 23:30 do dia 30 (no banco já é 1º de outubro, em UTC). Outubro: 10,00
    no dia 15, e 5,00 finalizada no dia 20 e cancelada no dia 21 (não soma)."""
    v1 = vender([(loja["picole"], 4)])
    v2 = vender([(loja["picole"], 2)])
    v3 = vender([(loja["picole"], 1)])
    cancelada = cliente.post(f"/api/vendas/{v3['id']}/cancelar", json={"motivo": "teste"})
    assert cancelada.status_code == 200, cancelada.text
    _mover(v1["id"], finalizada=datetime(2026, 9, 30, 23, 30))
    _mover(v2["id"], finalizada=datetime(2026, 10, 15, 10, 0))
    _mover(
        v3["id"], finalizada=datetime(2026, 10, 20, 11, 0), cancelada=datetime(2026, 10, 21, 9, 0)
    )


def test_relatorio_soma_por_mes(cliente, loja, vender):
    _vendas_em_dois_meses(cliente, loja, vender)

    def meses(inicio, fim):
        r = cliente.get("/api/relatorios/vendas", params=_periodo(inicio, fim)).json()
        return r, [
            (
                m["mes"],
                m["vendas"],
                m["faturamento_centavos"],
                m["ticket_medio_centavos"],
                m["canceladas"],
            )
            for m in r["meses"]
        ]

    r, por_mes = meses(date(2026, 9, 1), date(2026, 10, 31))
    assert por_mes == [("2026-09-01", 1, 2000, 2000, 0), ("2026-10-01", 1, 1000, 1000, 1)]
    assert sum(m[2] for m in por_mes) == r["faturamento_centavos"] == 3000
    # 1º/9/2026 é terça; 61 dias
    assert [s["dias_no_periodo"] for s in r["por_dia_da_semana"]] == [8, 9, 9, 9, 9, 9, 8]
    # Um mês só com o cancelamento aparece, sem faturamento (e não com zero).
    _r, so_o_cancelamento = meses(date(2026, 10, 21), date(2026, 10, 21))
    assert so_o_cancelamento == [("2026-10-01", 0, None, None, 1)]
    _r, nada = meses(date(2026, 8, 1), date(2026, 8, 31))
    assert nada == []


def test_periodo_invalido_e_permissoes(cliente, caixa, anonimo, loja):
    hoje = tempo.hoje()
    invertido = cliente.get(
        "/api/relatorios/vendas", params=_periodo(hoje, hoje - timedelta(days=1))
    )
    assert (invertido.status_code, invertido.json()["detail"]) == (
        422,
        "A data final é anterior à data inicial.",
    )
    longo = cliente.get("/api/relatorios/vendas", params=_periodo(hoje - timedelta(days=367), hoje))
    assert (longo.status_code, longo.json()["detail"]) == (422, "Escolha um período de até um ano.")
    for caminho in ("/api/relatorios/vendas", "/api/relatorios/vendas/lista"):
        assert caixa.get(caminho).status_code == 403
        assert anonimo.get(caminho).status_code == 401


# ---------------------------------------------------------------- a lista


def test_lista_de_vendas_do_periodo(cliente, caixa, loja, vender):
    ids = _cenario(cliente, caixa, loja, vender)
    lista = cliente.get("/api/relatorios/vendas/lista", params=_periodo(D1, D3)).json()
    assert [
        (
            v["id"],
            v["numero"],
            v["situacao_rotulo"],
            v["momento"][:16],
            v["operador"],
            v["formas"],
            v["total_centavos"],
            v["motivo_cancelamento"],
            v["cancelada_por"],
        )
        for v in lista["vendas"]
    ] == [
        (
            ids["v5"],
            5,
            "Finalizada",
            f"{D2}T20:15",
            "Caixa de Teste",
            ["Dinheiro", "Pix"],
            1070,
            "",
            "",
        ),
        (
            ids["v6"],
            6,
            "Cancelada antes de finalizar",
            f"{D2}T16:00",
            "Caixa de Teste",
            [],
            5990,
            "cliente desistiu",
            "Caixa de Teste",
        ),
        (
            ids["v4"],
            4,
            "Cancelada depois de finalizada",
            f"{D2}T10:00",
            "Gerente de Teste",
            ["Dinheiro"],
            500,
            "teste",
            "Gerente de Teste",
        ),
        (ids["v3"], 3, "Finalizada", f"{D2}T09:05", "Gerente de Teste", ["Crédito"], 1030, "", ""),
        (ids["v2"], 2, "Finalizada", f"{D1}T23:30", "Gerente de Teste", ["Pix"], 6650, "", ""),
        (ids["v1"], 1, "Finalizada", f"{D1}T14:10", "Gerente de Teste", ["Dinheiro"], 2000, "", ""),
    ]
    # A hora vai com o fuso da loja: 23:30 em Brasília, e não 02:30 do dia seguinte.
    assert lista["vendas"][4]["finalizada_em"] == f"{D1}T23:30:00-03:00"
    assert (lista["finalizadas"], lista["finalizadas_centavos"], lista["canceladas"]) == (
        4,
        10750,
        2,
    )

    canceladas = cliente.get(
        "/api/relatorios/vendas/lista", params=_periodo(D1, D3, situacao="canceladas")
    ).json()
    assert [v["numero"] for v in canceladas["vendas"]] == [6, 4]
    assert (canceladas["finalizadas"], canceladas["finalizadas_centavos"]) == (0, None)
    # A venda 4 foi finalizada no D2 e cancelada no D3: entra na lista dos dois dias.
    so_d3 = cliente.get("/api/relatorios/vendas/lista", params=_periodo(D3, D3)).json()
    assert [(v["numero"], v["situacao"]) for v in so_d3["vendas"]] == [(4, "cancelada_depois")]
    finalizadas = cliente.get(
        "/api/relatorios/vendas/lista", params=_periodo(D1, D3, situacao="finalizadas")
    ).json()
    assert [v["numero"] for v in finalizadas["vendas"]] == [5, 3, 2, 1]
    vazia = cliente.get(
        "/api/relatorios/vendas/lista",
        params=_periodo(D3 + timedelta(days=1), D3 + timedelta(days=1)),
    ).json()
    assert (vazia["vendas"], vazia["motivo"]) == ([], "nenhuma venda nem cancelamento no período")
    errada = cliente.get("/api/relatorios/vendas/lista", params=_periodo(D1, D3, situacao="x"))
    assert (errada.status_code, errada.json()["detail"]) == (422, "Situação desconhecida.")


def test_lista_grande_demais_nao_vem_cortada(cliente, caixa, loja, vender, monkeypatch):
    _cenario(cliente, caixa, loja, vender)
    monkeypatch.setattr(relatorios, "LIMITE_DA_LISTA", 3)
    grande = cliente.get("/api/relatorios/vendas/lista", params=_periodo(D1, D3))
    assert grande.status_code == 422
    assert grande.json()["detail"].startswith(
        "O período tem 6 vendas, mais do que as 3 que a lista"
    )
    # Os números do relatório não dependem da lista.
    assert cliente.get("/api/relatorios/vendas", params=_periodo(D1, D3)).json()["vendas"] == 4


@pytest.mark.parametrize("hora", [0, 2, 21, 23])
def test_dia_e_hora_sao_os_da_loja(cliente, loja, vender, hora):
    """De 21:00 às 23:59 em Brasília já é o dia seguinte em UTC; o relatório usa o dia da loja."""
    venda = vender([(loja["agua"], 1)])
    _mover(venda["id"], finalizada=_as(D1, hora, 30))
    r = cliente.get("/api/relatorios/vendas", params=_periodo(D1, D1)).json()
    assert [(d["dia"], d["vendas"]) for d in r["dias"]] == [(D1.isoformat(), 1)]
    assert [(h["dia_semana"], h["hora"]) for h in r["horarios"]] == [(D1.weekday(), hora)]
    vizinhos = cliente.get(
        "/api/relatorios/vendas",
        params=_periodo(D1 - timedelta(days=1), D1 - timedelta(days=1)),
    ).json()
    assert vizinhos["vendas"] == 0
    seguinte = cliente.get(
        "/api/relatorios/vendas", params=_periodo(D1 + timedelta(days=1), D1 + timedelta(days=1))
    ).json()
    assert seguinte["vendas"] == 0

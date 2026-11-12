"""Planilhas do Excel dos relatórios: os números são os mesmos da tela."""

import io
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from openpyxl import load_workbook

from app import config, excel, tempo
from tests.test_relatorio_vendas import D1, D2, D3, _cenario, _periodo

REAIS = '"R$" #,##0.00;[Red]-"R$" #,##0.00'


def _baixar(cliente, caminho, **params):
    resposta = cliente.get(caminho, params=params)
    assert resposta.status_code == 200, resposta.text
    assert resposta.headers["content-type"] == excel.TIPO_DO_ARQUIVO
    return resposta, load_workbook(io.BytesIO(resposta.content))


def _tabela(aba, primeira_coluna):
    """As linhas da tabela: da linha do título (`primeira_coluna` na coluna A) até a linha vazia."""
    linhas = [[c.value for c in linha] for linha in aba.iter_rows()]
    inicio = next(i for i, linha in enumerate(linhas) if linha[0] == primeira_coluna)
    tabela = []
    for linha in linhas[inicio + 1 :]:
        if all(v is None for v in linha):
            break
        tabela.append(linha)
    return linhas[inicio], tabela


def _reais(valor):
    return None if valor is None else round(Decimal(str(valor)) * 100)


# ---------------------------------------------------------------- relatório de vendas


def test_planilha_de_vendas_tem_os_numeros_da_tela(cliente, caixa, loja, vender):
    _cenario(cliente, caixa, loja, vender)
    cliente.put(
        "/api/configuracoes/loja",
        json={
            "nome_fantasia": "Sorveteria de Teste",
            "razao_social": "",
            "cnpj": "11.222.333/0001-81",
            "ie": "",
            "logradouro": "",
            "numero": "",
            "bairro": "",
            "cidade": "",
            "uf": "",
            "cep": "",
            "telefone": "",
            "rodape": "",
        },
    )
    tela = cliente.get("/api/relatorios/vendas", params=_periodo(D1, D3)).json()
    resposta, livro = _baixar(cliente, "/api/planilhas/vendas", **_periodo(D1, D3))
    nome = f"Moleka - Vendas {D1:%d-%m-%Y} a {D3:%d-%m-%Y}.xlsx"
    assert f"filename*=UTF-8''{nome.replace(' ', '%20')}" in resposta.headers["content-disposition"]
    # Dependendo do dia em que o teste roda, D1 e D3 podem cair em meses diferentes.
    varios_meses = (D1.year, D1.month) != (D3.year, D3.month)
    assert livro.sheetnames == [
        "Resumo",
        "Por dia",
        *(["Por mês"] if varios_meses else []),
        "Formas de pagamento",
        "Operadores",
        "Produtos",
        "Horários (R$)",
        "Horários (vendas)",
        "Lista de vendas",
    ]

    resumo = livro["Resumo"]
    assert resumo["A1"].value == "Sorveteria de Teste · CNPJ 11.222.333/0001-81"
    assert resumo["A2"].value == "Vendas por período: resumo"
    assert resumo["A3"].value == f"Período: {D1:%d/%m/%Y} a {D3:%d/%m/%Y}"
    assert resumo["A4"].value == "Operador: todos"
    assert resumo["A5"].value.startswith(f"Gerada em {tempo.hoje():%d/%m/%Y} às ")
    assert resumo["A5"].value.endswith(f"por Gerente de Teste · Moleka PDV {config.VERSAO}")
    _titulo, linhas = _tabela(resumo, "Indicador")
    valores = {
        linha[0]: (_reais(linha[1]) if linha[1] != "—" else "—", linha[2]) for linha in linhas
    }
    assert valores == {
        "Valor dos itens (antes dos descontos)": (11595, None),
        "Desconto do gerente": (-495, None),
        "Descontos das formas de pagamento": (-380, None),
        "Acréscimos das formas de pagamento": (30, None),
        "Faturamento": (10750, 4),
        "Ticket médio (faturamento ÷ vendas)": (2688, None),
        "Canceladas antes de finalizar": (5990, 1),
        "Canceladas depois de finalizadas": (500, 1),
        "Vendas sem documento fiscal": (10750, 4),
        "Vendas em que o caixa pediu NFC-e": (None, 0),
    }
    faturamento = next(linha for linha in resumo.iter_rows() if linha[0].value == "Faturamento")
    assert faturamento[1].number_format == REAIS

    _titulo, dias = _tabela(livro["Por dia"], "Dia")
    assert [
        (linha[0], linha[2], _reais(linha[3]) if linha[3] != "—" else "—", linha[5])
        for linha in dias
    ] == [
        (datetime(D1.year, D1.month, D1.day), 2, 8650, 0),
        (datetime(D2.year, D2.month, D2.day), 2, 2100, 1),
        (datetime(D3.year, D3.month, D3.day), 0, "—", 1),
        (None, 4, 10750, 2),  # o total
    ]
    assert livro["Por dia"].cell(row=8, column=1).number_format == "dd/mm/yyyy"

    _titulo, formas = _tabela(livro["Formas de pagamento"], "Forma")
    assert [
        (linha[0], linha[1], linha[2] if linha[2] == "—" else _reais(linha[2]), linha[4])
        for linha in formas
    ] == [
        ("Dinheiro", 2, 2500, 0.233),  # 23,3% vai como 0,233 no formato de %
        ("Pix", 2, 7220, 0.672),
        ("Débito", 0, "—", "—"),
        ("Crédito", 1, 1030, 0.096),
        ("Total", None, 10750, None),
    ]

    _titulo, produtos = _tabela(livro["Produtos"], "Código")
    assert [
        (linha[1], linha[3], linha[4], _reais(linha[5]), linha[6], linha[7], linha[8])
        for linha in produtos[:-1]
    ] == [
        (
            p["descricao"],
            float(p["quantidade"]),
            p["vendas"],
            p["faturamento_centavos"],
            v1,
            v2,
            p["classe"],
        )
        for p, v1, v2 in zip(
            tela["produtos"], (0.699, 0.247, 0.054), (0.699, 0.946, 1), strict=True
        )
    ]

    titulo, grade = _tabela(livro["Horários (R$)"], "Dia da semana")
    assert titulo[1:-1] == ["9h", "14h", "20h", "23h"]
    por_celula = {}
    for linha in grade[:-1]:
        for hora, valor in zip(titulo[1:-1], linha[1:-1], strict=True):
            if valor is not None:
                por_celula[(linha[0], hora)] = _reais(valor)
    # Entre parênteses, quantos daquele dia da semana o período tem: D1, D2 e D3 são três dias
    # seguidos, então um de cada.
    nomes = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")
    assert por_celula == {
        (f"{nomes[D1.weekday()]} (1)", "14h"): 2000,
        (f"{nomes[D1.weekday()]} (1)", "23h"): 6650,
        (f"{nomes[D2.weekday()]} (1)", "9h"): 1030,
        (f"{nomes[D2.weekday()]} (1)", "20h"): 1070,
    }
    assert [linha[0] for linha in grade[:-1]] == [
        f"{nome} ({1 if i in {D1.weekday(), D2.weekday(), D3.weekday()} else 0})"
        for i, nome in enumerate(nomes)
    ]
    assert _reais(grade[-1][-1]) == 10750

    _titulo, lista = _tabela(livro["Lista de vendas"], "Nº")
    assert [(linha[0], linha[1], linha[2], _reais(linha[6]), linha[7]) for linha in lista] == [
        (5, datetime(D2.year, D2.month, D2.day, 20, 15), "Finalizada", 1070, "Não"),
        # Cancelada antes de finalizar: a escolha da NFC-e nem chegou a ser feita.
        (6, datetime(D2.year, D2.month, D2.day, 16, 0), "Cancelada antes de finalizar", 5990, None),
        (
            4,
            datetime(D2.year, D2.month, D2.day, 10, 0),
            "Cancelada depois de finalizada",
            500,
            "Não",
        ),
        (3, datetime(D2.year, D2.month, D2.day, 9, 5), "Finalizada", 1030, "Não"),
        # 23:30 da loja (no banco é 02:30 do dia seguinte, em UTC)
        (2, datetime(D1.year, D1.month, D1.day, 23, 30), "Finalizada", 6650, "Não"),
        (1, datetime(D1.year, D1.month, D1.day, 14, 10), "Finalizada", 2000, "Não"),
    ]


def test_planilha_de_vendas_de_um_operador(cliente, caixa, loja, vender):
    """Com o filtro de operador, o nome do arquivo e o alto da planilha dizem de quem é."""
    from urllib.parse import quote

    _cenario(cliente, caixa, loja, vender)
    ids = {o["nome"]: o["id"] for o in cliente.get("/api/operadores").json()}
    params = {**_periodo(D1, D3), "operador_id": ids["Caixa de Teste"]}
    resposta, livro = _baixar(cliente, "/api/planilhas/vendas", **params)
    nome = f"Moleka - Vendas (Caixa de Teste) {D1:%d-%m-%Y} a {D3:%d-%m-%Y}.xlsx"
    assert f"filename*=UTF-8''{quote(nome)}" in resposta.headers["content-disposition"]
    assert livro["Resumo"]["A4"].value == "Operador: Caixa de Teste"
    _titulo, linhas = _tabela(livro["Resumo"], "Indicador")
    faturamento = next(linha for linha in linhas if linha[0] == "Faturamento")
    assert (_reais(faturamento[1]), faturamento[2]) == (1070, 1)  # só a venda 5
    desconhecido = cliente.get("/api/planilhas/vendas", params={**params, "operador_id": 9999})
    assert desconhecido.status_code == 404


def test_planilha_de_vendas_por_mes(cliente, loja, vender):
    from tests.test_relatorio_vendas import _vendas_em_dois_meses

    _vendas_em_dois_meses(cliente, loja, vender)
    params = _periodo(date(2026, 9, 1), date(2026, 10, 31))
    _resposta, livro = _baixar(cliente, "/api/planilhas/vendas", **params)
    assert livro.sheetnames[:3] == ["Resumo", "Por dia", "Por mês"]
    _titulo, meses = _tabela(livro["Por mês"], "Mês")
    assert [(m[0], m[1], _reais(m[2]), _reais(m[3]), m[4]) for m in meses] == [
        ("setembro/2026", 1, 2000, 2000, 0),
        ("outubro/2026", 1, 1000, 1000, 1),
        ("Total", 2, 3000, 1500, 1),
    ]
    notas = [c.value for c in livro["Por mês"]["A"] if isinstance(c.value, str)]
    assert "Meses sem venda nem cancelamento não aparecem." in notas
    assert not [n for n in notas if "só a partir" in n or "só até" in n]
    # Cada linha da grade diz quantos daquele dia da semana o período tem.
    _titulo, grade = _tabela(livro["Horários (R$)"], "Dia da semana")
    assert [linha[0] for linha in grade] == [
        "segunda (8)",
        "terça (9)",
        "quarta (9)",
        "quinta (9)",
        "sexta (9)",
        "sábado (9)",
        "domingo (8)",
        "Total",
    ]

    # Primeiro e último mês pela metade: a aba avisa.
    params = _periodo(date(2026, 9, 15), date(2026, 10, 20))
    _resposta, parcial = _baixar(cliente, "/api/planilhas/vendas", **params)
    notas = [c.value for c in parcial["Por mês"]["A"] if isinstance(c.value, str)]
    assert "setembro/2026: só a partir de 15/09/2026." in notas
    assert "outubro/2026: só até 20/10/2026." in notas
    # Um mês só: a aba nem aparece (seria igual ao resumo).
    params = _periodo(date(2026, 10, 1), date(2026, 10, 31))
    _resposta, um_mes = _baixar(cliente, "/api/planilhas/vendas", **params)
    assert "Por mês" not in um_mes.sheetnames


def test_planilha_de_vendas_sem_vendas_mostra_o_motivo(cliente, loja):
    hoje = tempo.hoje()
    _resposta, livro = _baixar(cliente, "/api/planilhas/vendas", **_periodo(hoje, hoje))
    _titulo, dias = _tabela(livro["Por dia"], "Dia")
    assert dias == [["sem vendas no período", None, None, None, None, None]]
    _titulo, linhas = _tabela(livro["Resumo"], "Indicador")
    assert linhas[4][:3] == ["Faturamento", "—", 0]
    _titulo, lista = _tabela(livro["Lista de vendas"], "Nº")
    assert lista[0][0] == "nenhuma venda nem cancelamento no período"


def test_planilha_de_vendas_com_lista_grande_demais(cliente, caixa, loja, vender, monkeypatch):
    from app import relatorios

    _cenario(cliente, caixa, loja, vender)
    monkeypatch.setattr(relatorios, "LIMITE_DA_LISTA", 3)
    _resposta, livro = _baixar(cliente, "/api/planilhas/vendas", **_periodo(D1, D3))
    _titulo, lista = _tabela(livro["Lista de vendas"], "Nº")
    assert lista[0][0].startswith("O período tem 6 vendas, mais do que as 3")
    _titulo, linhas = _tabela(livro["Resumo"], "Indicador")
    assert _reais(linhas[4][1]) == 10750  # o resto da planilha não depende da lista


# ---------------------------------------------------------------- financeiro e estoque


def test_planilhas_do_financeiro_e_do_estoque_tem_os_numeros_da_tela(cliente, caixa, loja, vender):
    _cenario(cliente, caixa, loja, vender)
    params = _periodo(D1, D3)

    dre = cliente.get("/api/financeiro/dre", params=params).json()
    _resposta, livro = _baixar(cliente, "/api/planilhas/dre", **params)
    _titulo, linhas = _tabela(livro["DRE"], "Conta")
    assert [
        (linha[0].strip(), linha[1] if linha[1] == "—" else _reais(linha[1])) for linha in linhas
    ] == [
        (linha["rotulo"], "—" if linha["valor_centavos"] is None else linha["valor_centavos"])
        for linha in dre["linhas"]
    ]

    rent = cliente.get("/api/financeiro/rentabilidade", params=params).json()
    _resposta, livro = _baixar(cliente, "/api/planilhas/rentabilidade", **params)
    _titulo, linhas = _tabela(livro["Rentabilidade"], "Código")
    assert [(linha[1], _reais(linha[4])) for linha in linhas[:-1]] == [
        (linha["descricao"], linha["receita_centavos"]) for linha in rent["linhas"]
    ]
    assert _reais(linhas[-1][4]) == rent["receita_centavos"] == 10750

    fluxo = cliente.get("/api/financeiro/fluxo", params=params).json()
    _resposta, livro = _baixar(cliente, "/api/planilhas/fluxo", **params)
    _titulo, linhas = _tabela(livro["Fluxo de caixa"], "Dia")
    assert [_reais(linha[1]) for linha in linhas[:-1]] == [
        d["vendas_centavos"] for d in fluxo["dias"]
    ]
    assert _reais(linhas[-1][1]) == fluxo["vendas_centavos"]

    contas = cliente.get("/api/financeiro/lancamentos", params=params).json()
    _resposta, livro = _baixar(cliente, "/api/planilhas/contas", **params)
    assert livro.sheetnames == ["Contas", "Totais"]
    _titulo, linhas = _tabela(livro["Contas"], "Vencimento")
    assert len(contas["itens"]) == 0 and linhas == [
        ["nenhum lançamento com este filtro", *[None] * 8]
    ]

    estoque = cliente.get("/api/estoque").json()
    resposta, livro = _baixar(cliente, "/api/planilhas/estoque")
    assert (
        f"Moleka - Estoque {tempo.hoje():%d-%m-%Y}.xlsx".replace(" ", "%20")
        in resposta.headers["content-disposition"]
    )
    _titulo, linhas = _tabela(livro["Estoque"], "Código")
    assert [(linha[1], Decimal(str(linha[4]))) for linha in linhas] == [
        (item["descricao"], Decimal(item["saldo"])) for item in estoque["itens"]
    ]


def test_planilha_de_contas_com_lancamentos(cliente):
    from tests.test_financeiro import _categorias

    cat = _categorias(cliente)
    hoje = tempo.hoje()
    dados = {
        "tipo": "despesa",
        "categoria_id": cat["Aluguel"],
        "descricao": "Aluguel de teste",
        "valor_centavos": 150000,
        "vencimento": hoje.isoformat(),
    }
    assert cliente.post("/api/financeiro/lancamentos", json=dados).status_code == 201
    pago = {
        **dados,
        "descricao": "Luz de teste",
        "valor_centavos": 23456,
        "pago_em": hoje.isoformat(),
    }
    assert cliente.post("/api/financeiro/lancamentos", json=pago).status_code == 201
    _resposta, livro = _baixar(
        cliente, "/api/planilhas/contas", **_periodo(hoje, hoje), tipo="despesa", situacao=""
    )
    contas = livro["Contas"]
    assert contas["A4"].value == "Lista: Só despesas · Em aberto e pagas"
    _titulo, linhas = _tabela(contas, "Vencimento")
    assert sorted((linha[1], _reais(linha[4]), linha[5]) for linha in linhas) == [
        ("Aluguel de teste", 150000, "Em aberto"),
        ("Luz de teste", 23456, "Pago"),
    ]
    _titulo, totais = _tabela(livro["Totais"], "Indicador")
    assert {linha[0]: _reais(linha[1]) for linha in totais}[
        "A pagar (em aberto, com as vencidas)"
    ] == 150000


def test_planilhas_so_do_gerente(caixa, anonimo):
    for caminho in (
        "/api/planilhas/vendas",
        "/api/planilhas/contas",
        "/api/planilhas/fluxo",
        "/api/planilhas/dre",
        "/api/planilhas/rentabilidade",
        "/api/planilhas/estoque",
    ):
        assert caixa.get(caminho).status_code == 403, caminho
        assert anonimo.get(caminho).status_code == 401, caminho


# ---------------------------------------------------------------- o montador de planilhas


def test_texto_que_comeca_com_igual_nao_vira_formula():
    cab = excel.Cabecalho("", "", "Gerente de Teste", "0.0.0", datetime(2026, 11, 12, 10, 0))
    aba = excel.Aba(
        "Teste",
        "Teste",
        [excel.Coluna("Produto"), excel.Coluna("Valor", "dinheiro")],
        [['=HYPERLINK("http://exemplo.invalid")', 1234]],
    )
    livro = load_workbook(io.BytesIO(excel.montar(cab, [aba])))
    _titulo, linhas = _tabela(livro["Teste"], "Produto")
    celula = livro["Teste"].cell(row=6, column=1)  # 1 loja, 2 título, 3 gerada, 5 títulos
    assert (celula.value, celula.data_type) == ('=HYPERLINK("http://exemplo.invalid")', "s")
    assert linhas[0][1] == 12.34
    assert livro["Teste"]["A1"].value == "Moleka PDV"  # sem os dados da loja, nada inventado


def test_nomes_das_abas_e_do_arquivo():
    assert excel.nome_da_aba("Vendas: 01/11 [teste]?") == "Vendas- 01-11 -teste--"
    assert len(excel.nome_da_aba("x" * 40)) == 31
    assert excel.nome_do_arquivo("DRE", date(2026, 11, 1), date(2026, 11, 30)) == (
        "Moleka - DRE 01-11-2026 a 30-11-2026.xlsx"
    )
    assert (
        excel.nome_do_arquivo("Estoque", date(2026, 11, 12)) == "Moleka - Estoque 12-11-2026.xlsx"
    )
    assert (
        excel.nome_do_arquivo('Contas "a/b"', date(2026, 11, 12))
        == "Moleka - Contas -a-b- 12-11-2026.xlsx"
    )
    cab = excel.Cabecalho("Loja", "", "Gerente", "0.0.0", datetime(2026, 11, 12, 10, 0))
    duas = [
        excel.Aba("Mesmo nome", "a", [excel.Coluna("A")], []),
        excel.Aba("mesmo nome", "b", [excel.Coluna("A")], []),
    ]
    assert load_workbook(io.BytesIO(excel.montar(cab, duas))).sheetnames == [
        "Mesmo nome",
        "mesmo nome (2)",
    ]
    with pytest.raises(ValueError, match="tipo de coluna desconhecido"):
        excel.montar(cab, [excel.Aba("x", "x", [excel.Coluna("A", "moeda")], [])])


def test_valores_de_cada_tipo():
    cab = excel.Cabecalho("Loja", "", "Gerente", "0.0.0", datetime(2026, 11, 12, 10, 0))
    colunas = [
        excel.Coluna("Texto"),
        excel.Coluna("Dinheiro", "dinheiro"),
        excel.Coluna("Qtd", "quantidade"),
        excel.Coluna("Inteiro", "inteiro"),
        excel.Coluna("Pct", "porcento"),
        excel.Coluna("Data", "data"),
        excel.Coluna("Hora", "data_hora"),
    ]
    momento = datetime(2026, 11, 12, 23, 30, tzinfo=tempo.FUSO)
    linhas = [
        ["a", -150, Decimal("0.350"), 3, Decimal("12.5"), date(2026, 11, 12), momento],
        ["b", None, Decimal("2.000"), None, None, None, None],
        ["c", "", "", "", "", "", ""],
    ]
    livro = load_workbook(io.BytesIO(excel.montar(cab, [excel.Aba("T", "T", colunas, linhas)])))
    aba = livro["T"]
    _titulo, lidas = _tabela(aba, "Texto")
    assert lidas[0] == [
        "a",
        -1.5,
        0.35,
        3,
        0.125,
        datetime(2026, 11, 12),
        datetime(2026, 11, 12, 23, 30),
    ]
    assert lidas[1] == ["b", "—", 2, "—", "—", "—", "—"]
    assert lidas[2] == ["c", None, None, None, None, None, None]
    assert [aba.cell(row=6, column=n).number_format for n in range(2, 8)] == [
        REAIS,
        "#,##0.000",
        "#,##0",
        "0.0%",
        "dd/mm/yyyy",
        "dd/mm/yyyy hh:mm",
    ]
    assert aba.cell(row=7, column=3).number_format == "#,##0"  # 2,000 é inteiro
    assert aba.freeze_panes == "A6"
    assert aba.auto_filter.ref == "A5:G8"


def test_planilha_aceita_as_datas_do_periodo_vazias(cliente):
    """Sem datas, a planilha usa o mesmo padrão da tela (hoje no relatório de vendas)."""
    resposta, _livro = _baixar(cliente, "/api/planilhas/vendas")
    hoje = tempo.hoje()
    assert (
        f"Moleka - Vendas {hoje:%d-%m-%Y}.xlsx".replace(" ", "%20")
        in resposta.headers["content-disposition"]
    )
    _ = timedelta

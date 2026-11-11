"""O que sai na impressora de cupom: comprovante de venda, resumo do caixa e os bytes ESC/POS.

As linhas esperadas estão escritas uma a uma, com os espaços contados à mão: o papel tem 48
colunas (ou 42, ou 32), o texto fica à esquerda e o valor encosta na última coluna.
"""

from datetime import datetime

from app import config, escpos, impressoras
from app.cupom import Cupom, Linha

LOJA = {
    "nome_fantasia": "Moleka de Teste",
    "razao_social": "Sorveteria Fictícia de Teste Ltda",
    "cnpj": "11222333000181",
    "ie": "123456789",
    "logradouro": "Rua das Flores",
    "numero": "100",
    "bairro": "Centro",
    "cidade": "Cidade de Teste",
    "uf": "RJ",
    "cep": "20040020",
    "telefone": "(21) 5555-0100",
    "rodape": "Obrigado pela preferência!",
}
TRACO = "-" * 48
# O cabeçalho da loja em 48 colunas. Cada linha é centralizada: sobram (48 - tamanho) espaços,
# metade vai para a esquerda (arredondando para baixo).
CABECALHO = [
    " " * 16 + "Moleka de Teste",  # 15 letras: sobram 33, 16 à esquerda
    " " * 7 + "Sorveteria Fictícia de Teste Ltda",  # 33 letras: sobram 15, 7 à esquerda
    " " * 5 + "CNPJ 11.222.333/0001-81  IE 123456789",  # 37: sobram 11, 5 à esquerda
    " " * 10 + "Rua das Flores, 100 - Centro",  # 28: sobram 20
    " " * 6 + "Cidade de Teste - RJ  CEP 20040-020",  # 35: sobram 13
    " " * 14 + "Tel. (21) 5555-0100",  # 19: sobram 29
    TRACO,
]


def _direita(texto, valor, colunas=48):
    """Texto à esquerda e valor encostado na última coluna."""
    return texto + " " * (colunas - len(texto) - len(valor)) + valor


def _impressora(cliente, **mudancas):
    opcoes = {
        "impressora": impressoras.NOME_DE_TESTE,
        "colunas": 48,
        "acentos": "cp850",
        "cortar": True,
        "gaveta": False,
        "quando": "perguntar",
        "vias": 1,
        **mudancas,
    }
    resposta = cliente.put("/api/configuracoes/impressao", json=opcoes)
    assert resposta.status_code == 200, resposta.text


def _hora(iso):
    """A API já devolve a hora da loja: aqui é só mudar o formato."""
    return datetime.fromisoformat(iso).strftime("%d/%m/%Y %H:%M")


def _textos(resposta):
    assert resposta.status_code == 200, resposta.text
    return [linha["texto"] for linha in resposta.json()["linhas"]]


# ---------------------------------------------------------------- ESC/POS


def test_escpos_de_um_cupom_pequeno_byte_a_byte():
    cupom = Cupom(
        "teste",
        32,
        (
            Linha("Picolé de limão", negrito=True),
            Linha("TOTAL  R$ 5,00", grande=True),
            Linha("fim"),
        ),
    )
    assert (
        escpos.codificar(cupom, acentos="cp850", cortar=True)
        == (
            b"\x1b@"  # iniciar
            b"\x1bt\x02"  # página de código 2 = CP850
            b"\x1bE\x01" + "Picolé de limão".encode("cp850") + b"\n"  # negrito ligado
            b"\x1bE\x00"  # negrito desligado
            b"\x1d!\x01" + b"TOTAL  R$ 5,00\n"  # altura dupla
            b"\x1d!\x00" + b"fim\n"  # tamanho normal
            b"\x1bE\x00\x1d!\x00"  # deixa a impressora no normal
            b"\x1dVB\x00"  # avança e corta
        )
    )
    # No CP850, "é" é 0x82 e "ã" é 0xC6.
    assert "Picolé de limão".encode("cp850") == b"Picol\x82 de lim\xc6o"
    sem_corte = escpos.codificar(cupom, acentos="sem", cortar=False)
    assert sem_corte.startswith(b"\x1b@\x1bE\x01Picole de limao\n")  # sem página de código
    assert sem_corte.endswith(b"\n\n\n\n\n")  # sobe o papel para rasgar
    duas = escpos.codificar(cupom, acentos="cp860", cortar=True, vias=2)
    uma = escpos.codificar(cupom, acentos="cp860", cortar=True)
    assert duas == uma + uma and b"\x1bt\x03" in uma  # CP860 é a página 3
    com_gaveta = escpos.codificar(
        Cupom("t", 32, (Linha("x"),), abre_gaveta=True), acentos="cp1252", cortar=True
    )
    assert com_gaveta.startswith(b"\x1bp\x00\x19\xfa\x1b@\x1bt\x10")  # pulso da gaveta primeiro


def test_letra_que_a_pagina_de_codigo_nao_tem_sai_sem_acento():
    assert escpos.texto_em_bytes("ação", "cp850") == b"a\x87\xc6o"
    assert escpos.texto_em_bytes("ação nº 1 — “ok”…", "sem") == b'acao no 1 - "ok"...'
    assert escpos.texto_em_bytes("€ 5", "cp850") == b"? 5"  # o que não tem troca vira "?"
    assert escpos.texto_em_bytes("Ã", "cp860") == b"\x8e"


# ---------------------------------------------------------------- comprovante de venda


def test_comprovante_de_venda_linha_por_linha(cliente, loja, vender, impressora_de_teste):
    assert cliente.put("/api/configuracoes/loja", json=LOJA).status_code == 200
    assert (
        cliente.put(
            "/api/formas-pagamento/pix", json={"ajuste_bp": -500, "ativo": True}
        ).status_code
        == 200
    )
    # 10 picolés a 4,50 = 45,00; 0,5 kg de sorvete a 59,90 = 29,95. Subtotal 74,95.
    # Desconto do gerente 4,95 -> 70,00. No Pix, 5% de desconto = 3,50. Total 66,50.
    venda = vender([(loja["picole"], 10), (loja["sorvete"], "0.5")], "pix", desconto_centavos=495)
    assert venda["total_centavos"] == 6650

    visto = cliente.get(f"/api/vendas/{venda['id']}/comprovante")
    assert _textos(visto) == [
        *CABECALHO,
        " " * 14 + "COMPROVANTE DE VENDA",  # 20 letras: sobram 28
        " " * 13 + "NÃO É DOCUMENTO FISCAL",  # 22 letras: sobram 26
        TRACO,
        _direita("Venda nº 1", _hora(venda["finalizada_em"])),
        "Operador: Gerente de Teste",
        TRACO,
        "001 Picolé de teste",
        _direita("    10 UN x 4,50", "45,00"),
        "002 Sorvete de teste por quilo",
        _direita("    0,5 KG x 59,90", "29,95"),
        TRACO,
        _direita("Subtotal", "74,95"),
        _direita("Desconto", "-4,95"),
        _direita("Desconto no Pix", "-3,50"),
        _direita("TOTAL", "R$ 66,50"),
        TRACO,
        _direita("Pix", "66,50"),
        TRACO,
        " " * 11 + "Obrigado pela preferência!",  # 26 letras: sobram 22
        (" " * ((48 - len(f"Moleka PDV {config.VERSAO}")) // 2)) + f"Moleka PDV {config.VERSAO}",
    ]
    linhas = visto.json()["linhas"]
    assert all(len(linha["texto"]) <= 48 for linha in linhas)
    destaque = {x["texto"].strip(): (x["negrito"], x["grande"]) for x in linhas}
    assert destaque["Moleka de Teste"] == (True, True)
    assert destaque["COMPROVANTE DE VENDA"] == (True, False)
    assert destaque[_direita("TOTAL", "R$ 66,50")] == (True, True)
    assert destaque["Operador: Gerente de Teste"] == (False, False)
    assert (visto.json()["colunas"], visto.json()["titulo"]) == (48, "Moleka - venda 1")
    # Sem impressora escolhida: a tela mostra o comprovante, mas não imprime, e diz por quê.
    assert visto.json()["pode_imprimir"] is False and "Nenhuma impressora" in visto.json()["motivo"]
    sem_impressora = cliente.post(f"/api/vendas/{venda['id']}/imprimir")
    assert (
        sem_impressora.status_code == 409
        and "Nenhuma impressora" in sem_impressora.json()["detail"]
    )

    _impressora(cliente, vias=2)
    assert cliente.get(f"/api/vendas/{venda['id']}/comprovante").json()["pode_imprimir"] is True
    impresso = cliente.post(f"/api/vendas/{venda['id']}/imprimir")
    assert impresso.status_code == 200, impresso.text
    assert impresso.json() == {"impressora": impressoras.NOME_DE_TESTE, "vias": 2}
    enviado = next(impressora_de_teste.glob("*.bin")).read_bytes()
    metade = len(enviado) // 2
    assert enviado[:metade] == enviado[metade:]  # duas vias iguais
    via = enviado[:metade]
    assert via.startswith(b"\x1b@\x1bt\x02") and via.endswith(b"\x1dVB\x00")
    # O que foi para a impressora é o que a tela mostrou: tirando os comandos, sobram as linhas.
    for comando in (b"\x1b@", b"\x1bt\x02", b"\x1bE\x01", b"\x1bE\x00", b"\x1d!\x01", b"\x1d!\x00"):
        via = via.replace(comando, b"")
    via = via.removesuffix(b"\x1dVB\x00")
    assert via.decode("cp850").splitlines() == _textos(visto)
    assert not via.startswith(b"\x1bp")  # reimpressão não abre a gaveta


def test_comprovante_em_dinheiro_mostra_o_que_o_cliente_deu_e_o_troco(cliente, loja):
    cliente.post("/api/venda/itens", json={"produto_id": loja["picole"], "quantidade": 1})
    cliente.post("/api/venda/pagamentos", json={"forma": "dinheiro", "valor_centavos": 1000})
    venda = cliente.post("/api/venda/finalizar", json={}).json()["venda"]
    textos = _textos(cliente.get(f"/api/vendas/{venda['id']}/comprovante"))
    # Loja sem dados: o cupom começa direto no título (nenhum cabeçalho inventado).
    assert textos[0] == " " * 14 + "COMPROVANTE DE VENDA"
    assert textos[-9:] == [
        "001 Picolé de teste",
        _direita("    1 UN x 5,00", "5,00"),
        TRACO,
        _direita("TOTAL", "R$ 5,00"),  # sem desconto, não há linha de subtotal
        TRACO,
        _direita("Dinheiro", "10,00"),  # o que o cliente entregou
        _direita("Troco", "5,00"),
        TRACO,
        (" " * ((48 - len(f"Moleka PDV {config.VERSAO}")) // 2)) + f"Moleka PDV {config.VERSAO}",
    ]


def test_comprovante_em_papel_estreito_quebra_a_descricao(
    cliente, loja, vender, impressora_de_teste
):
    _impressora(cliente, colunas=32)
    produto = cliente.post(
        "/api/produtos",
        json={
            "descricao": "Sorvete de creme com cobertura de chocolate belga",
            "precos": [{"tabela_id": loja["varejo"], "qtd_min": "1", "preco_centavos": 123456}],
        },
    ).json()
    venda = vender([(produto["id"], 2)])
    textos = _textos(cliente.get(f"/api/vendas/{venda['id']}/comprovante"))
    assert all(len(t) <= 32 for t in textos)
    inicio = textos.index("001 Sorvete de creme com")
    assert textos[inicio : inicio + 4] == [
        "001 Sorvete de creme com",  # a descrição quebra em 28 colunas (32 - 4 do número)
        "    cobertura de chocolate belga",
        _direita("    2 UN x 1.234,56", "2.469,12", 32),
        "-" * 32,
    ]


def test_venda_cancelada_sai_marcada_e_venda_aberta_nao_imprime(cliente, loja, vender):
    venda = vender([(loja["picole"], 1)])
    cancelada = cliente.post(
        f"/api/vendas/{venda['id']}/cancelar", json={"motivo": "cliente desistiu"}
    )
    assert cancelada.status_code == 200, cancelada.text
    textos = _textos(cliente.get(f"/api/vendas/{venda['id']}/comprovante"))
    assert " " * 12 + "*** VENDA CANCELADA ***" in textos  # 23 letras: sobram 25
    assert "Motivo: cliente desistiu" in textos

    aberta = cliente.post("/api/venda/itens", json={"produto_id": loja["agua"], "quantidade": 1})
    numero = aberta.json()["venda"]["id"]
    assert cliente.get(f"/api/vendas/{numero}/comprovante").status_code == 409
    assert cliente.post(f"/api/vendas/{numero}/imprimir").status_code == 409
    assert cliente.get("/api/vendas/99999/comprovante").status_code == 404


# ---------------------------------------------------------------- depois da venda


def _vender_em(cliente, produto, forma, valor=None):
    cliente.post("/api/venda/itens", json={"produto_id": produto, "quantidade": 1})
    pagamento = {"forma": forma} if valor is None else {"forma": forma, "valor_centavos": valor}
    cliente.post("/api/venda/pagamentos", json=pagamento)
    final = cliente.post("/api/venda/finalizar", json={})
    assert final.status_code == 200, final.text
    return final.json()


def test_depois_da_venda_imprime_sozinho_ou_so_abre_a_gaveta(cliente, loja, impressora_de_teste):
    def arquivos():
        return sorted(impressora_de_teste.glob("*.bin"))

    # Sem impressora: nada acontece, e a resposta diz que não há impressora.
    sem = _vender_em(cliente, loja["picole"], "dinheiro")
    assert sem["depois"] == {"impressora": "", "quando": "perguntar", "enviado": False, "erro": ""}
    assert arquivos() == []

    # "Perguntar": não imprime sozinho. Com a gaveta ligada, a venda em dinheiro manda só o pulso.
    _impressora(cliente, gaveta=True)
    perguntar = _vender_em(cliente, loja["picole"], "dinheiro", 1000)
    assert perguntar["depois"] == {
        "impressora": impressoras.NOME_DE_TESTE,
        "quando": "perguntar",
        "enviado": False,
        "erro": "",
    }
    assert [a.read_bytes() for a in arquivos()] == [b"\x1bp\x00\x19\xfa"]
    _vender_em(cliente, loja["picole"], "pix")  # no Pix a gaveta não abre
    assert len(arquivos()) == 1

    # "Sempre": o comprovante sai sozinho; em dinheiro, com o pulso da gaveta na frente.
    _impressora(cliente, gaveta=True, quando="sempre")
    sempre = _vender_em(cliente, loja["picole"], "dinheiro", 500)
    assert sempre["depois"]["enviado"] is True and sempre["depois"]["erro"] == ""
    assert sempre["venda"]["status"] == "finalizada"
    ultimo = arquivos()[-1].read_bytes()
    assert ultimo.startswith(b"\x1bp\x00\x19\xfa\x1b@") and b"COMPROVANTE DE VENDA" in ultimo
    no_pix = _vender_em(cliente, loja["picole"], "pix")
    assert no_pix["depois"]["enviado"] is True
    assert arquivos()[-1].read_bytes().startswith(b"\x1b@")  # comprovante sem abrir a gaveta
    assert len(arquivos()) == 3

    # "Nunca" com a gaveta desligada: nada vai para a impressora.
    _impressora(cliente, quando="nunca")
    nunca = _vender_em(cliente, loja["picole"], "dinheiro")
    assert nunca["depois"]["enviado"] is False and len(arquivos()) == 3


def test_impressora_com_defeito_nao_desfaz_a_venda(cliente, loja, impressora_de_teste, monkeypatch):
    from app.operadores import RegraError

    _impressora(cliente, quando="sempre")

    def quebrada(nome, dados, titulo):
        raise RegraError("Não consegui imprimir: a impressora foi removida do Windows.", status=409)

    monkeypatch.setattr(impressoras, "enviar", quebrada)
    feita = _vender_em(cliente, loja["picole"], "dinheiro")
    assert feita["venda"]["status"] == "finalizada"  # a venda está gravada
    assert feita["depois"]["enviado"] is False
    assert "a impressora foi removida do Windows" in feita["depois"]["erro"]
    assert cliente.get("/api/vendas/resumo-hoje").json()["quantidade"] == 1
    # Pedindo de novo, o erro aparece para quem pediu.
    de_novo = cliente.post(f"/api/vendas/{feita['venda']['id']}/imprimir")
    assert de_novo.status_code == 409 and "removida do Windows" in de_novo.json()["detail"]


# ---------------------------------------------------------------- resumo do caixa


def test_resumo_do_caixa_aberto_e_fechado(cliente, loja, caixa, impressora_de_teste):
    cliente.put("/api/formas-pagamento/pix", json={"ajuste_bp": -500, "ativo": True})
    # Fundo 100,00 (da loja de teste). Suprimento 50,00 e sangria 20,00.
    for tipo, valor, motivo in (("suprimento", 5000, "troco"), ("sangria", 2000, "depósito")):
        feito = cliente.post(
            "/api/caixa/movimentos", json={"tipo": tipo, "valor_centavos": valor, "motivo": motivo}
        )
        assert feito.status_code == 201, feito.text
    # Vendas: 1 picolé em dinheiro (5,00) e 10 picolés no Pix (45,00 - 5% = 42,75).
    _vender_em(cliente, loja["picole"], "dinheiro", 1000)
    cliente.post("/api/venda/itens", json={"produto_id": loja["picole"], "quantidade": 10})
    cliente.post("/api/venda/pagamentos", json={"forma": "pix"})
    assert cliente.post("/api/venda/finalizar", json={}).status_code == 200

    aberto = _textos(cliente.get("/api/caixa/resumo-impresso"))
    assert aberto[0] == " " * 9 + "RESUMO DO CAIXA (AINDA ABERTO)"  # 30 letras: sobram 18
    meio = aberto.index(_direita("Vendas finalizadas", "2"))
    assert aberto[meio : meio + 17] == [
        _direita("Vendas finalizadas", "2"),
        _direita("Total vendido", "47,75"),
        TRACO,
        "RECEBIDO POR FORMA",
        _direita("Dinheiro", "5,00"),
        _direita("Pix", "42,75"),
        _direita("Débito", "0,00"),
        _direita("Crédito", "0,00"),
        TRACO,
        "DINHEIRO NA GAVETA",
        _direita("Fundo de troco", "100,00"),
        _direita("(+) Vendas em dinheiro", "5,00"),
        _direita("(+) Suprimentos", "50,00"),
        _direita("(-) Sangrias", "20,00"),
        _direita("(=) Esperado", "135,00"),  # 100 + 5 + 50 - 20
        TRACO,
        "SANGRIAS E SUPRIMENTOS",
    ]
    assert "CONFERÊNCIA" not in aberto  # só existe depois de fechar
    assert any(t.endswith("Suprimento" + " " * (48 - 16 - 5) + "50,00") for t in aberto)
    # O motivo é gravado com o nome de quem fez.
    assert "  troco (Gerente de Teste)" in aberto and "  depósito (Gerente de Teste)" in aberto
    # O operador comum também vê e imprime o caixa aberto.
    assert caixa.get("/api/caixa/resumo-impresso").status_code == 200

    # Fechamento: no dinheiro foram contados 134,00 (falta 1,00); o resto bate.
    contado = {"dinheiro": 13400, "pix": 4275, "debito": 0, "credito": 0}
    fechado = cliente.post("/api/caixa/fechar", json={"contado": contado, "observacao": "teste"})
    assert fechado.status_code == 200, fechado.text
    sessao_id = fechado.json()["id"]
    assert cliente.get("/api/caixa/resumo-impresso").status_code == 409  # não há caixa aberto
    textos = _textos(cliente.get("/api/caixa/resumo-impresso", params={"sessao_id": sessao_id}))
    assert textos[0] == " " * 14 + "FECHAMENTO DE CAIXA"  # 19 letras: sobram 29
    inicio = textos.index("CONFERÊNCIA")
    assert textos[inicio : inicio + 9] == [
        "CONFERÊNCIA",
        "Dinheiro",
        _direita("  Esperado", "135,00"),
        _direita("  Contado", "134,00"),
        _direita("  Diferença", "-1,00"),
        "Pix",
        _direita("  Esperado", "42,75"),
        _direita("  Contado", "42,75"),
        _direita("  Diferença", "0,00"),
    ]
    assert "Observação: teste" in textos
    # Quem não fechou este caixa e não é gerente não imprime o fechamento dos outros.
    assert (
        caixa.get("/api/caixa/resumo-impresso", params={"sessao_id": sessao_id}).status_code == 403
    )
    assert caixa.post("/api/caixa/imprimir", json={"sessao_id": sessao_id}).status_code == 403
    assert cliente.get("/api/caixa/resumo-impresso", params={"sessao_id": 999}).status_code == 404

    _impressora(cliente, vias=2)
    impresso = cliente.post("/api/caixa/imprimir", json={"sessao_id": sessao_id})
    assert impresso.status_code == 200 and impresso.json()["vias"] == 1  # o resumo sai em uma via
    enviado = sorted(impressora_de_teste.glob("*.bin"))[-1].read_bytes()
    assert "FECHAMENTO DE CAIXA".encode("cp850") in enviado and enviado.count(b"\x1b@") == 1

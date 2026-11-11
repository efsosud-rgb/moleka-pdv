"""Configurações: dados da loja e impressora de cupom. Todos os dados são fictícios."""

import sys

import pytest

from app import impressoras
from app.operadores import RegraError

LOJA = {
    "nome_fantasia": "  Moleka   de Teste ",
    "razao_social": "Sorveteria Fictícia de Teste Ltda",
    "cnpj": "11.222.333/0001-81",
    "ie": "isento",
    "logradouro": "Rua das Flores",
    "numero": "100",
    "bairro": "Centro",
    "cidade": "Cidade de Teste",
    "uf": "rj",
    "cep": "20040-020",
    "telefone": "(21) 5555-0100",
    "rodape": "Obrigado pela preferência!",
}


def test_comecam_vazias_e_com_os_padroes(cliente):
    tudo = cliente.get("/api/configuracoes").json()
    assert set(tudo["loja"].values()) == {""}  # nada inventado: a loja começa em branco
    assert tudo["impressao"] == {
        "impressora": "",
        "colunas": 48,
        "acentos": "cp850",
        "cortar": True,
        "gaveta": False,
        "quando": "perguntar",
        "vias": 1,
        "confirmada": False,
    }
    assert (tudo["backup"]["pasta_extra"], tudo["backup"]["manter"]) == ("", 30)
    assert tudo["backup"]["copias"] == []
    assert len(tudo["ufs"]) == 27 and tudo["colunas"] == [48, 42, 32]
    assert [o["valor"] for o in tudo["acentos"]] == ["cp850", "cp860", "cp1252", "sem"]
    assert [o["valor"] for o in tudo["quando"]] == ["perguntar", "sempre", "nunca"]


def test_dados_da_loja_sao_limpos_e_conferidos(cliente):
    gravada = cliente.put("/api/configuracoes/loja", json=LOJA)
    assert gravada.status_code == 200, gravada.text
    assert gravada.json() == {
        **LOJA,
        "nome_fantasia": "Moleka de Teste",  # espaços sobrando saem
        "cnpj": "11222333000181",  # só os números
        "ie": "ISENTO",
        "uf": "RJ",
        "cep": "20040020",
    }
    assert cliente.get("/api/configuracoes").json()["loja"] == gravada.json()

    def recusa(campo, valor, trecho):
        resposta = cliente.put("/api/configuracoes/loja", json={**LOJA, campo: valor})
        assert resposta.status_code == 422, resposta.text
        assert trecho in resposta.json()["detail"], resposta.json()["detail"]

    recusa("cnpj", "11.222.333/0001-80", "CNPJ inválido")  # dígito final errado
    recusa("cnpj", "123", "CNPJ inválido")
    recusa("cep", "2004002", "CEP inválido")
    recusa("uf", "XX", "Estado (UF) inválido")
    recusa("ie", "abc123", "Inscrição estadual")
    recusa("nome_fantasia", "x" * 61, "Nome da loja: no máximo 60")
    # Nada do que foi recusado ficou gravado.
    assert cliente.get("/api/configuracoes").json()["loja"] == gravada.json()
    # Tudo é opcional: dá para apagar um campo.
    sem_cnpj = cliente.put("/api/configuracoes/loja", json={**LOJA, "cnpj": ""})
    assert sem_cnpj.status_code == 200 and sem_cnpj.json()["cnpj"] == ""


def _impressao(**mudancas):
    return {
        "impressora": impressoras.NOME_DE_TESTE,
        "colunas": 42,
        "acentos": "cp850",
        "cortar": True,
        "gaveta": False,
        "quando": "perguntar",
        "vias": 1,
        **mudancas,
    }


def test_impressora_escolhida_so_fica_ok_depois_do_teste_confirmado(cliente, impressora_de_teste):
    lista = cliente.get("/api/impressoras").json()
    assert lista == {
        "disponivel": True,
        "motivo": "",
        "impressoras": [{"nome": impressoras.NOME_DE_TESTE, "padrao": True}],
    }
    status = cliente.get("/api/status").json()["impressora_cupom"]
    assert (status["ok"], status["motivo"]) == (False, "nenhuma impressora de cupom escolhida")

    de_fora = cliente.put("/api/configuracoes/impressao", json=_impressao(impressora="Outra"))
    assert de_fora.status_code == 422 and "não está instalada" in de_fora.json()["detail"]
    # Sem impressora escolhida, o teste não tem para onde ir.
    assert cliente.post("/api/impressao/teste").status_code == 409

    escolhida = cliente.put("/api/configuracoes/impressao", json=_impressao())
    assert escolhida.status_code == 200, escolhida.text
    assert escolhida.json() == {**_impressao(), "confirmada": False}
    status = cliente.get("/api/status").json()["impressora_cupom"]
    assert (status["ok"], status["estado"]) == (False, "não testada")
    assert impressoras.NOME_DE_TESTE in status["motivo"]

    teste = cliente.post("/api/impressao/teste")
    assert teste.status_code == 200, teste.text
    assert teste.json()["impressora"] == impressoras.NOME_DE_TESTE
    arquivos = sorted(impressora_de_teste.glob("*.bin"))
    assert [a.name for a in arquivos] == ["impressao-001.bin"]
    enviado = arquivos[0].read_bytes()
    assert enviado.startswith(b"\x1b@\x1bt\x02")  # iniciar + página de código CP850
    assert enviado.endswith(b"\x1dVB\x00")  # corte
    assert "TESTE DE IMPRESSÃO".encode("cp850") in enviado
    assert b"\n123456789012345678901234567890123456789012\n" in enviado  # régua de 42 colunas
    assert "á é í ó ú â ê ô ã õ à ç Á É Ç Ã Õ".encode("cp850") in enviado
    # Mandar para a fila não é prova de que saiu no papel: continua "não testada".
    assert cliente.get("/api/status").json()["impressora_cupom"]["ok"] is False

    confirmada = cliente.post("/api/impressao/teste/confirmar", json={"saiu": True})
    assert confirmada.status_code == 200 and confirmada.json()["confirmada"] is True
    status = cliente.get("/api/status").json()["impressora_cupom"]
    assert (status["ok"], status["texto"]) == (True, impressoras.NOME_DE_TESTE)

    # Mudar o que não afeta o papel mantém a confirmação; mudar colunas ou acentos, não.
    mesma = cliente.put("/api/configuracoes/impressao", json=_impressao(quando="sempre", vias=2))
    assert mesma.json()["confirmada"] is True
    outra_largura = cliente.put("/api/configuracoes/impressao", json=_impressao(colunas=48))
    assert outra_largura.json()["confirmada"] is False
    cliente.post("/api/impressao/teste/confirmar", json={"saiu": True})
    outros_acentos = cliente.put(
        "/api/configuracoes/impressao", json=_impressao(colunas=48, acentos="sem")
    )
    assert outros_acentos.json()["confirmada"] is False
    # O gerente pode dizer que o teste NÃO saiu.
    cliente.post("/api/impressao/teste/confirmar", json={"saiu": True})
    nao_saiu = cliente.post("/api/impressao/teste/confirmar", json={"saiu": False})
    assert nao_saiu.json()["confirmada"] is False

    for campo, valor, trecho in (
        ("colunas", 40, "Colunas"),
        ("acentos", "utf8", "Acentos"),
        ("quando", "talvez", "Quando imprimir"),
        ("vias", 3, "Vias"),
    ):
        recusada = cliente.put("/api/configuracoes/impressao", json=_impressao(**{campo: valor}))
        assert recusada.status_code == 422 and trecho in recusada.json()["detail"], campo

    sem = cliente.put("/api/configuracoes/impressao", json=_impressao(impressora=""))
    assert sem.status_code == 200 and sem.json()["confirmada"] is False
    status = cliente.get("/api/status").json()["impressora_cupom"]
    assert status["motivo"] == "nenhuma impressora de cupom escolhida"
    assert cliente.post("/api/impressao/teste/confirmar", json={"saiu": True}).status_code == 409


def test_onde_nao_da_para_imprimir_a_tela_fica_sabendo(cliente, monkeypatch):
    motivo = "A impressão do cupom funciona só no Windows."
    monkeypatch.setattr(impressoras, "disponivel", lambda: (False, motivo))
    lista = cliente.get("/api/impressoras").json()
    assert lista == {"disponivel": False, "motivo": motivo, "impressoras": []}
    recusada = cliente.put("/api/configuracoes/impressao", json=_impressao())
    assert recusada.status_code == 409 and recusada.json()["detail"] == motivo
    # Sem impressora continua dando para gravar as outras opções.
    assert (
        cliente.put("/api/configuracoes/impressao", json=_impressao(impressora="")).status_code
        == 200
    )


def test_windows_sem_impressora_instalada(cliente, monkeypatch):
    monkeypatch.setattr(impressoras, "disponivel", lambda: (True, ""))
    monkeypatch.setattr(impressoras, "listar", lambda: [])
    lista = cliente.get("/api/impressoras").json()
    assert lista["disponivel"] is True and lista["impressoras"] == []
    assert lista["motivo"] == "O Windows não tem nenhuma impressora instalada."


def test_quando_o_windows_nao_entrega_a_lista_a_tela_mostra_o_motivo(cliente, monkeypatch):
    """Lista vazia por falha não pode aparecer como "nenhuma impressora instalada"."""
    from app.operadores import RegraError

    def falha():
        raise RegraError("O Windows não entregou a lista de impressoras: erro 1722.", status=500)

    monkeypatch.setattr(impressoras, "disponivel", lambda: (True, ""))
    monkeypatch.setattr(impressoras, "listar", falha)
    lista = cliente.get("/api/impressoras")
    assert lista.status_code == 200
    assert lista.json() == {
        "disponivel": False,
        "motivo": "O Windows não entregou a lista de impressoras: erro 1722.",
        "impressoras": [],
    }


def test_impressora_de_teste_grava_um_arquivo_por_impressao(impressora_de_teste):
    assert impressoras.disponivel() == (True, "")
    impressoras.enviar(impressoras.NOME_DE_TESTE, b"um", "primeiro")
    impressoras.enviar(impressoras.NOME_DE_TESTE, b"dois", "segundo")
    arquivos = sorted(impressora_de_teste.glob("*.bin"))
    assert [(a.name, a.read_bytes()) for a in arquivos] == [
        ("impressao-001.bin", b"um"),
        ("impressao-002.bin", b"dois"),
    ]
    with pytest.raises(RegraError, match="não existe neste computador"):
        impressoras.enviar("Outra impressora", b"x", "t")
    with pytest.raises(RegraError, match="Nenhuma impressora"):
        impressoras.enviar("", b"x", "t")
    with pytest.raises(RegraError, match="Não há o que imprimir"):
        impressoras.enviar(impressoras.NOME_DE_TESTE, b"", "t")


@pytest.mark.skipif(sys.platform != "win32", reason="fila de impressão do Windows")
def test_no_windows_lista_as_impressoras_e_recusa_a_que_nao_existe(monkeypatch):
    monkeypatch.delenv("MOLEKA_PDV_IMPRESSORA_EM_ARQUIVO", raising=False)
    assert impressoras.disponivel() == (True, "")
    lista = impressoras.listar()  # o que houver neste Windows; pode ser nenhuma
    assert all(i.nome for i in lista)
    assert [i.nome for i in lista] == sorted((i.nome for i in lista), key=str.casefold)
    assert sum(1 for i in lista if i.padrao) <= 1
    with pytest.raises(RegraError, match="Não consegui imprimir"):
        impressoras.enviar("Impressora que não existe 12345", b"teste", "Moleka - teste")


@pytest.mark.parametrize(
    ("metodo", "caminho", "corpo"),
    [
        ("get", "/api/configuracoes", None),
        ("put", "/api/configuracoes/loja", LOJA),
        ("get", "/api/impressoras", None),
        ("put", "/api/configuracoes/impressao", _impressao()),
        ("post", "/api/impressao/teste", None),
        ("post", "/api/impressao/teste/confirmar", {"saiu": True}),
        ("put", "/api/configuracoes/backup", {"pasta_extra": "", "manter": 30}),
        ("post", "/api/backup", None),
    ],
)
def test_so_o_gerente_mexe_nas_configuracoes(anonimo, caixa, metodo, caminho, corpo):
    extras = {} if corpo is None else {"json": corpo}
    assert getattr(anonimo, metodo)(caminho, **extras).status_code == 401
    assert getattr(caixa, metodo)(caminho, **extras).status_code == 403

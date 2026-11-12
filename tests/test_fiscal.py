"""Configurações → Fiscal (NFC-e) pela API: dados fiscais da empresa, certificado A1, CSC,
numeração, contador e dados fiscais dos produtos.

Tudo é fictício: a loja, o contador, os códigos CSC e os certificados
(tests/certificado_ficticio.py).
Esta versão não emite NFC-e; os testes conferem que os dados ficam prontos, conferidos e que os
segredos nunca voltam pela API nem vão para o banco, o log ou a cópia de segurança.
"""

import base64
import logging

import pytest
from certificado_ficticio import CNPJ, SENHA, TITULAR, gerar

from app import db
from app.models import Configuracao, DocumentoFiscal

LOJA = {
    "nome_fantasia": "Moleka de Teste",
    "razao_social": "Empresa Ficticia de Teste Ltda",
    "cnpj": CNPJ,
    "ie": "111222333444",
    "logradouro": "Rua das Flores",
    "numero": "100",
    "bairro": "Centro",
    "cidade": "São Paulo",
    "uf": "SP",
    "cep": "01001-000",
    "telefone": "",
    "rodape": "",
}
CSC_HOMOLOGACAO = "CSCFICTICIOHOMOLOGACAO0001"
CSC_PRODUCAO = "CSCFICTICIOPRODUCAO000002"
EMPRESA = {
    "crt": "1",
    "codigo_municipio": "3550308",
    "inscricao_municipal": "",
    "cnae": "4721-1/04",
    "credenciada": "sim",
    "emite_hoje": "nao",
    "emite_hoje_detalhe": "",
}


@pytest.fixture()
def padroes(cliente):
    """O que o programa cria ao abrir pela primeira vez: VAREJO, ATACADO e o Caixa 01."""
    db.semear_padroes()


def _situacoes(fiscal):
    return {p["chave"]: p["situacao"] for p in fiscal["pendencias"]}


def _detalhe(fiscal, chave):
    return next(p["detalhe"] for p in fiscal["pendencias"] if p["chave"] == chave)


def _instalar(cliente, conteudo=None, senha=SENHA, nome="C:\\Certificados\\empresa.pfx"):
    corpo = {
        "nome_arquivo": nome,
        "conteudo_base64": base64.b64encode(gerar() if conteudo is None else conteudo).decode(),
        "senha": senha,
    }
    return cliente.post("/api/fiscal/certificado", json=corpo)


def _gravar_loja(cliente, **mudancas):
    resposta = cliente.put("/api/configuracoes/loja", json={**LOJA, **mudancas})
    assert resposta.status_code == 200, resposta.text


def test_comeca_em_branco_e_diz_o_que_falta(cliente, padroes):
    fiscal = cliente.get("/api/fiscal").json()
    assert "ainda não emite NFC-e" in fiscal["aviso"]
    assert fiscal["ambiente"] == "homologacao"
    assert set(fiscal["empresa"].values()) == {""}  # nada inventado
    assert set(fiscal["contador"].values()) == {""}
    assert fiscal["certificado"] is None
    assert [(c["ambiente"], c["id"], c["salvo"], c["final"]) for c in fiscal["csc"]] == [
        ("homologacao", "", False, ""),
        ("producao", "", False, ""),
    ]
    assert [(n["caixa"], n["serie"], n["proximo_numero"]) for n in fiscal["numeracao"]] == [
        ("Caixa 01", 1, 1)
    ]
    assert fiscal["numeracao"][0]["ultima_registrada"] is None
    assert fiscal["categorias"] == []
    assert _situacoes(fiscal) == {
        "loja": "falta",
        "regime": "falta",
        "municipio": "falta",
        "credenciamento": "atencao",
        "certificado": "falta",
        "csc_homologacao": "falta",
        "csc_producao": "atencao",
        "numeracao": "atencao",
        "produtos": "atencao",
        "contador": "atencao",
    }
    assert fiscal["faltam"] == 5
    assert _detalhe(fiscal, "loja").startswith("Falta: razão social, CNPJ, inscrição estadual")
    assert [o["valor"] for o in fiscal["crts"]] == ["1", "4", "2", "3"]
    assert "5405" in [o["valor"] for o in fiscal["cfops"]]


def test_dados_fiscais_da_empresa_sao_conferidos(cliente):
    _gravar_loja(cliente, uf="RJ")
    base = {**EMPRESA, "codigo_municipio": ""}
    for mudanca, trecho in [
        ({"codigo_municipio": "355030"}, "são 7 números"),
        ({"codigo_municipio": "9950308"}, "nenhum estado"),
        ({"codigo_municipio": "3550308"}, "é de uma cidade de SP, mas o estado da loja"),
        ({"crt": "9"}, "Regime tributário"),
        ({"cnae": "47211"}, "CNAE"),
        ({"credenciada": "talvez"}, "Sim, Não ou Não sei"),
        ({"inscricao_municipal": "12#34"}, "Inscrição municipal"),
    ]:
        resposta = cliente.put("/api/fiscal/empresa", json={**base, **mudanca})
        assert resposta.status_code == 422, mudanca
        assert trecho in resposta.json()["detail"], resposta.json()["detail"]
    _gravar_loja(cliente)  # volta para SP
    resposta = cliente.put(
        "/api/fiscal/empresa", json={**EMPRESA, "inscricao_municipal": " 1.234.567-8 "}
    )
    assert resposta.status_code == 200, resposta.text
    fiscal = resposta.json()
    assert fiscal["empresa"]["cnae"] == "4721104"
    assert fiscal["empresa"]["inscricao_municipal"] == "1.234.567-8"
    situacoes = _situacoes(fiscal)
    assert (situacoes["loja"], situacoes["regime"], situacoes["municipio"]) == ("ok", "ok", "ok")
    assert situacoes["credenciamento"] == "ok"
    # Trocar o estado da loja depois faz o código do município voltar para a lista do que falta.
    _gravar_loja(cliente, uf="RJ")
    fiscal = cliente.get("/api/fiscal").json()
    assert _situacoes(fiscal)["municipio"] == "falta"
    assert "é de SP, mas o estado da loja é RJ" in _detalhe(fiscal, "municipio")


def test_inscricao_estadual_isento_pede_atencao(cliente):
    _gravar_loja(cliente, ie="ISENTO")
    fiscal = cliente.get("/api/fiscal").json()
    assert _situacoes(fiscal)["loja"] == "atencao"


def test_credenciamento_nao_entra_no_que_falta(cliente):
    cliente.put("/api/fiscal/empresa", json={**EMPRESA, "credenciada": "nao"})
    fiscal = cliente.get("/api/fiscal").json()
    assert _situacoes(fiscal)["credenciamento"] == "falta"
    assert "credenciar" in _detalhe(fiscal, "credenciamento")


def test_csc_fica_guardado_fora_do_banco_e_nunca_volta_inteiro(cliente, tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    corpo = {
        "id_homologacao": "000001",
        "codigo_homologacao": CSC_HOMOLOGACAO,
        "id_producao": "2",
        "codigo_producao": CSC_PRODUCAO,
    }
    resposta = cliente.put("/api/fiscal/csc", json=corpo)
    assert resposta.status_code == 200, resposta.text
    assert CSC_HOMOLOGACAO not in resposta.text and CSC_PRODUCAO not in resposta.text
    csc = {c["ambiente"]: c for c in resposta.json()["csc"]}
    assert (csc["homologacao"]["id"], csc["homologacao"]["salvo"]) == ("000001", True)
    assert csc["homologacao"]["final"] == CSC_HOMOLOGACAO[-4:]
    assert (csc["producao"]["id"], csc["producao"]["final"]) == ("2", CSC_PRODUCAO[-4:])
    situacoes = _situacoes(resposta.json())
    assert (situacoes["csc_homologacao"], situacoes["csc_producao"]) == ("ok", "ok")
    assert CSC_HOMOLOGACAO not in cliente.get("/api/fiscal").text
    with db.nova_sessao() as sessao:
        valores = " ".join(c.valor or "" for c in sessao.query(Configuracao).all())
    assert CSC_HOMOLOGACAO not in valores and CSC_PRODUCAO not in valores
    assert (tmp_path / "segredos" / "csc-homologacao").is_file()
    assert CSC_HOMOLOGACAO not in caplog.text and CSC_PRODUCAO not in caplog.text

    # Código vazio mantém o guardado; trocar só o ID não apaga o código.
    resposta = cliente.put(
        "/api/fiscal/csc",
        json={**corpo, "codigo_homologacao": "", "id_producao": "3", "codigo_producao": ""},
    )
    csc = {c["ambiente"]: c for c in resposta.json()["csc"]}
    assert (csc["homologacao"]["salvo"], csc["producao"]["id"], csc["producao"]["salvo"]) == (
        True,
        "3",
        True,
    )
    # Apagar o de produção.
    resposta = cliente.put(
        "/api/fiscal/csc",
        json={"id_homologacao": "000001", "id_producao": "3", "apagar_producao": True},
    )
    csc = {c["ambiente"]: c for c in resposta.json()["csc"]}
    assert (csc["homologacao"]["salvo"], csc["producao"]["salvo"]) == (True, False)
    assert not (tmp_path / "segredos" / "csc-producao").exists()


@pytest.mark.parametrize(
    ("corpo", "trecho"),
    [
        ({"id_homologacao": "ABC"}, "ID do CSC de homologação: só números"),
        ({"id_homologacao": "1234567"}, "até 6"),
        ({"codigo_homologacao": CSC_HOMOLOGACAO}, "Digite também o ID"),
        ({"id_homologacao": "1", "codigo_homologacao": "CSC COM ESPACO"}, "sem espaços"),
        ({"id_homologacao": "1", "codigo_homologacao": "CSC#FICTICIO"}, "só letras e números"),
        ({"id_homologacao": "1", "codigo_homologacao": "A" * 37}, "até 36"),
        ({"id_homologacao": "1", "codigo_homologacao": 12345678}, "formato inválido"),
        # O de produção errado impede gravar também o de homologação, que estava certo.
        (
            {"id_homologacao": "1", "codigo_homologacao": CSC_HOMOLOGACAO, "id_producao": "X"},
            "de produção",
        ),
    ],
)
def test_csc_errado_e_recusado_sem_repetir_o_codigo(cliente, corpo, trecho):
    resposta = cliente.put("/api/fiscal/csc", json=corpo)
    assert resposta.status_code == 422
    assert trecho in resposta.json()["detail"]
    codigo = str(corpo.get("codigo_homologacao", "")) or "nada"
    assert codigo not in resposta.text
    fiscal = cliente.get("/api/fiscal").json()
    assert [c["salvo"] for c in fiscal["csc"]] == [False, False]


def test_numeracao_e_conferida(cliente, padroes):
    fiscal = cliente.get("/api/fiscal").json()
    caixa = fiscal["numeracao"][0]["caixa_id"]
    for corpo, status, trecho in [
        ({"caixa_id": caixa, "serie": 1000, "proximo_numero": 1}, 422, "Série"),
        ({"caixa_id": caixa, "serie": 1, "proximo_numero": 0}, 422, "Próximo número"),
        ({"caixa_id": caixa, "serie": 1, "proximo_numero": 1_000_000_000}, 422, "Próximo número"),
        ({"caixa_id": 999, "serie": 1, "proximo_numero": 1}, 404, "Caixa"),
    ]:
        resposta = cliente.put("/api/fiscal/numeracao", json=corpo)
        assert resposta.status_code == status, corpo
        assert trecho in resposta.json()["detail"]
    resposta = cliente.put(
        "/api/fiscal/numeracao", json={"caixa_id": caixa, "serie": 2, "proximo_numero": 4522}
    )
    assert resposta.status_code == 200, resposta.text
    fiscal = resposta.json()
    assert (fiscal["numeracao"][0]["serie"], fiscal["numeracao"][0]["proximo_numero"]) == (2, 4522)
    assert fiscal["numeracao_conferida"] is True
    assert _situacoes(fiscal)["numeracao"] == "ok"
    assert "série 2, próxima nota nº 4522" in _detalhe(fiscal, "numeracao")


def test_numero_ja_registrado_nao_pode_voltar(cliente, loja, vender):
    # Um documento fiscal de mentira, gravado direto no banco: o sistema ainda não emite.
    venda = vender([(loja["picole"], "1")])
    fiscal = cliente.get("/api/fiscal").json()
    caixa = fiscal["numeracao"][0]["caixa_id"]
    with db.nova_sessao() as sessao:
        sessao.add(DocumentoFiscal(venda_id=venda["id"], serie=1, numero=150))
        sessao.commit()
    resposta = cliente.put(
        "/api/fiscal/numeracao", json={"caixa_id": caixa, "serie": 1, "proximo_numero": 120}
    )
    assert resposta.status_code == 422
    assert "nº 150 da série 1 já foi registrada" in resposta.json()["detail"]
    resposta = cliente.put(
        "/api/fiscal/numeracao", json={"caixa_id": caixa, "serie": 1, "proximo_numero": 151}
    )
    assert resposta.status_code == 200
    assert resposta.json()["numeracao"][0]["ultima_registrada"] == 150


def test_contador_e_conferido(cliente):
    for mudanca, trecho in [
        ({"email": "sem-arroba"}, "E-mail"),
        ({"documento": "111.111.111-11"}, "CPF ou CNPJ"),
        ({"observacoes": "x" * 601}, "600"),
    ]:
        resposta = cliente.put(
            "/api/fiscal/contador", json={"nome": "Contador Fictício", **mudanca}
        )
        assert resposta.status_code == 422
        assert trecho in resposta.json()["detail"]
    resposta = cliente.put(
        "/api/fiscal/contador",
        json={
            "nome": "  Contador   Fictício ",
            "crc": "sp-123456/o-1",
            "telefone": "(11) 5555-0199",
            "email": "Contador@Ficticio.com.br",
            "documento": "111.444.777-35",
            "observacoes": "  Picolé: CSOSN 500.  \n\n Água: CFOP 5405 ",
        },
    )
    assert resposta.status_code == 200, resposta.text
    contador = resposta.json()["contador"]
    assert contador == {
        "nome": "Contador Fictício",
        "crc": "SP-123456/O-1",
        "telefone": "(11) 5555-0199",
        "email": "contador@ficticio.com.br",
        "documento": "11144477735",
        "observacoes": "Picolé: CSOSN 500.\n\nÁgua: CFOP 5405",
    }
    assert _situacoes(resposta.json())["contador"] == "ok"


def test_certificado_instalado_conferido_e_removido(cliente, tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    _gravar_loja(cliente)
    conteudo = gerar()
    resposta = _instalar(cliente, conteudo)
    assert resposta.status_code == 201, resposta.text
    assert SENHA not in resposta.text
    fiscal = resposta.json()
    cert = fiscal["certificado"]
    assert (cert["titular"], cert["cnpj"], cert["emissor"]) == (
        TITULAR,
        CNPJ,
        "AC FICTICIA DE TESTE",
    )
    assert cert["arquivo"] == "empresa.pfx"  # só o nome, sem a pasta do computador
    assert (cert["tem_arquivo"], cert["tem_senha"], cert["cnpj_confere"]) == (True, True, True)
    assert cert["vencido"] is False and cert["dias_restantes"] in (364, 365)
    assert cert["fim"].endswith("-03:00")  # horário da loja
    assert _situacoes(fiscal)["certificado"] == "ok"
    copia = tmp_path / "certificado" / "certificado-a1.pfx"
    assert copia.read_bytes() == conteudo
    assert (tmp_path / "segredos" / "certificado-senha").is_file()
    with db.nova_sessao() as sessao:
        valores = " ".join(c.valor or "" for c in sessao.query(Configuracao).all())
    assert SENHA not in valores

    status = cliente.get("/api/status").json()["certificado"]
    assert (status["ok"], status["texto"]) == (True, "A1")
    assert TITULAR in status["motivo"]

    conferido = cliente.post("/api/fiscal/certificado/conferir")
    assert conferido.status_code == 200, conferido.text
    assert conferido.json()["cnpj"] == CNPJ
    assert "abriu com a senha guardada" in conferido.json()["mensagem"]

    # Instalar de novo troca o anterior.
    resposta = _instalar(cliente, gerar(dias_de_validade=700), nome="renovado.p12")
    assert resposta.status_code == 201
    assert resposta.json()["certificado"]["arquivo"] == "renovado.p12"
    assert resposta.json()["certificado"]["dias_restantes"] in (699, 700)

    recusado = cliente.post("/api/fiscal/certificado/remover", json={})
    assert recusado.status_code == 422
    assert copia.exists()
    removido = cliente.post("/api/fiscal/certificado/remover", json={"confirmo": True})
    assert removido.status_code == 200
    assert removido.json()["certificado"] is None
    assert not copia.exists() and not (tmp_path / "segredos" / "certificado-senha").exists()
    assert cliente.get("/api/status").json()["certificado"]["ok"] is False
    assert cliente.post("/api/fiscal/certificado/conferir").status_code == 409
    assert "certificado A1 removido por gerente" in caplog.text
    assert SENHA not in caplog.text


@pytest.mark.parametrize(
    ("conteudo", "senha", "trecho"),
    [
        (None, "senha-errada-ficticia", "com esta senha"),
        (gerar(dias_de_validade=-3), SENHA, "venceu em"),
        (gerar(comeca_em_dias=5, dias_de_validade=400), SENHA, "só passa a valer"),
        (gerar(titular="PESSOA FICTICIA", cnpj="", pessoa_fisica=True), SENHA, "pessoa física"),
        (gerar(titular="SEM CNPJ", cnpj=""), SENHA, "Não encontrei o CNPJ"),
        (gerar(cnpj="11444777000161"), SENHA, "mas o CNPJ da loja"),
        (gerar(com_chave=False), SENHA, "chave privada"),
    ],
    ids=[
        "senha-errada",
        "vencido",
        "ainda-nao-vale",
        "e-cpf",
        "sem-cnpj",
        "outra-empresa",
        "sem-chave",
    ],
)
def test_certificado_que_nao_serve_e_recusado(cliente, tmp_path, conteudo, senha, trecho):
    _gravar_loja(cliente)
    resposta = _instalar(cliente, conteudo, senha)
    assert resposta.status_code == 422
    assert trecho in resposta.json()["detail"], resposta.json()["detail"]
    assert senha not in resposta.text
    assert cliente.get("/api/fiscal").json()["certificado"] is None
    assert not (tmp_path / "certificado" / "certificado-a1.pfx").exists()
    assert not (tmp_path / "segredos" / "certificado-senha").exists()


def test_certificado_da_filial_vale_para_a_matriz(cliente):
    _gravar_loja(cliente)
    resposta = _instalar(cliente, gerar(cnpj="11222333000262"))
    assert resposta.status_code == 201, resposta.text
    assert resposta.json()["certificado"]["cnpj_confere"] is True


def test_certificado_sem_cnpj_na_loja_e_aceito_e_a_loja_fica_pendente(cliente):
    resposta = _instalar(cliente)
    assert resposta.status_code == 201, resposta.text
    fiscal = resposta.json()
    assert fiscal["certificado"]["cnpj_confere"] is None
    assert _situacoes(fiscal)["certificado"] == "ok"
    assert _situacoes(fiscal)["loja"] == "falta"
    # Depois, a loja com outro CNPJ: o certificado volta para a lista do que falta.
    _gravar_loja(cliente, cnpj="11444777000161")
    fiscal = cliente.get("/api/fiscal").json()
    assert fiscal["certificado"]["cnpj_confere"] is False
    assert _situacoes(fiscal)["certificado"] == "falta"


def test_certificado_perto_de_vencer_pede_atencao(cliente):
    _gravar_loja(cliente)
    fiscal = _instalar(cliente, gerar(dias_de_validade=10)).json()
    assert _situacoes(fiscal)["certificado"] == "atencao"
    assert "Vence em 10 dias" in _detalhe(fiscal, "certificado")
    assert cliente.get("/api/status").json()["certificado"]["texto"] == "A1 · vence em 10 dias"


@pytest.mark.parametrize(
    ("corpo", "trecho"),
    [
        ({"conteudo_base64": "não é base64!", "senha": SENHA}, "não chegou inteiro"),
        ({"conteudo_base64": "A" * 300_000, "senha": SENHA}, "grande demais"),
        ({"conteudo_base64": "", "senha": SENHA}, "Escolha o arquivo"),
        ({"conteudo_base64": base64.b64encode(gerar()).decode(), "senha": 1234}, "formato"),
    ],
    ids=["nao-e-base64", "grande-demais", "vazio", "senha-que-nao-e-texto"],
)
def test_envio_do_certificado_estragado(cliente, corpo, trecho):
    resposta = cliente.post("/api/fiscal/certificado", json={"nome_arquivo": "x.pfx", **corpo})
    assert resposta.status_code == 422
    assert trecho in resposta.json()["detail"]
    assert "1234" not in resposta.text


def test_a_copia_de_seguranca_nao_leva_os_segredos(cliente, tmp_path):
    _gravar_loja(cliente)
    assert _instalar(cliente).status_code == 201
    cliente.put(
        "/api/fiscal/csc", json={"id_homologacao": "1", "codigo_homologacao": CSC_HOMOLOGACAO}
    )
    feito = cliente.post("/api/backup")
    assert feito.status_code == 201, feito.text
    copia = (tmp_path / "backups" / feito.json()["copia"]["arquivo"]).read_bytes()
    assert copia.startswith(b"SQLite format 3")
    assert SENHA.encode() not in copia and CSC_HOMOLOGACAO.encode() not in copia
    assert b"fiscal.certificado_cnpj" in copia  # o que não é segredo vai junto


def _produto(cliente, varejo, descricao, categoria=None, **fiscais):
    corpo = {
        "descricao": descricao,
        "categoria": categoria,
        "precos": [{"tabela_id": varejo, "qtd_min": "1", "preco_centavos": 500}],
        **fiscais,
    }
    resposta = cliente.post("/api/produtos", json=corpo)
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def _varejo(cliente):
    return next(t["id"] for t in cliente.get("/api/tabelas-preco").json() if t["padrao"])


def test_produto_guarda_cfop_e_confere_a_origem(cliente, padroes):
    varejo = _varejo(cliente)
    produto = _produto(cliente, varejo, "Água fictícia", cfop="5405", cst_csosn="500", origem="0")
    assert (produto["cfop"], produto["origem"]) == ("5405", "0")
    for campos, trecho in [
        ({"cfop": "6102"}, "começa com 5"),
        ({"cfop": "51"}, "CFOP"),
        ({"origem": "9"}, "Origem"),
        ({"ncm": "2105"}, "NCM"),
    ]:
        resposta = cliente.post("/api/produtos", json={"descricao": "Produto fictício", **campos})
        assert resposta.status_code == 422
        assert trecho in resposta.json()["detail"]
    assert cliente.get(f"/api/produtos/{produto['id']}").json()["cfop"] == "5405"


def test_resumo_e_preenchimento_por_categoria(cliente, padroes, caplog):
    caplog.set_level(logging.INFO)
    varejo = _varejo(cliente)
    morango = _produto(cliente, varejo, "Picolé fictício de morango", "Picolés", ncm="21050010")
    limao = _produto(cliente, varejo, "Picolé fictício de limão", "Picolés")
    pote = _produto(cliente, varejo, "Pote fictício", "Sorvetes")
    avulso = _produto(cliente, varejo, "Produto fictício sem categoria")
    fiscal = cliente.get("/api/fiscal").json()
    resumo = {c["nome"]: c for c in fiscal["categorias"]}
    assert [c["nome"] for c in fiscal["categorias"]] == ["Picolés", "Sorvetes", None]
    assert (resumo["Picolés"]["produtos"], resumo["Picolés"]["sem_ncm"]) == (2, 1)
    assert (resumo["Picolés"]["sem_cfop"], resumo["Picolés"]["completa"]) == (2, False)
    assert _situacoes(fiscal)["produtos"] == "falta"
    assert (
        _detalhe(fiscal, "produtos")
        == "Dos 4 produtos ativos: 3 sem NCM, 4 sem CFOP e 4 sem CST/CSOSN."
    )

    for corpo, status, trecho in [
        ({"categoria": "Picolés"}, 422, "pelo menos um"),
        ({"categoria": "Picolés", "cfop": "6102"}, 422, "começa com 5"),
        ({"categoria": "Não existe", "ncm": "21050010"}, 404, "Nenhum produto"),
    ]:
        resposta = cliente.post("/api/fiscal/produtos/categoria", json=corpo)
        assert resposta.status_code == status
        assert trecho in resposta.json()["detail"]

    # Sem trocar: só os campos vazios (o NCM do picolé de morango fica como estava).
    resposta = cliente.post(
        "/api/fiscal/produtos/categoria",
        json={
            "categoria": "Picolés",
            "ncm": "2105.00.90",
            "cfop": "5405",
            "cst_csosn": "500",
            "origem": "2",
        },
    )
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["alterados"] == 2
    lido = {p: cliente.get(f"/api/produtos/{p}").json() for p in (morango["id"], limao["id"])}
    assert (lido[morango["id"]]["ncm"], lido[limao["id"]]["ncm"]) == ("21050010", "21050090")
    assert {p["cfop"] for p in lido.values()} == {"5405"}
    assert {p["origem"] for p in lido.values()} == {"0"}  # a origem só muda trocando
    assert "categoria Picolés por gerente: 2 de 2 produtos" in caplog.text

    # Trocando: todos ficam com os valores dados, e repetir não muda mais nada.
    corpo = {"categoria": "Picolés", "ncm": "21050090", "origem": "2", "sobrescrever": True}
    assert cliente.post("/api/fiscal/produtos/categoria", json=corpo).json()["alterados"] == 2
    assert cliente.get(f"/api/produtos/{morango['id']}").json()["ncm"] == "21050090"
    assert cliente.get(f"/api/produtos/{morango['id']}").json()["origem"] == "2"
    assert cliente.post("/api/fiscal/produtos/categoria", json=corpo).json()["alterados"] == 0

    # Os sem categoria e os outros.
    sem = {"categoria": "", "ncm": "22011000", "cfop": "5405", "cst_csosn": "500"}
    assert cliente.post("/api/fiscal/produtos/categoria", json=sem).json()["alterados"] == 1
    assert cliente.get(f"/api/produtos/{avulso['id']}").json()["cfop"] == "5405"
    resposta = cliente.post(
        "/api/fiscal/produtos/categoria",
        json={"categoria": "Sorvetes", "ncm": "21050010", "cfop": "5405", "cst_csosn": "500"},
    )
    fiscal = resposta.json()["fiscal"]
    assert all(c["completa"] for c in fiscal["categorias"])
    assert _situacoes(fiscal)["produtos"] == "ok"
    assert _detalhe(fiscal, "produtos") == "Os 4 produtos ativos têm NCM, CFOP e CST/CSOSN."
    assert cliente.get(f"/api/produtos/{pote['id']}").json()["cst_csosn"] == "500"


def test_cst_csosn_e_cfop_que_nao_combinam_pedem_atencao(cliente, padroes):
    varejo = _varejo(cliente)
    _produto(
        cliente, varejo, "Picolé fictício", "Picolés", ncm="21050010", cfop="5405", cst_csosn="60"
    )
    cliente.put("/api/fiscal/empresa", json={**EMPRESA, "crt": "1"})
    fiscal = cliente.get("/api/fiscal").json()
    assert _situacoes(fiscal)["produtos"] == "atencao"
    assert "o Simples usa CSOSN" in _detalhe(fiscal, "produtos")
    assert fiscal["categorias"][0]["fora_do_regime"] == 1
    # No regime normal, CST 60 combina.
    cliente.put("/api/fiscal/empresa", json={**EMPRESA, "crt": "3"})
    assert _situacoes(cliente.get("/api/fiscal").json())["produtos"] == "ok"
    # O MEI só usa CSOSN 102 ou 300 na NFC-e.
    cliente.post(
        "/api/fiscal/produtos/categoria",
        json={"categoria": "Picolés", "cst_csosn": "500", "sobrescrever": True},
    )
    cliente.put("/api/fiscal/empresa", json={**EMPRESA, "crt": "4"})
    fiscal = cliente.get("/api/fiscal").json()
    assert "o MEI usa CSOSN 102 ou 300" in _detalhe(fiscal, "produtos")
    # CFOP que começa com 5 mas não está na lista da NFC-e: atenção, sem recusar.
    cliente.put("/api/fiscal/empresa", json={**EMPRESA, "crt": "1"})
    cliente.post(
        "/api/fiscal/produtos/categoria",
        json={"categoria": "Picolés", "cfop": "5949", "sobrescrever": True},
    )
    fiscal = cliente.get("/api/fiscal").json()
    assert _situacoes(fiscal)["produtos"] == "atencao"
    assert "CFOP fora da lista" in _detalhe(fiscal, "produtos")


def test_com_tudo_preenchido_nada_falta(cliente, padroes):
    _gravar_loja(cliente)
    cliente.put("/api/fiscal/empresa", json=EMPRESA)
    assert _instalar(cliente).status_code == 201
    cliente.put(
        "/api/fiscal/csc",
        json={
            "id_homologacao": "1",
            "codigo_homologacao": CSC_HOMOLOGACAO,
            "id_producao": "2",
            "codigo_producao": CSC_PRODUCAO,
        },
    )
    caixa = cliente.get("/api/fiscal").json()["numeracao"][0]["caixa_id"]
    cliente.put("/api/fiscal/numeracao", json={"caixa_id": caixa, "serie": 1, "proximo_numero": 1})
    cliente.put(
        "/api/fiscal/contador", json={"nome": "Contador Fictício", "email": "c@ficticio.com.br"}
    )
    _produto(
        cliente,
        _varejo(cliente),
        "Picolé fictício",
        "Picolés",
        ncm="21050010",
        cfop="5405",
        cst_csosn="500",
    )
    fiscal = cliente.get("/api/fiscal").json()
    assert set(_situacoes(fiscal).values()) == {"ok"}
    assert fiscal["faltam"] == 0
    assert "ainda não emite NFC-e" in fiscal["aviso"]  # mesmo pronto, a emissão não existe


@pytest.mark.parametrize(
    ("metodo", "caminho", "corpo"),
    [
        ("get", "/api/fiscal", None),
        ("put", "/api/fiscal/empresa", EMPRESA),
        ("put", "/api/fiscal/csc", {"id_homologacao": "1"}),
        ("put", "/api/fiscal/numeracao", {"caixa_id": 1, "serie": 1, "proximo_numero": 1}),
        ("put", "/api/fiscal/contador", {"nome": "x"}),
        ("post", "/api/fiscal/certificado", {"conteudo_base64": "", "senha": ""}),
        ("post", "/api/fiscal/certificado/conferir", None),
        ("post", "/api/fiscal/certificado/remover", {"confirmo": True}),
        ("post", "/api/fiscal/produtos/categoria", {"categoria": "", "ncm": "21050010"}),
    ],
)
def test_so_o_gerente_mexe_nos_dados_fiscais(anonimo, caixa, metodo, caminho, corpo):
    argumentos = {} if corpo is None else {"json": corpo}
    assert getattr(anonimo, metodo)(caminho, **argumentos).status_code == 401
    assert getattr(caixa, metodo)(caminho, **argumentos).status_code == 403

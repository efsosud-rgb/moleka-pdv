"""Entrada no sistema: primeiro acesso, login, perfis e cadastro de operadores."""

import pytest
from conftest import ENDERECO, GERENTE, OPERADOR
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import acesso, db, operadores
from app.models import Operador, Perfil

TELAS_INTERNAS = ["/inicio", "/caixa", "/produtos", "/financeiro", "/operadores"]


def _operador_no_banco(login):
    with db.nova_sessao() as sessao:
        return sessao.scalar(select(Operador).where(Operador.login == login))


def _outra_janela(app):
    return TestClient(app, base_url=ENDERECO)


# ---------------------------------------------------------------- primeiro acesso


def test_sem_operador_o_sistema_pede_a_configuracao_inicial(anonimo):
    assert anonimo.get("/api/sessao").json() == {"configurado": False, "operador": None}
    capa = anonimo.get("/")
    assert capa.status_code == 200
    assert "Primeiro acesso" in capa.text and 'id="form-inicial"' in capa.text
    assert 'id="form-login"' not in capa.text


@pytest.mark.parametrize("caminho", TELAS_INTERNAS)
def test_tela_interna_sem_login_volta_para_a_capa(anonimo, caminho):
    resposta = anonimo.get(caminho, follow_redirects=False)
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/"


def test_api_de_cadastros_exige_login(anonimo):
    for caminho in ("/api/produtos", "/api/clientes", "/api/tabelas-preco", "/api/operadores"):
        resposta = anonimo.get(caminho)
        assert resposta.status_code == 401, caminho
        assert "usuário e senha" in resposta.json()["detail"]
    assert anonimo.post("/api/clientes", json={"nome": "Maria"}).status_code == 401
    # O que a capa precisa antes do login continua aberto.
    assert anonimo.get("/api/status").status_code == 200


def test_configuracao_inicial_cria_o_gerente_e_ja_entra(anonimo):
    resposta = anonimo.post(
        "/api/configuracao-inicial",
        json={"nome": "  Eric   Souza ", "login": " Eric ", "senha": "segredo1"},
    )
    assert resposta.status_code == 201, resposta.text
    assert resposta.json() == {
        "id": 1,
        "nome": "Eric Souza",
        "login": "eric",
        "perfil": "gerente",
        "ativo": True,
    }
    cookie = resposta.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "path=/" in cookie
    assert "max-age" not in cookie and "expires" not in cookie  # some ao fechar a janela

    sessao = anonimo.get("/api/sessao").json()
    assert sessao["configurado"] is True and sessao["operador"]["login"] == "eric"
    assert anonimo.get("/inicio", follow_redirects=False).status_code == 200

    # Só vale uma vez: com operador cadastrado, ninguém cria outro gerente por aqui.
    de_novo = anonimo.post(
        "/api/configuracao-inicial", json={"nome": "Outro", "login": "outro", "senha": "segredo2"}
    )
    assert de_novo.status_code == 409
    assert "já foi feita" in de_novo.json()["detail"]


@pytest.mark.parametrize(
    ("dados", "trecho"),
    [
        ({"nome": " ", "login": "eric", "senha": "1234"}, "nome"),
        ({"nome": "Eric", "login": "e", "senha": "1234"}, "usuário"),
        ({"nome": "Eric", "login": "eric souza", "senha": "1234"}, "usuário"),
        ({"nome": "Eric", "login": "érico", "senha": "1234"}, "usuário"),
        ({"nome": "Eric", "login": "eric", "senha": "123"}, "pelo menos 4"),
        ({"nome": "Eric", "login": "eric", "senha": "x" * 129}, "no máximo 128"),
    ],
)
def test_configuracao_inicial_recusa_dados_invalidos_com_mensagem_clara(anonimo, dados, trecho):
    resposta = anonimo.post("/api/configuracao-inicial", json=dados)
    assert resposta.status_code == 422
    assert trecho in resposta.json()["detail"]
    assert anonimo.get("/api/sessao").json()["configurado"] is False


def test_senha_fica_no_banco_so_como_hash_e_nunca_volta_na_api(cliente):
    gravado = _operador_no_banco(GERENTE["login"]).senha_hash
    assert gravado.startswith("scrypt$") and GERENTE["senha"] not in gravado
    for caminho in ("/api/sessao", "/api/operadores"):
        texto = cliente.get(caminho).text
        assert "senha" not in texto and "scrypt" not in texto, caminho


# ---------------------------------------------------------------- login e saída


def test_login_certo_errado_e_saida(app_teste, cliente, anonimo):
    capa = anonimo.get("/")
    assert 'id="form-login"' in capa.text and "Primeiro acesso" not in capa.text
    assert f'<option value="{GERENTE["login"]}">{GERENTE["nome"]}</option>' in capa.text

    errada = anonimo.post("/api/login", json={"login": "gerente", "senha": "errada"})
    assert errada.status_code == 401
    assert errada.json()["detail"] == "Usuário ou senha incorretos."
    assert "set-cookie" not in errada.headers
    # Usuário que não existe recebe a mesma resposta (não revela quem está cadastrado).
    inexistente = anonimo.post("/api/login", json={"login": "ninguem", "senha": "errada"})
    assert (inexistente.status_code, inexistente.json()) == (errada.status_code, errada.json())
    assert anonimo.get("/inicio", follow_redirects=False).status_code == 303

    certa = anonimo.post("/api/login", json={"login": " GERENTE ", "senha": GERENTE["senha"]})
    assert certa.status_code == 200 and certa.json()["perfil"] == "gerente"
    assert anonimo.get("/inicio", follow_redirects=False).status_code == 200
    assert "Operador: Gerente de Teste (gerente)" in anonimo.get("/inicio").text

    assert anonimo.post("/api/sair").status_code == 204
    assert anonimo.get("/api/sessao").json()["operador"] is None
    assert anonimo.get("/inicio", follow_redirects=False).status_code == 303
    # A outra janela (fixture `cliente`) continua logada: cada janela tem a sua sessão.
    assert cliente.get("/api/sessao").json()["operador"]["login"] == "gerente"


def test_capa_de_quem_ja_entrou_oferece_continuar_ou_trocar(cliente):
    capa = cliente.get("/").text
    assert "Continuar (Enter)" in capa and "Trocar de operador" in capa
    assert 'id="form-login"' not in capa and 'id="form-inicial"' not in capa


def test_codigo_de_sessao_inventado_nao_entra(anonimo, cliente):
    anonimo.cookies.set(acesso.COOKIE, "codigo-inventado")
    assert anonimo.get("/api/sessao").json()["operador"] is None
    assert anonimo.get("/api/operadores").status_code == 401


def test_muitas_senhas_erradas_bloqueiam_por_um_tempo(app_teste, cliente, anonimo):
    agora = [1000.0]
    app_teste.state.tentativas = acesso.Tentativas(relogio=lambda: agora[0])
    for _ in range(acesso.Tentativas.LIMITE):
        r = anonimo.post("/api/login", json={"login": "gerente", "senha": "errada"})
        assert r.status_code == 401
    bloqueado = anonimo.post("/api/login", json={"login": "gerente", "senha": GERENTE["senha"]})
    assert bloqueado.status_code == 429
    assert "Aguarde 30 segundos" in bloqueado.json()["detail"]
    assert bloqueado.headers["retry-after"] == "30"
    # O bloqueio é por usuário: outro operador não fica preso por causa deste.
    outro = anonimo.post("/api/login", json={"login": "caixa", "senha": "x"})
    assert outro.status_code == 401

    agora[0] += acesso.Tentativas.ESPERA + 1
    liberado = anonimo.post("/api/login", json={"login": "gerente", "senha": GERENTE["senha"]})
    assert liberado.status_code == 200


def test_acertar_a_senha_zera_a_contagem_de_erros(app_teste, cliente, anonimo):
    for _ in range(acesso.Tentativas.LIMITE - 1):
        anonimo.post("/api/login", json={"login": "gerente", "senha": "errada"})
    assert (
        anonimo.post("/api/login", json={"login": "gerente", "senha": GERENTE["senha"]}).status_code
        == 200
    )
    for _ in range(acesso.Tentativas.LIMITE - 1):
        r = anonimo.post("/api/login", json={"login": "gerente", "senha": "errada"})
        assert r.status_code == 401  # ainda não bloqueou: a contagem recomeçou


# ---------------------------------------------------------------- perfis


def test_operador_comum_nao_faz_o_que_e_do_gerente(caixa):
    assert caixa.get("/api/sessao").json()["operador"]["perfil"] == "operador"
    # Não mexe em operadores, produtos nem tabelas de preço.
    assert caixa.get("/api/operadores").status_code == 403
    assert caixa.post("/api/operadores", json=dict(OPERADOR, login="x2")).status_code == 403
    assert caixa.put("/api/operadores/1", json={}).status_code == 403
    assert caixa.post("/api/produtos", json={"codigo": "X", "descricao": "x"}).status_code == 403
    assert caixa.post("/api/tabelas-preco", json={"nome": "VAREJO"}).status_code == 403
    assert "Só o gerente" in caixa.get("/api/operadores").json()["detail"]
    # Mas consulta produtos e cadastra cliente (é o que o caixa precisa na venda).
    assert caixa.get("/api/produtos").status_code == 200
    assert caixa.post("/api/clientes", json={"nome": "Maria"}).status_code == 201


@pytest.mark.parametrize("caminho", ["/produtos", "/financeiro", "/operadores"])
def test_tela_do_gerente_manda_o_operador_comum_para_o_inicio(caixa, caminho):
    resposta = caixa.get(caminho, follow_redirects=False)
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/inicio?aviso=gerente"


def test_inicio_do_operador_comum_mostra_o_que_esta_trancado(caixa, cliente):
    do_caixa = caixa.get("/inicio").text
    assert "Operador: Caixa de Teste" in do_caixa and "(gerente)" not in do_caixa
    assert "só gerente" in do_caixa and "só o gerente abre" in do_caixa
    assert 'href="/produtos"' not in do_caixa and 'href="/operadores"' not in do_caixa
    assert 'href="/caixa"' in do_caixa
    do_gerente = cliente.get("/inicio").text
    assert 'href="/produtos"' in do_gerente and 'href="/operadores"' in do_gerente
    assert "só gerente" not in do_gerente


# ---------------------------------------------------------------- cadastro de operadores


def test_gerente_cadastra_altera_e_inativa_operador(app_teste, cliente):
    novo = cliente.post(
        "/api/operadores",
        json={"nome": "Ana  Lima", "login": "Ana.Lima", "senha": "4321", "perfil": "operador"},
    )
    assert novo.status_code == 201, novo.text
    ana = novo.json()
    assert (ana["nome"], ana["login"], ana["perfil"], ana["ativo"]) == (
        "Ana Lima",
        "ana.lima",
        "operador",
        True,
    )
    repetido = cliente.post(
        "/api/operadores", json={"nome": "Outra Ana", "login": "ana.lima", "senha": "9999"}
    )
    assert repetido.status_code == 409 and "Já existe" in repetido.json()["detail"]
    assert (
        cliente.post(
            "/api/operadores", json={"nome": "Sem Senha", "login": "sem", "senha": "12"}
        ).status_code
        == 422
    )
    nomes = [o["nome"] for o in cliente.get("/api/operadores").json()]
    assert nomes == ["Ana Lima", "Gerente de Teste"]  # em ordem alfabética

    # A Ana entra em outra janela.
    janela_da_ana = _outra_janela(app_teste)
    assert (
        janela_da_ana.post("/api/login", json={"login": "ana.lima", "senha": "4321"}).status_code
        == 200
    )

    # O gerente troca a senha dela: a sessão aberta cai e a senha antiga para de valer.
    alterado = cliente.put(
        f"/api/operadores/{ana['id']}",
        json={
            "nome": "Ana Lima",
            "login": "ana",
            "perfil": "operador",
            "ativo": True,
            "senha": "nova-senha",
        },
    )
    assert alterado.status_code == 200 and alterado.json()["login"] == "ana"
    assert janela_da_ana.get("/api/sessao").json()["operador"] is None
    assert (
        janela_da_ana.post("/api/login", json={"login": "ana", "senha": "4321"}).status_code == 401
    )
    assert (
        janela_da_ana.post("/api/login", json={"login": "ana", "senha": "nova-senha"}).status_code
        == 200
    )

    # Inativar derruba a sessão e impede novos logins; o cadastro continua lá.
    inativo = cliente.put(
        f"/api/operadores/{ana['id']}",
        json={"nome": "Ana Lima", "login": "ana", "perfil": "operador", "ativo": False},
    )
    assert inativo.status_code == 200 and inativo.json()["ativo"] is False
    assert janela_da_ana.get("/inicio", follow_redirects=False).status_code == 303
    recusado = janela_da_ana.post("/api/login", json={"login": "ana", "senha": "nova-senha"})
    assert recusado.status_code == 403 and "inativo" in recusado.json()["detail"]
    assert [o["login"] for o in cliente.get("/api/operadores").json()] == ["ana", "gerente"]
    # Inativo não aparece na lista da tela de login.
    capa = janela_da_ana.get("/").text
    assert 'value="gerente"' in capa and 'value="ana"' not in capa

    assert cliente.put("/api/operadores/999", json=inativo.json()).status_code == 404


def test_gerente_nao_inativa_nem_rebaixa_a_si_mesmo(cliente):
    eu = cliente.get("/api/sessao").json()["operador"]
    base = {"nome": eu["nome"], "login": eu["login"], "perfil": "gerente", "ativo": True}
    for mudanca in ({"ativo": False}, {"perfil": "operador"}):
        resposta = cliente.put(f"/api/operadores/{eu['id']}", json={**base, **mudanca})
        assert resposta.status_code == 409, mudanca
        assert "próprio usuário" in resposta.json()["detail"]
    # Mas muda o próprio nome e a própria senha, e continua logado.
    resposta = cliente.put(
        f"/api/operadores/{eu['id']}", json={**base, "nome": "Novo Nome", "senha": "outra-senha"}
    )
    assert resposta.status_code == 200 and resposta.json()["nome"] == "Novo Nome"
    assert cliente.get("/api/sessao").json()["operador"]["nome"] == "Novo Nome"
    assert _operador_no_banco("gerente").perfil == Perfil.GERENTE


def test_segundo_gerente_pode_rebaixar_o_primeiro(app_teste, cliente):
    cliente.post(
        "/api/operadores",
        json={"nome": "Sócia", "login": "socia", "senha": "abcd", "perfil": "gerente"},
    )
    socia = _outra_janela(app_teste)
    assert socia.post("/api/login", json={"login": "socia", "senha": "abcd"}).status_code == 200
    rebaixado = socia.put(
        "/api/operadores/1",
        json={"nome": "Gerente de Teste", "login": "gerente", "perfil": "operador", "ativo": True},
    )
    assert rebaixado.status_code == 200 and rebaixado.json()["perfil"] == "operador"
    # O primeiro continua logado, agora sem os poderes de gerente.
    assert cliente.get("/api/operadores").status_code == 403
    assert cliente.get("/api/sessao").json()["operador"]["perfil"] == "operador"


def test_minha_senha(app_teste, caixa, anonimo):
    errada = caixa.post("/api/minha-senha", json={"senha_atual": "0000", "senha_nova": "abcd"})
    assert errada.status_code == 403 and "senha atual" in errada.json()["detail"]
    curta = caixa.post("/api/minha-senha", json={"senha_atual": "1234", "senha_nova": "abc"})
    assert curta.status_code == 422
    igual = caixa.post("/api/minha-senha", json={"senha_atual": "1234", "senha_nova": "1234"})
    assert igual.status_code == 422 and "igual" in igual.json()["detail"]

    assert (
        caixa.post(
            "/api/minha-senha", json={"senha_atual": "1234", "senha_nova": "abcd"}
        ).status_code
        == 204
    )
    assert caixa.get("/api/sessao").json()["operador"]["login"] == "caixa"  # continua logado
    assert anonimo.post("/api/login", json={"login": "caixa", "senha": "1234"}).status_code == 401
    assert anonimo.post("/api/login", json={"login": "caixa", "senha": "abcd"}).status_code == 200
    assert anonimo.post("/api/sair").status_code == 204
    assert anonimo.post("/api/minha-senha", json={}).status_code == 401


# ---------------------------------------------------------------- recuperação de acesso


def test_recuperacao_de_acesso_gera_senha_provisoria_e_reativa(cliente, anonimo):
    with db.nova_sessao() as sessao:
        gerente, provisoria = operadores.redefinir_senha(sessao, None)  # só há um gerente
        assert gerente.login == "gerente" and len(provisoria) == 6 and provisoria.isdigit()
        with pytest.raises(operadores.RegraError, match="Não existe operador"):
            operadores.redefinir_senha(sessao, "fulano")
    assert (
        anonimo.post("/api/login", json={"login": "gerente", "senha": GERENTE["senha"]}).status_code
        == 401
    )
    assert (
        anonimo.post("/api/login", json={"login": "gerente", "senha": provisoria}).status_code
        == 200
    )


def test_recuperacao_com_dois_gerentes_pede_o_usuario(cliente):
    cliente.post(
        "/api/operadores",
        json={"nome": "Sócia", "login": "socia", "senha": "abcd", "perfil": "gerente"},
    )
    with db.nova_sessao() as sessao:
        with pytest.raises(operadores.RegraError, match="mais de um gerente"):
            operadores.redefinir_senha(sessao, None)
        alvo, _ = operadores.redefinir_senha(sessao, " SOCIA ")
        assert alvo.login == "socia"


def test_recuperacao_sem_nenhum_gerente_explica_o_que_fazer(anonimo):
    with db.nova_sessao() as sessao:
        with pytest.raises(operadores.RegraError, match="primeiro gerente"):
            operadores.redefinir_senha(sessao, None)


# ---------------------------------------------------------------- só a janela do programa


def test_pedido_com_endereco_de_fora_e_recusado(anonimo):
    """Um domínio de fora apontado para 127.0.0.1 não conversa com o sistema."""
    resposta = anonimo.get("/api/status", headers={"host": "site-malicioso.example"})
    assert resposta.status_code == 400
    assert anonimo.get("/api/status", headers={"host": "localhost:8765"}).status_code == 200


def test_pedido_que_altera_dados_vindo_de_outro_site_e_recusado(anonimo):
    dados = {"nome": "Invasor", "login": "invasor", "senha": "123456"}
    for origem in ("https://site-malicioso.example", "null"):
        resposta = anonimo.post("/api/configuracao-inicial", json=dados, headers={"origin": origem})
        assert resposta.status_code == 403, origem
    assert anonimo.get("/api/sessao").json()["configurado"] is False
    # Da própria janela (mesma origem) passa.
    resposta = anonimo.post("/api/configuracao-inicial", json=dados, headers={"origin": ENDERECO})
    assert resposta.status_code == 201


def test_telas_nao_ficam_guardadas_na_janela(cliente):
    """Depois de trocar de operador, "voltar" não mostra a tela do operador anterior."""
    for caminho in ("/", "/inicio", "/operadores"):
        assert cliente.get(caminho).headers["cache-control"] == "no-store", caminho

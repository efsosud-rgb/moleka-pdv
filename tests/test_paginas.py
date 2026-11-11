"""As páginas da interface: existem, apontam para lugares que existem e não inventam dados."""

import re

import pytest

PAGINAS = ["/", "/inicio", "/caixa", "/produtos", "/financeiro"]


@pytest.mark.parametrize("caminho", PAGINAS)
def test_pagina_abre(cliente, caminho):
    resposta = cliente.get(caminho)
    assert resposta.status_code == 200
    assert "Moleka" in resposta.text
    assert resposta.headers["content-type"].startswith("text/html")


@pytest.mark.parametrize("caminho", PAGINAS)
def test_links_e_arquivos_da_pagina_existem(cliente, caminho):
    """Todo href/src interno de uma página responde 200 (nada de link quebrado)."""
    html = cliente.get(caminho).text
    alvos = set(re.findall(r'(?:href|src)="(/[^"#]*)"', html))
    assert alvos, "a página deveria apontar para CSS, JS e outras telas"
    for alvo in sorted(alvos):
        assert cliente.get(alvo).status_code == 200, f"{caminho} aponta para {alvo}"


def test_arquivos_da_interface_e_da_marca(cliente):
    css = cliente.get("/static/css/moleka.css")
    assert css.status_code == 200
    # As fontes e a tira da animação citadas no CSS vêm junto com o programa (nada da internet).
    assert "fonts.googleapis.com" not in css.text
    for url in re.findall(r"url\\(([^)]+)\\)", css.text):
        caminho = url.strip("'\"")
        if caminho.startswith("../"):
            caminho = "/static/" + caminho[3:]
        assert cliente.get(caminho).status_code == 200, caminho
    assert cliente.get("/static/js/moleka.js").status_code == 200
    assert cliente.get("/assets/brand/mascote.png").headers["content-type"] == "image/png"


@pytest.mark.parametrize("caminho", PAGINAS)
def test_pagina_nao_traz_numero_inventado(cliente, caminho):
    """Regra do projeto: sem dado real, a tela mostra "—". Nada de valor de exemplo."""
    html = cliente.get(caminho).text
    assert not re.search(r"R\\$\\s*\\d", html), "há um valor em reais escrito direto na página"
    assert "fictíci" not in html and "Exemplo" not in html
    assert "fonts.googleapis.com" not in html


def test_modulos_sem_tela_avisam_que_estao_em_construcao(cliente):
    html = cliente.get("/inicio").text
    assert html.count("em breve") >= 6
    assert "data-em-breve" in html
    for tela in ("/caixa", "/produtos", "/financeiro"):
        assert "Tela em construção" in cliente.get(tela).text, tela

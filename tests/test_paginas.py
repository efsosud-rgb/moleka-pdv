"""As páginas da interface: existem, apontam para lugares que existem e não inventam dados.

A fixture `cliente` é a janela com o gerente logado; o que acontece sem login e com o operador
comum está em test_acesso.py.
"""

import re

import pytest

PAGINAS = [
    "/",
    "/inicio",
    "/caixa",
    "/controle-caixa",
    "/produtos",
    "/clientes",
    "/tabelas-preco",
    "/financeiro",
    "/operadores",
]
SCRIPTS = [
    "moleka.js",
    "entrada.js",
    "operadores.js",
    "produtos.js",
    "clientes.js",
    "tabelas.js",
    "controle_caixa.js",
    "caixa.js",
]


@pytest.mark.parametrize("caminho", PAGINAS)
def test_pagina_abre(cliente, caminho):
    resposta = cliente.get(caminho, follow_redirects=False)
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
    urls = re.findall(r"url\(([^)]+)\)", css.text)
    assert len(urls) >= 8, "o CSS deveria citar as fontes e a tira da animação"
    for url in urls:
        caminho = url.strip("'\"")
        if caminho.startswith("../"):
            caminho = "/static/" + caminho[3:]
        assert cliente.get(caminho).status_code == 200, caminho
    for script in SCRIPTS:
        assert cliente.get(f"/static/js/{script}").status_code == 200, script
    assert cliente.get("/assets/brand/mascote.png").headers["content-type"] == "image/png"


@pytest.mark.parametrize("caminho", PAGINAS)
def test_pagina_nao_traz_numero_inventado(cliente, caminho):
    """Regra do projeto: sem dado real, a tela mostra "—". Nada de valor de exemplo."""
    html = cliente.get(caminho).text
    assert not re.search(r"R\$\s*\d", html), "há um valor em reais escrito direto na página"
    assert "fictíci" not in html and "Exemplo" not in html
    assert "fonts.googleapis.com" not in html


def test_expressao_do_valor_em_reais_pega_um_valor_de_verdade():
    """O teste acima só vale se a expressão dele reconhecer um valor escrito na página."""
    assert re.search(r"R\$\s*\d", "<b>R$ 12,50</b>")
    assert re.search(r"R\$\s*\d", "Total: R$12")
    assert not re.search(r"R\$\s*\d", "Preço unit. (R$)")


def test_modulos_sem_tela_avisam_que_estao_em_construcao(cliente):
    html = cliente.get("/inicio").text
    assert html.count("em breve") >= 6
    assert "data-em-breve" in html
    # O Financeiro ainda é só o visual; as telas que já gravam dados não trazem o aviso.
    assert "Tela em construção" in cliente.get("/financeiro").text
    for tela in ("/caixa", "/controle-caixa", "/produtos", "/clientes", "/tabelas-preco"):
        assert "Tela em construção" not in cliente.get(tela).text, tela


@pytest.mark.parametrize("caminho", ["/caixa", "/controle-caixa", "/produtos", "/clientes"])
def test_telas_que_gravam_carregam_o_seu_script(cliente, caminho):
    html = cliente.get(caminho).text
    scripts = re.findall(r'<script src="(/static/js/[^"?]+)', html)
    assert len(scripts) == 2, scripts  # o comum (moleka.js) e o da tela
    assert scripts[0] == "/static/js/moleka.js"


def test_teclas_dos_menus_valem_em_todas_as_telas(cliente):
    """F2 (venda) e F11 (controle de caixa) saem dos menus, que estão em toda tela com moldura."""
    for caminho in ("/inicio", "/produtos", "/clientes", "/tabelas-preco", "/operadores"):
        html = cliente.get(caminho).text
        assert 'data-atalho-menu="F2"' in html, caminho
        assert 'data-atalho-menu="F11"' in html, caminho

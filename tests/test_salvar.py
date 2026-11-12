"""Gravar no computador a planilha que a tela pediu para salvar (app/salvar.py)."""

import base64
import os
from pathlib import Path

import pytest

from app import salvar


def test_nome_seguro():
    assert salvar.nome_seguro("Moleka - Vendas 01-11-2026 a 12-11-2026.xlsx") == (
        "Moleka - Vendas 01-11-2026 a 12-11-2026.xlsx"
    )
    # Sem pasta nenhuma, nem com ".." ou com a barra do Windows.
    assert salvar.nome_seguro("../../Windows/system32/x.xlsx") == "x.xlsx"
    assert salvar.nome_seguro("C:\\Users\\eric\\Desktop\\x.xlsx") == "x.xlsx"
    # Caracteres que o Windows recusa viram hífen; a extensão é sempre .xlsx.
    assert salvar.nome_seguro('Moleka: "DRE" <nov>?') == "Moleka- -DRE- -nov--.xlsx"
    assert salvar.nome_seguro("planilha.XLSX") == "planilha.xlsx"
    assert salvar.nome_seguro("relatorio.exe") == "relatorio.exe.xlsx"
    assert salvar.nome_seguro("") == "Moleka.xlsx"
    assert salvar.nome_seguro("...") == "Moleka.xlsx"
    longo = salvar.nome_seguro("a" * 400)
    assert len(longo) == 150 and longo.endswith(".xlsx")


def test_ler_conteudo():
    assert salvar.ler_conteudo(base64.b64encode(b"PK\x03\x04planilha").decode()) == (
        b"PK\x03\x04planilha"
    )
    assert salvar.ler_conteudo("") == "A planilha chegou vazia. Tente de novo."
    assert (
        salvar.ler_conteudo("isto não é base64!") == "A planilha chegou incompleta. Tente de novo."
    )
    grande = "A" * (salvar.LIMITE_BYTES * 2)
    assert "grande demais" in salvar.ler_conteudo(grande)


def test_caminho_escolhido(tmp_path):
    assert salvar.caminho_escolhido(None) is None
    assert salvar.caminho_escolhido(()) is None
    assert salvar.caminho_escolhido("") is None
    # O pywebview no Windows devolve uma tupla com o caminho; em outras versões, o texto.
    alvo = tmp_path / "Vendas.xlsx"
    assert salvar.caminho_escolhido((str(alvo),)) == alvo
    assert salvar.caminho_escolhido(str(alvo)) == alvo
    # A pessoa apagou a extensão do nome: ela volta.
    assert salvar.caminho_escolhido(str(tmp_path / "Vendas")) == tmp_path / "Vendas.xlsx"


def test_gravar_e_regravar(tmp_path):
    alvo = tmp_path / "Vendas.xlsx"
    assert salvar.gravar(alvo, b"primeira") == {"ok": True, "caminho": str(alvo), "erro": ""}
    assert alvo.read_bytes() == b"primeira"
    # Gravar de novo por cima (a janela do Windows já perguntou se pode substituir).
    assert salvar.gravar(alvo, b"segunda")["ok"]
    assert alvo.read_bytes() == b"segunda"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["Vendas.xlsx"]  # nada de provisório


def test_gravar_quando_o_windows_nao_deixa(tmp_path, monkeypatch):
    """Com a planilha aberta no Excel, o Windows recusa a troca: a mensagem diz o que fazer, a
    planilha antiga fica como estava e o provisório não fica para trás."""
    alvo = tmp_path / "Vendas.xlsx"
    alvo.write_bytes(b"antiga")

    def recusa(origem, destino):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(os, "replace", recusa)
    r = salvar.gravar(alvo, b"nova")
    assert r["ok"] is False
    assert r["erro"].startswith(
        "Não deu para gravar “Vendas.xlsx”: a planilha está aberta no Excel"
    )
    assert alvo.read_bytes() == b"antiga"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["Vendas.xlsx"]


def test_gravar_em_pasta_que_nao_existe(tmp_path):
    r = salvar.gravar(tmp_path / "nao-existe" / "Vendas.xlsx", b"x")
    assert r["ok"] is False and r["erro"].startswith("Não deu para gravar a planilha:")


@pytest.mark.parametrize("nome", ["Moleka - DRE 01-11-2026 a 30-11-2026.xlsx", "Ação ç ã.xlsx"])
def test_nomes_que_a_api_sugere_passam_inteiros(nome):
    assert salvar.nome_seguro(nome) == nome
    assert Path(salvar.nome_seguro(nome)).suffix == ".xlsx"

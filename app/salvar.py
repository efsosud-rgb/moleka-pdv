"""Gravar no computador um arquivo que a tela pediu para salvar (as planilhas do Excel).

A janela do programa (pywebview) não baixa arquivos como um navegador: a tela manda o conteúdo
para o Python (ver `Ponte.salvar_arquivo` em main.py), que abre a janela "Salvar como" do
Windows e grava onde a pessoa escolher. Aqui fica a parte que não depende da janela.
"""

from __future__ import annotations

import base64
import binascii
import os
import re
from pathlib import Path
from typing import Any

EXTENSAO = ".xlsx"
TIPOS_DO_DIALOGO = ("Planilha do Excel (*.xlsx)",)
LIMITE_BYTES = 30 * 1024 * 1024  # a planilha de um ano inteiro fica muito abaixo disso
_PROIBIDO = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_TAMANHO_DO_NOME = 150


def resultado(ok: bool, caminho: str = "", erro: str = "") -> dict[str, Any]:
    """O que volta para a tela (o pywebview entrega o dicionário ao JavaScript)."""
    return {"ok": ok, "caminho": caminho, "erro": erro}


def nome_seguro(nome: str) -> str:
    """Só o nome do arquivo, sem pasta e sem os caracteres que o Windows recusa, terminado em
    .xlsx. Ex.: "../Moleka: Vendas" -> "Moleka- Vendas.xlsx"."""
    base = Path(str(nome).replace("\\", "/")).name
    base = _PROIBIDO.sub("-", base).strip().strip(".").strip()
    if base.lower().endswith(EXTENSAO):
        base = base[: -len(EXTENSAO)].rstrip(" .")
    base = (base or "Moleka")[: _TAMANHO_DO_NOME - len(EXTENSAO)].rstrip(" .") or "Moleka"
    return base + EXTENSAO


def ler_conteudo(conteudo_base64: str) -> bytes | str:
    """Os bytes do arquivo, ou o texto do erro."""
    if not isinstance(conteudo_base64, str) or not conteudo_base64:
        return "A planilha chegou vazia. Tente de novo."
    if len(conteudo_base64) > LIMITE_BYTES * 4 // 3 + 4:
        return "A planilha ficou grande demais para salvar. Escolha um período menor."
    try:
        return base64.b64decode(conteudo_base64, validate=True)
    except (binascii.Error, ValueError):
        return "A planilha chegou incompleta. Tente de novo."


def caminho_escolhido(escolha: object) -> Path | None:
    """O caminho que a janela "Salvar como" devolveu (texto, ou lista/tupla com um texto), já
    terminado em .xlsx. None quando a pessoa desistiu."""
    if isinstance(escolha, (list, tuple)):
        escolha = escolha[0] if escolha else None
    if not escolha:
        return None
    caminho = Path(str(escolha))
    if caminho.suffix.lower() != EXTENSAO:
        caminho = caminho.with_name(caminho.name + EXTENSAO)
    return caminho


def gravar(caminho: Path, conteudo: bytes) -> dict[str, Any]:
    """Grava num arquivo provisório e troca de uma vez: um erro no meio não deixa planilha
    pela metade. Com a planilha antiga aberta no Excel, o Windows não deixa trocar."""
    provisorio = caminho.with_name(caminho.name + ".gravando")
    try:
        provisorio.write_bytes(conteudo)
        os.replace(provisorio, caminho)
    except PermissionError:
        provisorio.unlink(missing_ok=True)
        return resultado(
            False,
            erro=f"Não deu para gravar “{caminho.name}”: a planilha está aberta no Excel, ou a "
            "pasta não aceita gravação. Feche a planilha (ou escolha outra pasta) e tente de novo.",
        )
    except OSError as erro:
        try:
            provisorio.unlink(missing_ok=True)
        except OSError:
            pass
        return resultado(False, erro=f"Não deu para gravar a planilha: {erro.strerror or erro}.")
    return resultado(True, caminho=str(caminho))

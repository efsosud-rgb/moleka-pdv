"""Transforma um cupom (`app/cupom.py`) nos bytes que a impressora térmica entende (ESC/POS).

A ELGIN i9 do caixa usa a linguagem ESC/POS da Epson (ver DECISOES de 11/11/2026), a mesma da
maioria das térmicas de 80 mm. Só são usados comandos básicos: iniciar, página de código,
negrito, altura dupla, corte e abertura da gaveta. O alinhamento já vem feito com espaços.
"""

from __future__ import annotations

import unicodedata

from app.cupom import Cupom

INICIAR = b"\x1b@"  # ESC @: volta a impressora ao estado inicial
NEGRITO = {True: b"\x1bE\x01", False: b"\x1bE\x00"}  # ESC E n
TAMANHO = {True: b"\x1d!\x01", False: b"\x1d!\x00"}  # GS ! n: altura dupla ou normal
CORTAR = b"\x1dVB\x00"  # GS V 66 0: avança até a guilhotina e corta
AVANCAR = b"\n\n\n\n\n"  # sem guilhotina: sobe o papel para rasgar à mão
GAVETA = b"\x1bp\x00\x19\xfa"  # ESC p 0 25 250: pulso no conector da gaveta
# ESC t n: número da página de código na tabela da Epson, e o nome dela no Python.
PAGINAS: dict[str, tuple[int, str]] = {
    "cp850": (2, "cp850"),
    "cp860": (3, "cp860"),
    "cp1252": (16, "cp1252"),
}
# Sinais que as páginas de código não têm: trocados por parecidos antes de codificar.
TROCAS = str.maketrans(
    {"—": "-", "–": "-", "“": '"', "”": '"', "‘": "'", "’": "'", "…": "...", "·": "-", "•": "*"}
)


def _sem_acento(texto: str) -> str:
    texto = texto.replace("º", "o").replace("ª", "a")
    decomposto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in decomposto if unicodedata.category(c) != "Mn")


def texto_em_bytes(texto: str, acentos: str) -> bytes:
    """O texto na página de código escolhida. O que ela não tiver vira a letra sem acento
    ou, em último caso, "?"."""
    texto = texto.translate(TROCAS)
    if acentos not in PAGINAS:
        return _sem_acento(texto).encode("ascii", errors="replace")
    codec = PAGINAS[acentos][1]
    saida = bytearray()
    for letra in texto:
        try:
            saida += letra.encode(codec)
        except UnicodeEncodeError:
            saida += _sem_acento(letra).encode("ascii", errors="replace")
    return bytes(saida)


def codificar(cupom: Cupom, *, acentos: str, cortar: bool, vias: int = 1) -> bytes:
    """Os bytes de um cupom, prontos para a fila da impressora em modo RAW."""
    uma = bytearray(INICIAR)
    if acentos in PAGINAS:
        uma += b"\x1bt" + bytes([PAGINAS[acentos][0]])
    negrito = grande = False
    for linha in cupom.linhas:
        if linha.negrito != negrito:
            negrito = linha.negrito
            uma += NEGRITO[negrito]
        if linha.grande != grande:
            grande = linha.grande
            uma += TAMANHO[grande]
        uma += texto_em_bytes(linha.texto, acentos) + b"\n"
    uma += NEGRITO[False] + TAMANHO[False]
    uma += CORTAR if cortar else AVANCAR
    inicio = GAVETA if cupom.abre_gaveta else b""
    return inicio + bytes(uma) * max(vias, 1)

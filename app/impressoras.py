"""As impressoras do Windows: quais existem e como mandar um cupom para uma delas.

O cupom vai para a fila de impressão do Windows em modo RAW: os bytes ESC/POS chegam à
impressora térmica como estão, sem passar pelo desenho do driver. É assim que as térmicas de
cupom trabalham, e não abre nenhuma janela de impressão na frente do caixa.

Tudo é feito com as funções do próprio Windows (winspool.drv, via ctypes), sem biblioteca a
mais. Fora do Windows não há o que listar nem para onde mandar.

Para os testes automáticos existe uma impressora de mentira: com a variável de ambiente
MOLEKA_PDV_IMPRESSORA_EM_ARQUIVO apontando para uma pasta, a lista traz só ela, e cada
impressão vira um arquivo nessa pasta. Não é para uso na loja.
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.operadores import RegraError

log = logging.getLogger("moleka.impressoras")

NOME_DE_TESTE = "Impressora de teste (grava em arquivo)"
VARIAVEL_DE_TESTE = "MOLEKA_PDV_IMPRESSORA_EM_ARQUIVO"
_SO_NO_WINDOWS = "A impressão do cupom funciona só no Windows."


@dataclass(frozen=True)
class Impressora:
    nome: str
    padrao: bool = False  # é a impressora padrão do Windows


def _pasta_de_teste() -> Path | None:
    pasta = os.environ.get(VARIAVEL_DE_TESTE)
    return Path(pasta) if pasta else None


def disponivel() -> tuple[bool, str]:
    """(dá para imprimir neste computador?, motivo quando não dá)."""
    if _pasta_de_teste() is not None or sys.platform == "win32":
        return True, ""
    return False, _SO_NO_WINDOWS


def listar() -> list[Impressora]:
    """As impressoras instaladas, em ordem alfabética, com a padrão do Windows marcada."""
    if _pasta_de_teste() is not None:
        return [Impressora(NOME_DE_TESTE, padrao=True)]
    if sys.platform != "win32":
        return []
    try:
        return _listar_no_windows()
    except RegraError:
        raise
    except Exception as erro:  # a lista de impressoras não pode derrubar a tela
        log.exception("não consegui listar as impressoras do Windows")
        raise RegraError(
            f"Não consegui ler a lista de impressoras do Windows: {erro}", status=500
        ) from erro


def enviar(nome: str, dados: bytes, titulo: str) -> None:
    """Põe os bytes na fila da impressora. Erro vira RegraError com o motivo em português.

    Quando esta função volta sem erro, o Windows ACEITOU o trabalho na fila. Se saiu papel, só
    quem está olhando para a impressora sabe (sem papel, desligada e cabo solto ficam na fila).
    """
    if not nome:
        raise RegraError("Nenhuma impressora de cupom escolhida em Configurações.", status=409)
    if not dados:
        raise RegraError("Não há o que imprimir.")
    pasta = _pasta_de_teste()
    if pasta is not None:
        if nome != NOME_DE_TESTE:
            raise RegraError(f"A impressora “{nome}” não existe neste computador.", status=409)
        try:
            pasta.mkdir(parents=True, exist_ok=True)
            numero = len(list(pasta.glob("impressao-*.bin"))) + 1
            (pasta / f"impressao-{numero:03d}.bin").write_bytes(dados)
        except OSError as erro:
            motivo = erro.strerror or str(erro)
            raise RegraError(f"Não consegui imprimir em “{nome}”: {motivo}.", status=409) from erro
        return
    if sys.platform != "win32":
        raise RegraError(_SO_NO_WINDOWS, status=409)
    try:
        _enviar_no_windows(nome, dados, titulo)
    except RegraError:
        raise
    except Exception as erro:  # qualquer falha do Windows vira recado, nunca tela de erro
        log.exception("impressão em %s falhou", nome)
        raise RegraError(f"Não consegui imprimir em “{nome}”: {erro}.", status=409) from erro
    log.info("cupom enviado para a fila de %s: %s (%d bytes)", nome, titulo, len(dados))


# ---------------------------------------------------------------- Windows (winspool.drv)

_ENUM_LOCAL = 0x00000002
_ENUM_CONEXOES = 0x00000004
_ERRO_BUFFER_PEQUENO = 122
_MOTIVOS = {
    2: "o Windows não achou a impressora",
    5: "o Windows não deu permissão para usar esta impressora",
    1722: "o serviço de impressão do Windows não respondeu",
    1801: "o nome da impressora não existe mais no Windows",
    1905: "a impressora foi removida do Windows",
    3012: "nenhuma impressora foi encontrada",
}


def _spooler() -> Any:
    """As funções de impressão do Windows, com os tipos de cada argumento declarados."""
    if sys.platform != "win32":  # o resto só existe no Windows
        raise RuntimeError(_SO_NO_WINDOWS)
    from ctypes import wintypes

    dll = ctypes.WinDLL("winspool.drv", use_last_error=True)
    dll.OpenPrinterW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.HANDLE), ctypes.c_void_p]
    dll.OpenPrinterW.restype = wintypes.BOOL
    dll.ClosePrinter.argtypes = [wintypes.HANDLE]
    dll.ClosePrinter.restype = wintypes.BOOL
    dll.StartDocPrinterW.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p]
    dll.StartDocPrinterW.restype = wintypes.DWORD
    dll.EndDocPrinter.argtypes = [wintypes.HANDLE]
    dll.EndDocPrinter.restype = wintypes.BOOL
    dll.StartPagePrinter.argtypes = [wintypes.HANDLE]
    dll.StartPagePrinter.restype = wintypes.BOOL
    dll.EndPagePrinter.argtypes = [wintypes.HANDLE]
    dll.EndPagePrinter.restype = wintypes.BOOL
    dll.WritePrinter.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    dll.WritePrinter.restype = wintypes.BOOL
    dll.EnumPrintersW.argtypes = [
        wintypes.DWORD,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
    ]
    dll.EnumPrintersW.restype = wintypes.BOOL
    dll.GetDefaultPrinterW.argtypes = [wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    dll.GetDefaultPrinterW.restype = wintypes.BOOL
    return dll


def _motivo(codigo: int) -> str:
    return _MOTIVOS.get(codigo, f"erro {codigo} do Windows")


def _listar_no_windows() -> list[Impressora]:
    if sys.platform != "win32":  # o resto só existe no Windows
        raise RuntimeError(_SO_NO_WINDOWS)
    from ctypes import wintypes

    class Info4(ctypes.Structure):  # PRINTER_INFO_4W: só o nome, sem consultar a rede
        _fields_ = [
            ("pPrinterName", wintypes.LPWSTR),
            ("pServerName", wintypes.LPWSTR),
            ("Attributes", wintypes.DWORD),
        ]

    dll = _spooler()
    tipos = _ENUM_LOCAL | _ENUM_CONEXOES
    preciso = wintypes.DWORD(0)
    quantas = wintypes.DWORD(0)
    # Primeiro pedido sem memória nenhuma, só para o Windows dizer de quanto precisa. Se ele
    # responde "deu certo", é porque não há impressora instalada. Qualquer outra recusa (serviço
    # de impressão parado, por exemplo) é falha, e não "nenhuma impressora".
    if dll.EnumPrintersW(tipos, None, 4, None, 0, ctypes.byref(preciso), ctypes.byref(quantas)):
        return []
    codigo = ctypes.get_last_error()
    if codigo != _ERRO_BUFFER_PEQUENO or preciso.value == 0:
        log.warning("o Windows não listou as impressoras: erro %d", codigo)
        raise RegraError(
            f"O Windows não entregou a lista de impressoras: {_motivo(codigo)}.", status=500
        )
    memoria = ctypes.create_string_buffer(preciso.value)
    feito = dll.EnumPrintersW(
        tipos, None, 4, memoria, preciso.value, ctypes.byref(preciso), ctypes.byref(quantas)
    )
    if not feito:
        motivo = _motivo(ctypes.get_last_error())
        log.warning("o Windows não listou as impressoras: %s", motivo)
        raise RegraError(f"O Windows não entregou a lista de impressoras: {motivo}.", status=500)
    registros = ctypes.cast(memoria, ctypes.POINTER(Info4))
    nomes = sorted(
        {registros[i].pPrinterName for i in range(quantas.value) if registros[i].pPrinterName},
        key=str.casefold,
    )
    padrao = _padrao_do_windows(dll)
    return [Impressora(nome, padrao=nome == padrao) for nome in nomes]


def _padrao_do_windows(dll: Any) -> str:
    if sys.platform != "win32":  # o resto só existe no Windows
        raise RuntimeError(_SO_NO_WINDOWS)
    from ctypes import wintypes

    tamanho = wintypes.DWORD(0)
    dll.GetDefaultPrinterW(None, ctypes.byref(tamanho))
    if ctypes.get_last_error() != _ERRO_BUFFER_PEQUENO or tamanho.value == 0:
        return ""
    nome = ctypes.create_unicode_buffer(tamanho.value)
    if not dll.GetDefaultPrinterW(nome, ctypes.byref(tamanho)):
        return ""
    return nome.value


def _enviar_no_windows(nome: str, dados: bytes, titulo: str) -> None:
    if sys.platform != "win32":  # o resto só existe no Windows
        raise RuntimeError(_SO_NO_WINDOWS)
    from ctypes import wintypes

    class DocInfo1(ctypes.Structure):  # DOC_INFO_1W
        _fields_ = [
            ("pDocName", wintypes.LPWSTR),
            ("pOutputFile", wintypes.LPWSTR),
            ("pDatatype", wintypes.LPWSTR),
        ]

    def falha(etapa: str) -> RegraError:
        codigo = ctypes.get_last_error()
        log.warning("impressão em %s falhou ao %s: erro %d", nome, etapa, codigo)
        return RegraError(
            f"Não consegui imprimir em “{nome}”: {_motivo(codigo)}. Confira se a impressora "
            "está ligada e instalada no Windows.",
            status=409,
        )

    dll = _spooler()
    fila = wintypes.HANDLE()
    if not dll.OpenPrinterW(nome, ctypes.byref(fila), None):
        raise falha("abrir a impressora")
    try:
        documento = DocInfo1(titulo[:60] or "Moleka PDV", None, "RAW")
        if dll.StartDocPrinterW(fila, 1, ctypes.byref(documento)) == 0:
            raise falha("começar o trabalho")
        try:
            if not dll.StartPagePrinter(fila):
                raise falha("começar a página")
            escritos = wintypes.DWORD(0)
            memoria = (ctypes.c_char * len(dados)).from_buffer_copy(dados)
            pronto = dll.WritePrinter(fila, memoria, len(dados), ctypes.byref(escritos))
            if not pronto or escritos.value != len(dados):
                raise falha("mandar o cupom")
            dll.EndPagePrinter(fila)
        finally:
            dll.EndDocPrinter(fila)
    finally:
        dll.ClosePrinter(fila)

"""Segredos do sistema: a senha do certificado digital e os códigos CSC da NFC-e.

Ficam FORA do banco de dados e, por isso, fora da cópia de segurança: um arquivo por segredo em
`<dados>/segredos/` (no Windows, %APPDATA%\\MolekaPDV\\segredos). Nada daqui vai para o log, para a
tela ou para as respostas da API.

- Windows (o programa da loja): o texto é cifrado pela DPAPI do Windows (CryptProtectData), presa
  ao usuário do Windows que usa o programa. Outro usuário, ou o arquivo copiado para outro
  computador, não abre. Se o administrador redefinir a senha desse usuário do Windows (o próprio
  usuário trocar a senha não faz mal), o Windows pode perder a chave e o segredo tem de ser
  digitado de novo.
- Outros sistemas (desenvolvimento e testes automáticos): o texto fica sem cifra, num arquivo que
  só o dono lê (permissão 600). Não é usado na loja.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from app import config

NOMES = frozenset({"certificado-senha", "csc-homologacao", "csc-producao"})
# Cabeçalho de cada arquivo: diz como o resto foi gravado.
_DPAPI = b"MOLEKA-DPAPI-1\n"
_TEXTO = b"MOLEKA-TEXTO-1\n"
# "Entropia" da DPAPI: outro programa do mesmo usuário precisa saber este texto para abrir.
_ENTROPIA = b"MolekaPDV-segredos"


class SegredoError(RuntimeError):
    """Não deu para gravar ou ler um segredo. `str(erro)` é a mensagem para o usuário."""


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    class _Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.c_void_p)]

    _SEM_PERGUNTAR = 0x01  # CRYPTPROTECT_UI_FORBIDDEN: nunca abrir janela do Windows

    def _dpapi(dados: bytes, cifrar: bool) -> bytes:
        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        funcao = crypt32.CryptProtectData if cifrar else crypt32.CryptUnprotectData
        funcao.argtypes = [
            ctypes.POINTER(_Blob),
            ctypes.c_void_p,
            ctypes.POINTER(_Blob),
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(_Blob),
        ]
        funcao.restype = wintypes.BOOL
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        memoria = ctypes.create_string_buffer(dados, len(dados))
        entrada = _Blob(len(dados), ctypes.cast(memoria, ctypes.c_void_p))
        memoria_entropia = ctypes.create_string_buffer(_ENTROPIA, len(_ENTROPIA))
        entropia = _Blob(len(_ENTROPIA), ctypes.cast(memoria_entropia, ctypes.c_void_p))
        saida = _Blob()
        if not funcao(
            ctypes.byref(entrada),
            None,
            ctypes.byref(entropia),
            None,
            None,
            _SEM_PERGUNTAR,
            ctypes.byref(saida),
        ):
            codigo = ctypes.get_last_error()
            raise SegredoError(
                "O Windows não conseguiu "
                + ("guardar" if cifrar else "abrir")
                + f" o dado protegido (código {codigo})."
            )
        try:
            return ctypes.string_at(saida.pbData, saida.cbData)
        finally:
            kernel32.LocalFree(saida.pbData)


def pasta() -> Path:
    destino = config.pasta_dados() / "segredos"
    destino.mkdir(exist_ok=True)
    return destino


def _arquivo(nome: str) -> Path:
    if nome not in NOMES:
        raise ValueError(f"segredo desconhecido: {nome}")
    return pasta() / nome


def gravar(nome: str, valor: str) -> None:
    """Grava (ou troca) o segredo. Texto vazio apaga."""
    arquivo = _arquivo(nome)
    if not valor:
        apagar(nome)
        return
    dados = valor.encode("utf-8")
    if sys.platform == "win32":
        conteudo = _DPAPI + _dpapi(dados, cifrar=True)
    else:
        conteudo = _TEXTO + dados
    provisorio = arquivo.with_name(arquivo.name + ".gravando")
    descritor = os.open(provisorio, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descritor, "wb") as saida:
            saida.write(conteudo)
        os.replace(provisorio, arquivo)
    except OSError as erro:
        provisorio.unlink(missing_ok=True)
        raise SegredoError(f"Não consegui gravar o dado protegido: {erro.strerror}.") from erro


def ler(nome: str) -> str | None:
    """O segredo, ou None quando não há nenhum gravado."""
    arquivo = _arquivo(nome)
    try:
        conteudo = arquivo.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as erro:
        raise SegredoError(f"Não consegui ler o dado protegido: {erro.strerror}.") from erro
    if conteudo.startswith(_TEXTO):
        return conteudo[len(_TEXTO) :].decode("utf-8")
    if conteudo.startswith(_DPAPI):
        if sys.platform == "win32":
            return _dpapi(conteudo[len(_DPAPI) :], cifrar=False).decode("utf-8")
        raise SegredoError("Este dado foi protegido pelo Windows e só abre no Windows.")
    raise SegredoError("O arquivo do dado protegido está estragado. Digite de novo.")


def existe(nome: str) -> bool:
    return _arquivo(nome).is_file()


def apagar(nome: str) -> None:
    _arquivo(nome).unlink(missing_ok=True)

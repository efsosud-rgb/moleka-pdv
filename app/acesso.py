"""Quem está usando o sistema agora: sessões de login e permissões por perfil.

A sessão fica só na memória do programa: fechou o Moleka PDV, todos precisam entrar de novo.
O navegador da janela guarda apenas um código sorteado, num cookie que o JavaScript não lê
(`HttpOnly`) e que não acompanha pedidos vindos de outros sites (`SameSite=Strict`).

Perfis (ver docs/ESPECIFICACAO.md §12):
- operador: vende, opera o caixa e cadastra clientes;
- gerente: tudo o que o operador faz, mais produtos, preços, financeiro, fiscal e operadores.
"""

from __future__ import annotations

import math
import secrets
import threading
import time
from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app import db
from app.models import Operador, Perfil

COOKIE = "moleka_sessao"


class Sessoes:
    """Código da sessão → operador. Uma por aplicação (`app.state.sessoes`)."""

    def __init__(self) -> None:
        self._trava = threading.Lock()
        self._operador_por_codigo: dict[str, int] = {}

    def abrir(self, operador_id: int) -> str:
        codigo = secrets.token_urlsafe(32)
        with self._trava:
            self._operador_por_codigo[codigo] = operador_id
        return codigo

    def operador_id(self, codigo: str | None) -> int | None:
        if not codigo:
            return None
        with self._trava:
            return self._operador_por_codigo.get(codigo)

    def fechar(self, codigo: str | None) -> None:
        if not codigo:
            return
        with self._trava:
            self._operador_por_codigo.pop(codigo, None)

    def fechar_do_operador(self, operador_id: int, *, menos: str | None = None) -> None:
        """Derruba as sessões de um operador (senha trocada ou cadastro inativado)."""
        with self._trava:
            for codigo in [c for c, o in self._operador_por_codigo.items() if o == operador_id]:
                if codigo != menos:
                    del self._operador_por_codigo[codigo]


class Tentativas:
    """Freio contra adivinhação de senha: depois de `LIMITE` erros seguidos, espera `ESPERA` s."""

    LIMITE = 5
    ESPERA = 30
    _MAXIMO_DE_USUARIOS = 500  # a lista não cresce sem fim se alguém inventar usuários

    def __init__(self, relogio: Callable[[], float] = time.monotonic) -> None:
        self._relogio = relogio
        self._trava = threading.Lock()
        self._erros: dict[str, int] = {}
        self._liberado_em: dict[str, float] = {}

    def espera(self, login: str) -> int:
        """Segundos que faltam para este usuário poder tentar de novo (0 = pode tentar)."""
        with self._trava:
            falta = self._liberado_em.get(login, 0.0) - self._relogio()
            if falta <= 0:
                self._liberado_em.pop(login, None)
                return 0
            return math.ceil(falta)

    def errou(self, login: str) -> None:
        with self._trava:
            agora = self._relogio()
            if len(self._erros) >= self._MAXIMO_DE_USUARIOS and login not in self._erros:
                self._erros.clear()
            if len(self._liberado_em) >= self._MAXIMO_DE_USUARIOS:
                self._liberado_em = {u: t for u, t in self._liberado_em.items() if t > agora}
            erros = self._erros.get(login, 0) + 1
            if erros >= self.LIMITE:
                self._erros.pop(login, None)
                self._liberado_em[login] = agora + self.ESPERA
            else:
                self._erros[login] = erros

    def acertou(self, login: str) -> None:
        with self._trava:
            self._erros.pop(login, None)
            self._liberado_em.pop(login, None)


# ---------------------------------------------------------------- cookie da sessão


def gravar_cookie(resposta: Response, codigo: str) -> None:
    # Sem prazo: o cookie some quando a janela do programa fecha. Sem `secure`: o servidor
    # é local (http://127.0.0.1) e não sai deste computador.
    resposta.set_cookie(COOKIE, codigo, httponly=True, samesite="strict", path="/")


def apagar_cookie(resposta: Response) -> None:
    resposta.delete_cookie(COOKIE, httponly=True, samesite="strict", path="/")


# ---------------------------------------------------------------- dependências do FastAPI


def sessoes(request: Request) -> Sessoes:
    armazem: Sessoes = request.app.state.sessoes
    return armazem


def tentativas(request: Request) -> Tentativas:
    freio: Tentativas = request.app.state.tentativas
    return freio


def operador_opcional(request: Request, sessao: Session = Depends(db.sessao)) -> Operador | None:
    """O operador que está com a sessão aberta nesta janela, ou None."""
    codigo = request.cookies.get(COOKIE)
    armazem = sessoes(request)
    operador_id = armazem.operador_id(codigo)
    if operador_id is None:
        return None
    operador = sessao.get(Operador, operador_id)
    if operador is None or not operador.ativo:
        armazem.fechar(codigo)
        return None
    return operador


def exigir_operador(operador: Operador | None = Depends(operador_opcional)) -> Operador:
    if operador is None:
        raise HTTPException(401, "Entre com o seu usuário e senha para continuar.")
    return operador


def exigir_gerente(operador: Operador = Depends(exigir_operador)) -> Operador:
    if operador.perfil != Perfil.GERENTE:
        raise HTTPException(403, "Só o gerente pode fazer isso.")
    return operador


def e_gerente(operador: Operador | None) -> bool:
    return operador is not None and operador.perfil == Perfil.GERENTE

"""Entrada no sistema e cadastro de operadores.

- `/api/sessao`: quem está logado nesta janela e se o sistema já tem operador.
- `/api/configuracao-inicial`: cria o primeiro gerente (só funciona enquanto não houver nenhum).
- `/api/login`, `/api/sair`, `/api/minha-senha`.
- `/api/operadores`: listar, criar e alterar (só o gerente). Operador não é apagado: fica inativo.

A senha nunca volta numa resposta nem vai para o log.
"""

from __future__ import annotations

import logging
import threading

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import acesso, db, operadores, seguranca
from app.models import Operador, Perfil

router = APIRouter(tags=["acesso"])
log = logging.getLogger("moleka.acesso")

_trava_da_configuracao_inicial = threading.Lock()


class OperadorOut(BaseModel):
    id: int
    nome: str
    login: str
    perfil: Perfil
    ativo: bool


class SessaoOut(BaseModel):
    configurado: bool  # já existe pelo menos um operador cadastrado
    operador: OperadorOut | None  # quem está logado nesta janela


class PrimeiroGerenteIn(BaseModel):
    nome: str
    login: str
    senha: str


class LoginIn(BaseModel):
    login: str
    senha: str


class MinhaSenhaIn(BaseModel):
    senha_atual: str
    senha_nova: str


class OperadorIn(BaseModel):
    nome: str
    login: str
    senha: str
    perfil: Perfil = Perfil.OPERADOR
    ativo: bool = True


class OperadorAlteracao(BaseModel):
    nome: str
    login: str
    perfil: Perfil
    ativo: bool
    senha: str | None = None  # vazio = não muda a senha


def _saida(operador: Operador) -> OperadorOut:
    return OperadorOut(
        id=operador.id,
        nome=operador.nome,
        login=operador.login,
        perfil=operador.perfil,
        ativo=operador.ativo,
    )


def _abrir_sessao(request: Request, resposta: Response, operador: Operador) -> None:
    armazem = acesso.sessoes(request)
    armazem.fechar(request.cookies.get(acesso.COOKIE))  # troca de operador na mesma janela
    acesso.gravar_cookie(resposta, armazem.abrir(operador.id))


# ---------------------------------------------------------------- sessão


@router.get("/sessao", response_model=SessaoOut)
def sessao_atual(
    operador: Operador | None = Depends(acesso.operador_opcional),
    sessao: Session = Depends(db.sessao),
) -> SessaoOut:
    return SessaoOut(
        configurado=operadores.existe_algum(sessao),
        operador=_saida(operador) if operador else None,
    )


@router.post("/configuracao-inicial", response_model=OperadorOut, status_code=201)
def configuracao_inicial(
    dados: PrimeiroGerenteIn,
    request: Request,
    resposta: Response,
    sessao: Session = Depends(db.sessao),
) -> OperadorOut:
    """Primeiro acesso: cria o gerente e já entra com ele."""
    with _trava_da_configuracao_inicial:
        if operadores.existe_algum(sessao):
            raise HTTPException(
                409, "A configuração inicial já foi feita. Entre com o seu usuário e senha."
            )
        gerente = operadores.criar(
            sessao, nome=dados.nome, login=dados.login, senha=dados.senha, perfil=Perfil.GERENTE
        )
    _abrir_sessao(request, resposta, gerente)
    log.info("configuração inicial: gerente %s criado", gerente.login)
    return _saida(gerente)


@router.post("/login", response_model=OperadorOut)
def entrar(
    dados: LoginIn,
    request: Request,
    resposta: Response,
    sessao: Session = Depends(db.sessao),
) -> OperadorOut:
    login = operadores.normalizar_login(dados.login)[:30]
    freio = acesso.tentativas(request)
    espera = freio.espera(login)
    if espera:
        raise HTTPException(
            429,
            f"Muitas tentativas com a senha errada. Aguarde {espera} segundos e tente de novo.",
            headers={"Retry-After": str(espera)},
        )
    operador = operadores.por_login(sessao, login)
    if operador is None:
        seguranca.gastar_tempo_de_uma_conferencia(dados.senha)
        senha_certa = False
    else:
        senha_certa = seguranca.conferir(dados.senha, operador.senha_hash)
    if operador is None or not senha_certa:
        freio.errou(login)
        log.warning("login recusado: usuário %s", login)
        raise HTTPException(401, "Usuário ou senha incorretos.")
    if not operador.ativo:
        log.warning("login recusado: usuário %s está inativo", login)
        raise HTTPException(403, "Este operador está inativo. Fale com o gerente.")
    freio.acertou(login)
    _abrir_sessao(request, resposta, operador)
    log.info("login: %s (%s)", operador.login, operador.perfil.value)
    return _saida(operador)


@router.post("/sair", status_code=204)
def sair(
    request: Request,
    resposta: Response,
    operador: Operador | None = Depends(acesso.operador_opcional),
) -> None:
    if operador is not None:
        log.info("saída: %s", operador.login)
    acesso.sessoes(request).fechar(request.cookies.get(acesso.COOKIE))
    acesso.apagar_cookie(resposta)


@router.post("/minha-senha", status_code=204)
def trocar_minha_senha(
    dados: MinhaSenhaIn,
    request: Request,
    operador: Operador = Depends(acesso.exigir_operador),
    sessao: Session = Depends(db.sessao),
) -> None:
    operadores.trocar_senha(sessao, operador, atual=dados.senha_atual, nova=dados.senha_nova)
    # Quem estiver com a senha antiga em outra janela precisa entrar de novo.
    acesso.sessoes(request).fechar_do_operador(
        operador.id, menos=request.cookies.get(acesso.COOKIE)
    )
    log.info("senha trocada pelo próprio operador: %s", operador.login)


# ---------------------------------------------------------------- operadores (só o gerente)


@router.get("/operadores", response_model=list[OperadorOut])
def listar_operadores(
    _gerente: Operador = Depends(acesso.exigir_gerente),
    sessao: Session = Depends(db.sessao),
) -> list[OperadorOut]:
    return [_saida(o) for o in operadores.listar(sessao)]


@router.post("/operadores", response_model=OperadorOut, status_code=201)
def criar_operador(
    dados: OperadorIn,
    gerente: Operador = Depends(acesso.exigir_gerente),
    sessao: Session = Depends(db.sessao),
) -> OperadorOut:
    novo = operadores.criar(
        sessao,
        nome=dados.nome,
        login=dados.login,
        senha=dados.senha,
        perfil=dados.perfil,
        ativo=dados.ativo,
    )
    log.info("operador %s (%s) criado por %s", novo.login, novo.perfil.value, gerente.login)
    return _saida(novo)


@router.put("/operadores/{operador_id}", response_model=OperadorOut)
def alterar_operador(
    operador_id: int,
    dados: OperadorAlteracao,
    request: Request,
    gerente: Operador = Depends(acesso.exigir_gerente),
    sessao: Session = Depends(db.sessao),
) -> OperadorOut:
    alvo = sessao.get(Operador, operador_id)
    if alvo is None:
        raise HTTPException(404, "Operador não encontrado.")
    mudancas = operadores.alterar(
        sessao,
        alvo,
        autor=gerente,
        nome=dados.nome,
        login=dados.login,
        perfil=dados.perfil,
        ativo=dados.ativo,
        senha=dados.senha or None,
    )
    if alvo.id != gerente.id and ("senha" in mudancas or not alvo.ativo):
        acesso.sessoes(request).fechar_do_operador(alvo.id)
    if mudancas:
        log.info("operador %s alterado por %s: %s", alvo.login, gerente.login, ", ".join(mudancas))
    return _saida(alvo)

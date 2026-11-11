"""Regras do cadastro de operadores: quem pode entrar no sistema e com qual perfil.

Usado pela API (`app/api/login.py`) e pela recuperação de acesso (`main.py --redefinir-senha`).
As funções levantam `RegraError` com a mensagem pronta para mostrar na tela.

Regras:
- operador nunca é apagado: fica inativo (o histórico de vendas e de caixa aponta para ele);
- o usuário (login) é único, em minúsculas, sem espaços;
- ninguém inativa nem rebaixa o próprio usuário. Como só um gerente ativo altera operadores,
  essa regra garante que sempre sobra pelo menos um gerente ativo.
"""

from __future__ import annotations

import logging
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import seguranca
from app.models import Operador, Perfil

log = logging.getLogger("moleka.acesso")

_LOGIN_VALIDO = re.compile(r"[a-z0-9][a-z0-9._-]{1,29}")


class RegraError(ValueError):
    """Uma regra do sistema impediu a operação. `str(erro)` é a mensagem para o usuário."""

    def __init__(self, mensagem: str, status: int = 422) -> None:
        super().__init__(mensagem)
        self.status = status


# ---------------------------------------------------------------- validação dos campos


def normalizar_login(texto: str) -> str:
    return texto.strip().lower()


def validar_nome(texto: str) -> str:
    nome = " ".join(texto.split())
    if not nome:
        raise RegraError("Digite o nome do operador.")
    if len(nome) > 80:
        raise RegraError("O nome pode ter no máximo 80 letras.")
    return nome


def validar_login(texto: str) -> str:
    login = normalizar_login(texto)
    if not _LOGIN_VALIDO.fullmatch(login):
        raise RegraError(
            "O usuário deve ter de 2 a 30 caracteres, só com letras sem acento, números, "
            "ponto, traço ou sublinhado, sem espaços. Por exemplo: maria ou caixa1."
        )
    return login


def validar_senha(senha: str) -> str:
    if len(senha) < seguranca.SENHA_MINIMA:
        raise RegraError(f"A senha precisa ter pelo menos {seguranca.SENHA_MINIMA} caracteres.")
    if len(senha) > seguranca.SENHA_MAXIMA:
        raise RegraError(f"A senha pode ter no máximo {seguranca.SENHA_MAXIMA} caracteres.")
    return senha


# ---------------------------------------------------------------- consultas


def existe_algum(sessao: Session) -> bool:
    return (sessao.scalar(select(func.count()).select_from(Operador)) or 0) > 0


def por_login(sessao: Session, login: str) -> Operador | None:
    return sessao.scalar(select(Operador).where(Operador.login == normalizar_login(login)))


def listar(sessao: Session, *, so_ativos: bool = False) -> list[Operador]:
    consulta = select(Operador).order_by(func.lower(Operador.nome), Operador.id)
    if so_ativos:
        consulta = consulta.where(Operador.ativo.is_(True))
    return list(sessao.scalars(consulta))


# ---------------------------------------------------------------- alterações


def criar(
    sessao: Session, *, nome: str, login: str, senha: str, perfil: Perfil, ativo: bool = True
) -> Operador:
    nome = validar_nome(nome)
    login = validar_login(login)
    validar_senha(senha)
    if por_login(sessao, login) is not None:
        raise RegraError(f"Já existe um operador com o usuário “{login}”.", status=409)
    operador = Operador(
        nome=nome, login=login, senha_hash=seguranca.gerar_hash(senha), perfil=perfil, ativo=ativo
    )
    sessao.add(operador)
    sessao.commit()
    return operador


def alterar(
    sessao: Session,
    alvo: Operador,
    *,
    autor: Operador,
    nome: str,
    login: str,
    perfil: Perfil,
    ativo: bool,
    senha: str | None = None,
) -> list[str]:
    """Altera o cadastro de `alvo` a pedido de `autor`. Devolve a lista do que mudou."""
    nome = validar_nome(nome)
    login = validar_login(login)
    if senha:
        validar_senha(senha)
    if alvo.id == autor.id and (not ativo or perfil != alvo.perfil):
        raise RegraError(
            "Você não pode inativar nem mudar o perfil do seu próprio usuário. "
            "Peça a outro gerente.",
            status=409,
        )
    outro = por_login(sessao, login)
    if outro is not None and outro.id != alvo.id:
        raise RegraError(f"Já existe um operador com o usuário “{login}”.", status=409)

    mudancas: list[str] = []
    if alvo.nome != nome:
        alvo.nome = nome
        mudancas.append("nome")
    if alvo.login != login:
        alvo.login = login
        mudancas.append("usuário")
    if alvo.perfil != perfil:
        alvo.perfil = perfil
        mudancas.append(f"perfil ({perfil.value})")
    if alvo.ativo != ativo:
        alvo.ativo = ativo
        mudancas.append("reativado" if ativo else "inativado")
    if senha:
        alvo.senha_hash = seguranca.gerar_hash(senha)
        mudancas.append("senha")
    sessao.commit()
    return mudancas


def trocar_senha(sessao: Session, operador: Operador, *, atual: str, nova: str) -> None:
    """Troca a senha do próprio operador, que precisa provar que sabe a atual."""
    if not seguranca.conferir(atual, operador.senha_hash):
        raise RegraError("A senha atual não confere.", status=403)
    validar_senha(nova)
    if nova == atual:
        raise RegraError("A senha nova é igual à atual. Escolha outra.")
    operador.senha_hash = seguranca.gerar_hash(nova)
    sessao.commit()


def redefinir_senha(sessao: Session, login: str | None) -> tuple[Operador, str]:
    """Recuperação de acesso: sorteia uma senha provisória e reativa o operador.

    Sem `login`, vale para o gerente, desde que só exista um. Devolve o operador e a senha
    provisória, que não é gravada em lugar nenhum: quem chamou mostra na tela uma única vez.
    """
    if login:
        alvo = por_login(sessao, login)
        if alvo is None:
            conhecidos = ", ".join(o.login for o in listar(sessao)) or "nenhum"
            raise RegraError(
                f"Não existe operador com o usuário “{normalizar_login(login)}”. "
                f"Usuários cadastrados: {conhecidos}."
            )
    else:
        gerentes = [o for o in listar(sessao) if o.perfil == Perfil.GERENTE]
        if not gerentes:
            raise RegraError(
                "Ainda não existe gerente cadastrado. Abra o sistema: a tela inicial cria o "
                "primeiro gerente."
            )
        if len(gerentes) > 1:
            raise RegraError(
                "Há mais de um gerente. Diga de qual usuário é a senha: "
                + ", ".join(o.login for o in gerentes)
                + "."
            )
        alvo = gerentes[0]
    provisoria = seguranca.senha_provisoria()
    alvo.senha_hash = seguranca.gerar_hash(provisoria)
    alvo.ativo = True
    sessao.commit()
    log.warning("senha redefinida pela recuperação de acesso: usuário %s", alvo.login)
    return alvo, provisoria

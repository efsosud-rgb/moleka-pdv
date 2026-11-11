"""Senhas dos operadores: o banco guarda só o hash (scrypt), nunca a senha.

Formato gravado em `operador.senha_hash`:

    scrypt$<n>$<r>$<p>$<sal em base64>$<hash em base64>

Os parâmetros vão junto com o hash para que possam ser aumentados no futuro sem invalidar as
senhas já cadastradas. `scrypt` vem com o Python (`hashlib`): não acrescenta dependência.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from functools import cache

SENHA_MINIMA = 4
SENHA_MAXIMA = 128

# Custo de cada verificação: 16 MB de memória e algumas dezenas de milissegundos.
# Pesado para quem tenta adivinhar senhas em massa, leve para o PC do caixa (i3, 4 GB).
_N = 2**14
_R = 8
_P = 1
_TAMANHO_DO_SAL = 16
_TAMANHO_DO_HASH = 32
_MEMORIA_MAXIMA = 64 * 1024 * 1024
# Limites aceitos ao ler um hash gravado (protege contra um banco adulterado travar o caixa).
_N_MAXIMO = 2**17
_R_MAXIMO = 16
_P_MAXIMO = 4


def _derivar(senha: str, sal: bytes, n: int, r: int, p: int, tamanho: int) -> bytes:
    return hashlib.scrypt(
        senha.encode("utf-8"), salt=sal, n=n, r=r, p=p, dklen=tamanho, maxmem=_MEMORIA_MAXIMA
    )


def _b64(dados: bytes) -> str:
    return base64.b64encode(dados).decode("ascii")


def gerar_hash(senha: str) -> str:
    """Devolve o texto a gravar no banco para esta senha (sal novo a cada chamada)."""
    sal = secrets.token_bytes(_TAMANHO_DO_SAL)
    derivada = _derivar(senha, sal, _N, _R, _P, _TAMANHO_DO_HASH)
    return "$".join(("scrypt", str(_N), str(_R), str(_P), _b64(sal), _b64(derivada)))


def conferir(senha: str, gravado: str) -> bool:
    """Diz se a senha digitada é a que gerou o hash gravado. Hash malformado nunca confere."""
    try:
        esquema, n_txt, r_txt, p_txt, sal_txt, esperado_txt = gravado.split("$")
        if esquema != "scrypt":
            return False
        n, r, p = int(n_txt), int(r_txt), int(p_txt)
        if not (1 < n <= _N_MAXIMO and 0 < r <= _R_MAXIMO and 0 < p <= _P_MAXIMO):
            return False
        sal = base64.b64decode(sal_txt, validate=True)
        esperado = base64.b64decode(esperado_txt, validate=True)
        if not sal or not esperado:
            return False
        derivada = _derivar(senha, sal, n, r, p, len(esperado))
    except ValueError:  # inclui base64 inválido (binascii.Error) e parâmetros recusados
        return False
    return hmac.compare_digest(derivada, esperado)


@cache
def _hash_de_ninguem() -> str:
    return gerar_hash(secrets.token_urlsafe(24))


def gastar_tempo_de_uma_conferencia(senha: str) -> None:
    """Faz o trabalho de uma conferência sem conferir nada.

    Usado quando o usuário digitado não existe, para que a resposta demore o mesmo que a de
    uma senha errada (quem está de fora não descobre quais usuários existem pelo relógio).
    """
    conferir(senha, _hash_de_ninguem())


def senha_provisoria(digitos: int = 6) -> str:
    """Senha numérica sorteada, para a recuperação de acesso (o operador troca ao entrar)."""
    return "".join(secrets.choice("0123456789") for _ in range(digitos))

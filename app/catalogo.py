"""Catálogo de produtos: o que o cadastro e a entrada de nota têm em comum."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Produto


def proximo_codigo(sessao: Session) -> str:
    """O próximo código numérico livre: o maior código só de números, mais um."""
    numeros = [int(c) for (c,) in sessao.execute(select(Produto.codigo)) if c.isdigit()]
    return str(max(numeros, default=0) + 1)

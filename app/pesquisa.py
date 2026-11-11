"""Texto para pesquisa: sem acento e sem diferença entre maiúsculas e minúsculas.

No caixa ninguém digita acento: "agua" tem de achar "Água" e "joao" tem de achar "João". O
SQLite sozinho só ignora maiúsculas nas letras sem acento, então a função `sem_acento` é
registrada no banco (ver `app/db.py`) e usada nas buscas e na ordem alfabética das listas.
"""

from __future__ import annotations

import unicodedata


def sem_acento(texto: str | None) -> str:
    """Devolve o texto em minúsculas e sem acentos, cedilha ou til. Vazio vira ""."""
    if not texto:
        return ""
    decomposto = unicodedata.normalize("NFD", str(texto))
    return "".join(c for c in decomposto if unicodedata.category(c) != "Mn").casefold()

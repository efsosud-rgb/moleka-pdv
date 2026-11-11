"""CPF e CNPJ: limpar, conferir os dígitos verificadores e formatar.

O CNPJ aceita letras nas 12 primeiras posições (CNPJ alfanumérico, emitido pela Receita desde
julho de 2026). A conta dos dígitos é a mesma do CNPJ numérico; cada caractere vale o seu
código ASCII menos 48 (os algarismos continuam valendo o próprio número; "A" vale 17).
"""

from __future__ import annotations

import re

_PESOS_CNPJ_1 = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
_PESOS_CNPJ_2 = (6, *_PESOS_CNPJ_1)
_FORMATO_CNPJ = re.compile(r"[0-9A-Z]{12}[0-9]{2}")


def limpar(texto: str | None) -> str:
    """Tira pontos, traços, barras e espaços e passa as letras para maiúsculas."""
    return re.sub(r"[^0-9A-Za-z]", "", texto or "").upper()


def cpf_valido(cpf: str) -> bool:
    cpf = limpar(cpf)
    if len(cpf) != 11 or not cpf.isdigit() or cpf == cpf[0] * 11:
        return False
    for tamanho in (9, 10):
        soma = sum(int(cpf[i]) * (tamanho + 1 - i) for i in range(tamanho))
        digito = (soma * 10) % 11 % 10
        if digito != int(cpf[tamanho]):
            return False
    return True


def _digito_cnpj(base: str, pesos: tuple[int, ...]) -> int:
    soma = sum((ord(c) - 48) * peso for c, peso in zip(base, pesos, strict=True))
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def cnpj_valido(cnpj: str) -> bool:
    cnpj = limpar(cnpj)
    if not _FORMATO_CNPJ.fullmatch(cnpj) or cnpj == cnpj[0] * 14:
        return False
    primeiro = _digito_cnpj(cnpj[:12], _PESOS_CNPJ_1)
    segundo = _digito_cnpj(cnpj[:12] + str(primeiro), _PESOS_CNPJ_2)
    return cnpj[12:] == f"{primeiro}{segundo}"


def tipo(documento: str) -> str | None:
    """ "cpf", "cnpj" ou None quando não é nenhum dos dois (ou os dígitos não conferem)."""
    documento = limpar(documento)
    if len(documento) == 11 and cpf_valido(documento):
        return "cpf"
    if len(documento) == 14 and cnpj_valido(documento):
        return "cnpj"
    return None


def formatar(documento: str | None) -> str:
    """12345678909 -> 123.456.789-09; 12ABC34501DE35 -> 12.ABC.345/01DE-35."""
    d = limpar(documento)
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    return d

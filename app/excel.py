"""Planilhas do Excel (.xlsx) dos relatórios, montadas com o openpyxl.

Cada aba leva no alto o nome da loja, o título, o período e os filtros, e no pé, as notas e os
avisos que a tela mostra. Os valores entram como números de verdade (dá para somar e fazer
gráfico no Excel): dinheiro em reais com duas casas, quantidades, porcentagens e datas. Onde a
tela mostra "—", a planilha também mostra "—", e o motivo vai nas notas.

Os números vêm da mesma função que alimenta a tela (ver app/api/planilhas.py): a planilha não
refaz conta nenhuma, só troca centavos por reais.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.properties import PageSetupProperties
from openpyxl.worksheet.worksheet import Worksheet

TIPO_DO_ARQUIVO = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
TRACO = "—"

# Formatos do Excel. O separador de milhar e o de decimais aparecem como o Windows do usuário
# estiver configurado (no Brasil, 1.234,56).
_REAIS = '"R$" #,##0.00;[Red]-"R$" #,##0.00'
_INTEIRO = "#,##0"
_DECIMAL = "#,##0.000"
_PORCENTO = "0.0%"
_DATA = "dd/mm/yyyy"
_DATA_HORA = "dd/mm/yyyy hh:mm"
_TIPOS = frozenset({"texto", "dinheiro", "quantidade", "inteiro", "porcento", "data", "data_hora"})

_VINHO = "542424"
_FUNDO_DO_TITULO = PatternFill("solid", fgColor="F6E7C8")
_LINHA = Side(style="thin", color="B9A27A")
_PROIBIDO_NA_ABA = re.compile(r"[\[\]:*?/\\]")
_PROIBIDO_NO_NOME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclass(frozen=True)
class Coluna:
    titulo: str
    tipo: str = "texto"  # texto, dinheiro (centavos), quantidade, inteiro, porcento, data...
    largura: float = 14


@dataclass
class Aba:
    nome: str  # o nome da aba, no pé da planilha
    titulo: str
    colunas: list[Coluna]
    linhas: list[list[Any]]
    total: list[Any] | None = None
    detalhes: list[str] = field(default_factory=list)  # período, filtros
    notas: list[str] = field(default_factory=list)  # avisos e motivos, como na tela
    vazia: str = ""  # o que escrever quando não há linhas (ex.: "sem vendas no período")


@dataclass(frozen=True)
class Cabecalho:
    loja: str  # "" = dados da loja ainda não preenchidos
    cnpj: str
    operador: str
    versao: str
    agora: datetime  # horário da loja


def nome_da_aba(texto: str) -> str:
    """O Excel não aceita alguns caracteres nem mais de 31 letras no nome da aba."""
    return _PROIBIDO_NA_ABA.sub("-", texto).strip()[:31] or "Planilha"


def nome_do_arquivo(titulo: str, inicio: date | None = None, fim: date | None = None) -> str:
    """ "Moleka - Vendas 01-11-2026 a 30-11-2026.xlsx" (sem caracteres que o Windows recusa)."""
    partes = [f"Moleka - {titulo}"]
    if inicio is not None:
        partes.append(f"{inicio:%d-%m-%Y}")
        if fim is not None and fim != inicio:
            partes.append(f"a {fim:%d-%m-%Y}")
    nome = _PROIBIDO_NO_NOME.sub("-", " ".join(partes)).strip()
    return f"{nome}.xlsx"


def _valor(tipo: str, valor: Any) -> tuple[Any, str | None]:
    """(o que vai na célula, o formato) para um valor do tipo da coluna."""
    if valor is None:
        return TRACO, None
    if valor == "":
        return None, None  # não se aplica a esta linha: a célula fica vazia
    if isinstance(valor, str) and tipo != "texto":
        return valor, None  # um texto numa coluna de número ("—", "parcial")
    if tipo == "dinheiro":
        return Decimal(int(valor)) / 100, _REAIS
    if tipo == "inteiro":
        return int(valor), _INTEIRO
    if tipo == "quantidade":
        numero = Decimal(valor)
        return numero, _INTEIRO if numero == numero.to_integral_value() else _DECIMAL
    if tipo == "porcento":  # chega como 12.5 (por cento); vai como 0,125 com o formato de %
        return Decimal(valor) / 100, _PORCENTO
    if tipo == "data":
        return valor, _DATA
    if tipo == "data_hora":
        momento = valor.replace(tzinfo=None) if isinstance(valor, datetime) else valor
        return momento, _DATA_HORA
    return str(valor), None


def _escrever(planilha: Worksheet, linha: int, coluna: int, tipo: str, valor: Any) -> None:
    conteudo, formato = _valor(tipo, valor)
    celula = planilha.cell(row=linha, column=coluna, value=conteudo)
    if isinstance(conteudo, str) and conteudo.startswith("="):
        # Texto que começa com "=" viraria fórmula no Excel (o nome de um produto, por exemplo).
        celula.data_type = "s"
    if formato:
        celula.number_format = formato
    if conteudo == TRACO:
        celula.alignment = Alignment(horizontal="right" if tipo != "texto" else "left")


def _cabecalho(planilha: Worksheet, cab: Cabecalho, aba: Aba) -> int:
    """Escreve o alto da aba e devolve a linha onde a tabela começa."""
    loja = cab.loja or "Moleka PDV"
    if cab.cnpj:
        loja += f" · CNPJ {cab.cnpj}"
    planilha.cell(row=1, column=1, value=loja).font = Font(bold=True, color=_VINHO)
    planilha.cell(row=2, column=1, value=aba.titulo).font = Font(bold=True, size=14)
    linha = 3
    for detalhe in aba.detalhes:
        planilha.cell(row=linha, column=1, value=detalhe)
        linha += 1
    gerada = (
        f"Gerada em {cab.agora:%d/%m/%Y} às {cab.agora:%H:%M} por {cab.operador} · "
        f"Moleka PDV {cab.versao}"
    )
    planilha.cell(row=linha, column=1, value=gerada).font = Font(italic=True, color="6B5B4B")
    return linha + 2


def _preencher(planilha: Worksheet, cab: Cabecalho, aba: Aba) -> None:
    for coluna in aba.colunas:
        if coluna.tipo not in _TIPOS:
            raise ValueError(f"tipo de coluna desconhecido: {coluna.tipo}")
    topo = _cabecalho(planilha, cab, aba)
    for n, coluna in enumerate(aba.colunas, start=1):
        celula = planilha.cell(row=topo, column=n, value=coluna.titulo)
        celula.font = Font(bold=True, color=_VINHO)
        celula.fill = _FUNDO_DO_TITULO
        celula.border = Border(bottom=_LINHA)
        celula.alignment = Alignment(
            horizontal="left" if coluna.tipo in ("texto", "data", "data_hora") else "right",
            vertical="bottom",
            wrap_text=True,
        )
        planilha.column_dimensions[get_column_letter(n)].width = coluna.largura
    linha = topo + 1
    if not aba.linhas:
        planilha.cell(row=linha, column=1, value=aba.vazia or TRACO).font = Font(italic=True)
        linha += 1
    for valores in aba.linhas:
        for n, (coluna, valor) in enumerate(zip(aba.colunas, valores, strict=True), start=1):
            _escrever(planilha, linha, n, coluna.tipo, valor)
        linha += 1
    if aba.linhas:
        ultima = get_column_letter(len(aba.colunas))
        planilha.auto_filter.ref = f"A{topo}:{ultima}{linha - 1}"
    if aba.total is not None:
        for n, (coluna, valor) in enumerate(zip(aba.colunas, aba.total, strict=True), start=1):
            if valor == "":
                continue
            _escrever(planilha, linha, n, coluna.tipo, valor)
            total = planilha.cell(row=linha, column=n)
            total.font = Font(bold=True)
            total.border = Border(top=_LINHA)
        linha += 1
    linha += 1
    for nota in aba.notas:
        if nota:
            planilha.cell(row=linha, column=1, value=nota).font = Font(italic=True)
            linha += 1
    planilha.freeze_panes = f"A{topo + 1}"
    planilha.page_setup.orientation = "landscape" if len(aba.colunas) > 5 else "portrait"
    planilha.page_setup.fitToWidth = 1
    planilha.page_setup.fitToHeight = 0
    planilha.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    planilha.print_title_rows = f"{topo}:{topo}"


def montar(cabecalho: Cabecalho, abas: list[Aba]) -> bytes:
    """O arquivo .xlsx, pronto para salvar."""
    livro = Workbook()
    for vazia in list(livro.worksheets):  # o openpyxl já começa com uma aba em branco
        livro.remove(vazia)
    usados: set[str] = set()
    for aba in abas:
        nome = nome_da_aba(aba.nome)
        base, n = nome, 2
        while nome.casefold() in usados:
            sufixo = f" ({n})"
            nome = base[: 31 - len(sufixo)] + sufixo
            n += 1
        usados.add(nome.casefold())
        _preencher(livro.create_sheet(nome), cabecalho, aba)
    livro.properties.creator = f"Moleka PDV {cabecalho.versao}"
    livro.properties.title = abas[0].titulo if abas else "Moleka PDV"
    saida = io.BytesIO()
    livro.save(saida)
    return saida.getvalue()

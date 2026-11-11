"""Páginas da interface, montadas no servidor com Jinja2.

A moldura (menus, faixa do topo, menu lateral e barra de status) fica num só lugar
(`ui/templates/base.html`); cada tela só descreve o seu miolo. Os dados chegam depois,
pelo JavaScript, a partir da API (`/api/...`): a página em si não carrega número nenhum.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app import config

router = APIRouter(include_in_schema=False)
_templates: Jinja2Templates | None = None


@dataclass(frozen=True)
class Modulo:
    """Um módulo do sistema, como aparece no menu lateral e na tela inicial."""

    id: str
    rotulo: str
    descricao: str
    icone: str
    cor: str  # cor do selo na tela inicial: vermelho, amarelo, verde ou vinho
    url: str | None = None  # None = ainda não construído ("em breve")
    atalho: str | None = None
    no_menu_lateral: bool = True


MODULOS: tuple[Modulo, ...] = (
    Modulo(
        "caixa", "Caixa (PDV)", "Venda rápida e cupom NFC-e", "caixa", "vermelho", "/caixa", "F2"
    ),
    Modulo(
        "controle-caixa",
        "Controle de Caixa",
        "Abertura, sangria, suprimento e fechamento",
        "relogio",
        "amarelo",
    ),
    Modulo(
        "produtos",
        "Produtos",
        "Cadastro, código de barras e preços",
        "etiqueta",
        "verde",
        "/produtos",
        "F5",
    ),
    Modulo("estoque", "Estoque", "Saldos, ajustes e inventário", "caixas", "vinho"),
    Modulo(
        "entrada-nf",
        "Entrada de NF (XML)",
        "Importa a compra e atualiza estoque e custo",
        "xml",
        "vermelho",
    ),
    Modulo("clientes", "Clientes", "Cadastro, CPF na nota e histórico", "pessoas", "amarelo"),
    Modulo(
        "tabelas-preco",
        "Tabelas de Preço",
        "Varejo, atacado e preço por quantidade",
        "lista",
        "verde",
    ),
    Modulo(
        "financeiro",
        "Financeiro",
        "Despesas, receitas e fluxo de caixa",
        "carteira",
        "vinho",
        "/financeiro",
    ),
    Modulo(
        "dre",
        "DRE e Rentabilidade",
        "Resultado do período e margem por produto",
        "grafico",
        "vermelho",
        "/financeiro",
        no_menu_lateral=False,
    ),
    Modulo(
        "fiscal", "Fiscal / NFC-e", "Emissão, contingência e certificado A1", "recibo", "amarelo"
    ),
)


@dataclass(frozen=True)
class ItemMenu:
    """Uma linha de um menu do topo. Sem `url` nem `acao`, aparece como "em breve"."""

    rotulo: str
    url: str | None = None
    acao: str | None = None  # tratada em moleka.js: "sair", "tela-cheia" ou "sobre"
    atalho: str | None = None


MENUS: tuple[tuple[str, tuple[ItemMenu, ...]], ...] = (
    (
        "Arquivo",
        (
            ItemMenu("Início", url="/inicio"),
            ItemMenu("Capa do sistema", url="/"),
            ItemMenu("Tela cheia", acao="tela-cheia"),
            ItemMenu("Sair", acao="sair", atalho="Alt+F4"),
        ),
    ),
    (
        "Cadastros",
        (
            ItemMenu("Produtos", url="/produtos", atalho="F5"),
            ItemMenu("Clientes"),
            ItemMenu("Tabelas de preço"),
            ItemMenu("Operadores"),
        ),
    ),
    ("Caixa", (ItemMenu("Venda (PDV)", url="/caixa", atalho="F2"), ItemMenu("Controle de caixa"))),
    ("Estoque", (ItemMenu("Saldos e ajustes"), ItemMenu("Entrada de NF (XML)"))),
    ("Financeiro", (ItemMenu("DRE e fluxo de caixa", url="/financeiro"), ItemMenu("Lançamentos"))),
    ("Fiscal", (ItemMenu("NFC-e emitidas"), ItemMenu("Certificado A1"))),
    ("Relatórios", (ItemMenu("Vendas por período"), ItemMenu("Rentabilidade por produto"))),
    ("Ajuda", (ItemMenu("Sobre o Moleka PDV", acao="sobre"),)),
)

# Ícones de traço (24x24). O conteúdo vai dentro de <svg class="ic" viewBox="0 0 24 24">.
ICONES: dict[str, str] = {
    "casa": '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/><path d="M9.5 21v-6h5v6"/>',
    "caixa": (
        '<rect x="3" y="11" width="18" height="10" rx="2"/><path d="M7 11V5h10v6"/>'
        '<path d="M9.5 8h5"/><path d="M7 15h2M11 15h2M15 15h2M8 18h8"/>'
    ),
    "relogio": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "etiqueta": '<path d="M3 12V4h8l10 10-8 8z"/><circle cx="7.5" cy="8.5" r="1.5"/>',
    "caixas": (
        '<rect x="3.5" y="12" width="8" height="8.5"/>'
        '<rect x="12.5" y="12" width="8" height="8.5"/>'
        '<rect x="8" y="3.5" width="8" height="8.5"/>'
    ),
    "xml": (
        '<path d="M14 3H6v18h12V7z"/><path d="M14 3v4h4"/>'
        '<path d="m10 12-2 2.5 2 2.5M14 12l2 2.5-2 2.5"/>'
    ),
    "pessoas": (
        '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.6-3.6 3.2-5.5 6.5-5.5s5.9 1.9 6.5 5.5"/>'
        '<path d="M16 4.8a3.5 3.5 0 0 1 0 6.4M18.5 14.8c1.7.8 2.7 2.5 3 5.2"/>'
    ),
    "lista": '<path d="M4 6h16M4 12h9M4 18h6"/><circle cx="17.5" cy="16.5" r="3.5"/>',
    "carteira": (
        '<rect x="3" y="6.5" width="18" height="13.5" rx="2"/><path d="M3 11h18"/>'
        '<path d="M15.5 15.5h2"/>'
    ),
    "grafico": '<path d="M4 4v16h16"/><path d="m7.5 15 4-4 3 3 5-6"/>',
    "recibo": '<path d="M6 3h12v18l-3-2-3 2-3-2-3 2z"/><path d="M9 8h6M9 12h6M9 16h3"/>',
    "engrenagem": (
        '<circle cx="12" cy="12" r="3"/><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3'
        'M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M5.3 18.7l2.1-2.1M16.6 7.4l2.1-2.1"/>'
    ),
    "barras": '<path d="M4 5v14M7.5 5v14M10 5v14M13.5 5v14M16 5v14M20 5v14"/>',
    "busca": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    "mais": '<path d="M12 5v14M5 12h14"/>',
    "dinheiro": (
        '<rect x="2.5" y="6" width="19" height="12" rx="2"/><circle cx="12" cy="12" r="2.5"/>'
        '<path d="M6 10v4M18 10v4"/>'
    ),
    "pix": '<path d="M12 3l9 9-9 9-9-9z"/><path d="M8.5 12 12 8.5l3.5 3.5-3.5 3.5z"/>',
    "cartao": (
        '<rect x="2.5" y="5" width="19" height="14" rx="2"/><path d="M2.5 10h19"/>'
        '<path d="M6 15h4"/>'
    ),
    "x": '<path d="M6 6l12 12M18 6 6 18"/>',
    "salvar": '<path d="M5 3h11l3 3v15H5z"/><path d="M8 3v5h7V3"/><path d="M8 21v-7h8v7"/>',
    "lixeira": '<path d="M4 7h16M9 7V4h6v3M6 7l1 14h10l1-14"/>',
    "atualizar": '<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 5v6h-6"/>',
    "baixar": '<path d="M12 3v12M7 10l5 5 5-5"/><path d="M4 21h16"/>',
    "alerta": '<path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17h.01"/>',
    "seta": '<path d="m6 9 6 6 6-6"/>',
    "obra": '<path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17h.01"/>',
}


def templates() -> Jinja2Templates:
    global _templates
    if _templates is None:
        _templates = Jinja2Templates(directory=config.pasta_ui() / "templates")
        _templates.env.globals.update(
            app_nome=config.APP_NOME,
            versao=config.VERSAO,
            modulos=MODULOS,
            menus=MENUS,
            icones=ICONES,
        )
    return _templates


def _pagina(request: Request, nome: str, tela: str) -> HTMLResponse:
    return templates().TemplateResponse(request, nome, {"tela": tela})


@router.get("/", response_class=HTMLResponse)
def capa(request: Request) -> HTMLResponse:
    return _pagina(request, "capa.html", "capa")


@router.get("/inicio", response_class=HTMLResponse)
def inicio(request: Request) -> HTMLResponse:
    return _pagina(request, "inicio.html", "inicio")


@router.get("/caixa", response_class=HTMLResponse)
def caixa(request: Request) -> HTMLResponse:
    return _pagina(request, "caixa.html", "caixa")


@router.get("/produtos", response_class=HTMLResponse)
def produtos(request: Request) -> HTMLResponse:
    return _pagina(request, "produtos.html", "produtos")


@router.get("/financeiro", response_class=HTMLResponse)
def financeiro(request: Request) -> HTMLResponse:
    return _pagina(request, "financeiro.html", "financeiro")

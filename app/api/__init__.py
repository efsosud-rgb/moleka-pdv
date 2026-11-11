"""Aplicação FastAPI: API local (/api/...), páginas da interface e arquivos estáticos."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from app import acesso, config
from app.api.cadastros import router as cadastros_router
from app.api.caixa import router as caixa_router
from app.api.estoque import router as estoque_router
from app.api.login import router as login_router
from app.api.status import router as status_router
from app.api.vendas import router as vendas_router
from app.operadores import RegraError
from app.web import router as paginas_router

# O servidor só atende a janela do próprio programa, neste computador.
ENDERECOS_LOCAIS = frozenset({"127.0.0.1", "localhost"})
_METODOS_QUE_SO_LEEM = frozenset({"GET", "HEAD", "OPTIONS"})


def _nome_do_host(valor: str) -> str:
    # "127.0.0.1:8765" vira "127.0.0.1": o número da porta não importa.
    return valor.rsplit(":", 1)[0].strip().lower() if valor else ""


def criar_app() -> FastAPI:
    app = FastAPI(
        title=config.APP_NOME, version=config.VERSAO, docs_url="/api/docs", redoc_url=None
    )
    app.state.sessoes = acesso.Sessoes()
    app.state.tentativas = acesso.Tentativas()

    @app.middleware("http")
    async def so_deste_computador(
        request: Request, seguir: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Recusa pedidos que não vieram da janela do programa.

        Um site aberto no navegador deste PC consegue mandar pedidos para 127.0.0.1. Dois
        cuidados: o endereço pedido tem de ser o local (um domínio de fora apontado para
        127.0.0.1 é recusado) e pedidos que alteram dados não podem ter origem em outro site.
        """
        if _nome_do_host(request.headers.get("host", "")) not in ENDERECOS_LOCAIS:
            return PlainTextResponse("Endereço não permitido.", status_code=400)
        if request.method not in _METODOS_QUE_SO_LEEM:
            origem = request.headers.get("origin")
            if origem is not None and urlsplit(origem).hostname not in ENDERECOS_LOCAIS:
                return JSONResponse({"detail": "Pedido de outra origem recusado."}, 403)
        return await seguir(request)

    @app.exception_handler(RegraError)
    async def regra_violada(_request: Request, erro: RegraError) -> JSONResponse:
        return JSONResponse({"detail": str(erro)}, status_code=erro.status)

    app.include_router(status_router, prefix="/api")
    app.include_router(login_router, prefix="/api")
    # Cadastros só para quem entrou no sistema; o que é só do gerente está marcado em cada rota.
    so_logado = [Depends(acesso.exigir_operador)]
    app.include_router(cadastros_router, prefix="/api", dependencies=so_logado)
    app.include_router(caixa_router, prefix="/api", dependencies=so_logado)
    app.include_router(vendas_router, prefix="/api", dependencies=so_logado)
    # Estoque: só o gerente (a exigência está no próprio módulo).
    app.include_router(estoque_router, prefix="/api")
    app.include_router(paginas_router)

    # Marca (logo, mascote, artes da capa) e arquivos da interface (CSS, JS, fontes).
    app.mount("/assets", StaticFiles(directory=config.pasta_assets()), name="assets")
    app.mount("/static", StaticFiles(directory=config.pasta_ui() / "static"), name="static")
    return app

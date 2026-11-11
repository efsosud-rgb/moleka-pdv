"""Aplicação FastAPI: API local (/api/...), páginas da interface e arquivos estáticos."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import config
from app.api.cadastros import router as cadastros_router
from app.api.status import router as status_router
from app.web import router as paginas_router


def criar_app() -> FastAPI:
    app = FastAPI(
        title=config.APP_NOME, version=config.VERSAO, docs_url="/api/docs", redoc_url=None
    )
    app.include_router(status_router, prefix="/api")
    app.include_router(cadastros_router, prefix="/api")
    app.include_router(paginas_router)

    # Marca (logo, mascote, artes da capa) e arquivos da interface (CSS, JS, fontes).
    app.mount("/assets", StaticFiles(directory=config.pasta_assets()), name="assets")
    app.mount("/static", StaticFiles(directory=config.pasta_ui() / "static"), name="static")
    return app

"""Aplicação FastAPI: API local (/api/...) + interface (/) + marca (/assets/...)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import config
from app.api.cadastros import router as cadastros_router
from app.api.status import router as status_router


def criar_app() -> FastAPI:
    app = FastAPI(
        title=config.APP_NOME, version=config.VERSAO, docs_url="/api/docs", redoc_url=None
    )
    app.include_router(status_router, prefix="/api")
    app.include_router(cadastros_router, prefix="/api")

    # Marca (logo, mascote) e interface. A interface é servida por último, na raiz.
    app.mount("/assets", StaticFiles(directory=config.pasta_assets()), name="assets")
    app.mount("/", StaticFiles(directory=config.pasta_ui(), html=True), name="ui")
    return app

"""Ponto de entrada do Moleka PDV.

Sobe o servidor local (só em 127.0.0.1) numa thread e abre a janela do sistema com pywebview.
Uso:
    python main.py              # abre a janela (precisa de WebView2 no Windows)
    python main.py --sem-janela # só o servidor, para desenvolvimento/testes (abra no navegador)
"""

from __future__ import annotations

import argparse
import socket
import sys
import threading
import time

import uvicorn

from app import config, db
from app.api import criar_app


def _porta_livre(porta: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", porta)) != 0


def _esperar_servidor(porta: int, segundos: float = 10) -> bool:
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if not _porta_livre(porta):
            return True
        time.sleep(0.1)
    return False


def iniciar_servidor(porta: int) -> uvicorn.Server:
    db.criar_schema()
    servidor = uvicorn.Server(
        uvicorn.Config(criar_app(), host="127.0.0.1", port=porta, log_level="warning")
    )
    threading.Thread(target=servidor.run, name="servidor-local", daemon=True).start()
    if not _esperar_servidor(porta):
        raise RuntimeError(f"o servidor local não subiu na porta {porta}")
    return servidor


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=config.APP_NOME)
    parser.add_argument("--sem-janela", action="store_true", help="só o servidor local")
    parser.add_argument("--porta", type=int, default=config.porta())
    parser.add_argument("--janela", action="store_true", help="janela normal em vez de tela cheia")
    args = parser.parse_args(argv)

    porta = args.porta
    if not _porta_livre(porta):
        print(f"A porta {porta} já está em uso (o sistema já está aberto?).", file=sys.stderr)
        return 2

    servidor = iniciar_servidor(porta)
    url = f"http://127.0.0.1:{porta}/"
    print(f"{config.APP_NOME} {config.VERSAO} — {url} — dados em {config.pasta_dados()}")

    if args.sem_janela:
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    else:
        import webview  # importado aqui: só é necessário com janela

        webview.create_window(
            config.APP_NOME,
            url,
            fullscreen=not args.janela,
            width=1366,
            height=768,
            min_size=(1024, 700),
            text_select=False,
        )
        webview.start()

    servidor.should_exit = True
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Ponto de entrada do Moleka PDV.

Sobe o servidor local (só em 127.0.0.1) numa thread e abre a janela do sistema com pywebview.
Uso:
    python main.py               # abre a janela maximizada (precisa do WebView2 no Windows)
    python main.py --tela-cheia  # tela cheia, sem barra de título (modo caixa)
    python main.py --janela      # janela de 1366x768, para desenvolvimento
    python main.py --sem-janela  # só o servidor, para desenvolvimento/testes (abra no navegador)
    python main.py --redefinir-senha [USUARIO]  # recuperação de acesso: gera uma senha provisória
"""

from __future__ import annotations

import argparse
import logging
import os
import socket
import sys
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

import uvicorn

from app import config, db, operadores
from app.api import criar_app

log = logging.getLogger("moleka")

# Identificador do WebView2 Runtime no registro do Windows (documentação da Microsoft).
_WEBVIEW2_CHAVE = r"Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"


def configurar_logs() -> Path:
    """Grava o log em <dados>/logs/moleka.log e devolve o caminho do arquivo."""
    arquivo = config.pasta_dados() / "logs" / "moleka.log"
    handler = RotatingFileHandler(arquivo, maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    raiz = logging.getLogger()
    raiz.setLevel(logging.INFO)
    raiz.addHandler(handler)
    # Empacotado sem console, stdout e stderr não existem; quem escreve neles quebraria.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    return arquivo


def avisar(titulo: str, texto: str, *, com_janela: bool) -> None:
    """Mostra um erro ao usuário: caixa de mensagem no Windows com janela, stderr nos demais."""
    log.error("%s: %s", titulo, texto)
    if com_janela and os.name == "nt":
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, texto, titulo, 0x10)  # 0x10 = ícone de erro
    else:
        print(f"{titulo}: {texto}", file=sys.stderr)


def informar(titulo: str, texto: str) -> None:
    """Mostra um recado que não é erro: caixa de mensagem no Windows, terminal nos demais."""
    if os.name == "nt":
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, texto, titulo, 0x40)  # 0x40 = ícone de informação
    else:
        print(f"{titulo}: {texto}")


def redefinir_senha(usuario: str) -> int:
    """Recuperação de acesso: sorteia uma senha provisória para um operador e mostra na tela.

    Não precisa do sistema aberto nem de login: quem usa este computador já tem acesso ao
    arquivo do banco. Por isso cada uso fica registrado no log (sem a senha).
    """
    db.criar_schema()
    try:
        with db.nova_sessao() as sessao:
            operador, provisoria = operadores.redefinir_senha(sessao, usuario or None)
    except operadores.RegraError as erro:
        avisar(f"{config.APP_NOME} — recuperação de acesso", str(erro), com_janela=True)
        return 4
    informar(
        f"{config.APP_NOME} — recuperação de acesso",
        f"Senha provisória de {operador.nome} (usuário {operador.login}):\n\n"
        f"        {provisoria}\n\n"
        "Anote agora: ela não aparece de novo. Abra o sistema, entre com ela e troque em "
        "Arquivo → Minha senha.",
    )
    return 0


def webview2_instalado() -> bool:
    """Diz se o WebView2 Runtime está instalado (só faz sentido no Windows)."""
    import winreg

    locais = (
        (winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\WOW6432Node\\" + _WEBVIEW2_CHAVE),
        (winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\" + _WEBVIEW2_CHAVE),
        (winreg.HKEY_CURRENT_USER, "Software\\" + _WEBVIEW2_CHAVE),
    )
    for raiz, caminho in locais:
        try:
            with winreg.OpenKey(raiz, caminho) as chave:
                versao, _ = winreg.QueryValueEx(chave, "pv")
        except OSError:
            continue
        if versao and versao != "0.0.0.0":
            return True
    return False


def marcar_aberto() -> None:
    """Cria um mutex de nome fixo; o instalador usa para saber se o sistema está aberto."""
    if os.name == "nt":
        import ctypes

        ctypes.windll.kernel32.CreateMutexW(None, False, "MolekaPDV_Aberto")


def _porta_livre(porta: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", porta)) != 0


def _esperar_servidor(porta: int, segundos: float = 15) -> bool:
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if not _porta_livre(porta):
            return True
        time.sleep(0.1)
    return False


def iniciar_servidor(porta: int) -> uvicorn.Server:
    db.criar_schema()
    servidor = uvicorn.Server(
        uvicorn.Config(
            criar_app(), host="127.0.0.1", port=porta, log_level="warning", log_config=None
        )
    )
    threading.Thread(target=servidor.run, name="servidor-local", daemon=True).start()
    if not _esperar_servidor(porta):
        raise RuntimeError(f"o servidor local não subiu na porta {porta}")
    return servidor


class Ponte:
    """Funções da janela que a interface pode chamar por `window.pywebview.api`.

    A janela fica num atributo com sublinhado: o pywebview expõe os atributos públicos
    para o JavaScript, e a janela não deve ir junto.
    """

    def __init__(self) -> None:
        self._janela = None

    def sair(self) -> None:
        if self._janela is not None:
            self._janela.destroy()

    def tela_cheia(self) -> None:
        if self._janela is not None:
            self._janela.toggle_fullscreen()


def abrir_janela(url: str, *, tela_cheia: bool, janela_pequena: bool) -> None:
    import webview  # importado aqui: só é necessário com janela

    ponte = Ponte()
    janela = webview.create_window(
        config.APP_NOME,
        url,
        js_api=ponte,
        fullscreen=tela_cheia,
        maximized=not tela_cheia and not janela_pequena,
        width=1366,
        height=768,
        min_size=(1024, 700),
        text_select=False,
    )
    ponte._janela = janela
    webview.start(
        gui="edgechromium" if os.name == "nt" else None,
        storage_path=str(config.pasta_dados() / "webview"),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=config.APP_NOME)
    parser.add_argument("--sem-janela", action="store_true", help="só o servidor local")
    parser.add_argument("--porta", type=int, default=config.porta())
    parser.add_argument("--tela-cheia", action="store_true", help="tela cheia (modo caixa)")
    parser.add_argument("--janela", action="store_true", help="janela de 1366x768")
    parser.add_argument(
        "--redefinir-senha",
        nargs="?",
        const="",
        default=None,
        metavar="USUARIO",
        help="recuperação de acesso: gera uma senha provisória (sem USUARIO, a do gerente)",
    )
    args = parser.parse_args(argv)
    com_janela = not args.sem_janela

    arquivo_log = configurar_logs()
    if args.redefinir_senha is not None:
        try:
            return redefinir_senha(args.redefinir_senha)
        except Exception as erro:  # sem terminal no programa empacotado: o motivo vai para a tela
            log.exception("falha na recuperação de acesso")
            avisar(
                config.APP_NOME,
                f"Não foi possível redefinir a senha.\n\n{erro}\n\nDetalhes em:\n{arquivo_log}",
                com_janela=True,
            )
            return 1
    log.info("%s %s iniciando; dados em %s", config.APP_NOME, config.VERSAO, config.pasta_dados())

    porta = args.porta
    if not _porta_livre(porta):
        avisar(
            config.APP_NOME,
            f"O {config.APP_NOME} já está aberto neste computador (porta {porta} em uso).",
            com_janela=com_janela,
        )
        return 2

    if com_janela and os.name == "nt" and not webview2_instalado():
        avisar(
            config.APP_NOME,
            "Falta o componente WebView2 da Microsoft, que desenha as telas do sistema.\n\n"
            "Instale o 'WebView2 Runtime' (gratuito, no site da Microsoft) ou rode de novo "
            "o instalador do Moleka PDV com internet, e abra o sistema outra vez.",
            com_janela=True,
        )
        return 3

    try:
        servidor = iniciar_servidor(porta)
    except Exception as erro:  # qualquer falha na partida precisa chegar ao usuário
        log.exception("falha ao iniciar o servidor local")
        avisar(
            config.APP_NOME,
            f"O sistema não conseguiu iniciar.\n\n{erro}\n\nDetalhes em:\n{arquivo_log}",
            com_janela=com_janela,
        )
        return 1

    marcar_aberto()
    url = f"http://127.0.0.1:{porta}/"
    print(f"{config.APP_NOME} {config.VERSAO} — {url} — dados em {config.pasta_dados()}")
    log.info("servidor local em %s", url)

    codigo = 0
    if args.sem_janela:
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    else:
        try:
            abrir_janela(url, tela_cheia=args.tela_cheia, janela_pequena=args.janela)
        except Exception as erro:  # idem: o usuário precisa ver o motivo
            log.exception("falha ao abrir a janela")
            avisar(
                config.APP_NOME,
                f"A janela do sistema não abriu.\n\n{erro}\n\nDetalhes em:\n{arquivo_log}",
                com_janela=True,
            )
            codigo = 1

    servidor.should_exit = True
    log.info("encerrado (código %s)", codigo)
    return codigo


if __name__ == "__main__":
    raise SystemExit(main())

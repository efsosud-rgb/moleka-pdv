"""Abre o Moleka PDV direto do código, sem instalador (para testes no Windows).

Para que serve: o instalador ainda não tem assinatura digital, e o Windows 11 com o Controle
Inteligente de Aplicativos ligado recusa instalá-lo (erro 4551). Rodando pelo código, quem
executa é o Python, que é assinado, e o instalador não entra na história.

Uso, no PowerShell, com o Python 3.12 ou mais novo instalado:

    py tools\\abrir_pelo_codigo.py                # prepara o ambiente e abre o sistema
    py tools\\abrir_pelo_codigo.py --navegador    # abre no navegador, sem a janela própria
    py tools\\abrir_pelo_codigo.py --so-preparar  # só prepara e confere, não abre

O que faz, nesta ordem:
1. cria um ambiente do Python só do Moleka (pasta "venv", ao lado da pasta do código);
2. instala as bibliotecas listadas no pyproject.toml;
3. confere se o Windows deixa o Python carregar essas bibliotecas;
4. abre o sistema na janela própria; se a janela não puder abrir, abre no navegador.

Não altera nenhuma configuração do Windows. Os dados do sistema ficam na mesma pasta que o
programa instalado usaria (%APPDATA%\\MolekaPDV).
"""

from __future__ import annotations

import argparse
import os
import re
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PORTA = 8765
# Biblioteca da janela própria. Se ela não instalar ou não carregar, o sistema abre no navegador.
BIBLIOTECA_DA_JANELA = "pywebview"
MODULOS_ESSENCIAIS = ("pydantic_core", "pydantic", "sqlalchemy", "fastapi", "uvicorn", "jinja2")
SINAIS_DE_BLOQUEIO = ("Controle de Aplicativo", "Application Control", "4551")

resumo: list[str] = []


def dizer(texto: str = "") -> None:
    print(texto, flush=True)


def anotar(texto: str) -> None:
    """Mostra na tela e guarda para o resumo final."""
    resumo.append(texto)
    dizer(texto)


def dependencias() -> tuple[list[str], list[str]]:
    """Lê o pyproject.toml e devolve (essenciais, da janela).

    Os extras entre colchetes saem (ex.: "uvicorn[standard]" vira "uvicorn"): são aceleradores
    opcionais, e cada biblioteca compilada a mais é um arquivo a mais para o Windows conferir.
    """
    import tomllib  # só existe do Python 3.11 em diante; a versão é conferida antes, em main()

    with open(RAIZ / "pyproject.toml", "rb") as arquivo:
        lista = tomllib.load(arquivo)["project"]["dependencies"]
    limpas = [re.sub(r"\[[^\]]*\]", "", item).strip() for item in lista]
    da_janela = [d for d in limpas if d.lower().startswith(BIBLIOTECA_DA_JANELA)]
    essenciais = [d for d in limpas if d not in da_janela]
    return essenciais, da_janela


def python_do_ambiente(venv: Path) -> Path:
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def rodar(comando: list[str], pasta: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Roda um comando montado aqui (nada vem de fora) e devolve a saída como texto."""
    return subprocess.run(
        comando, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=pasta
    )


def fim_do_texto(texto: str, linhas: int = 6) -> str:
    return "\n".join(texto.strip().splitlines()[-linhas:])


def parece_bloqueio(texto: str) -> bool:
    return any(sinal in texto for sinal in SINAIS_DE_BLOQUEIO)


def criar_ambiente(venv: Path) -> Path | None:
    python = python_do_ambiente(venv)
    if python.exists():
        anotar(f"[1/4] Ambiente do Python: já existia em {venv}")
        return python
    dizer(f"[1/4] Criando o ambiente do Python em {venv} ...")
    feito = rodar([sys.executable, "-m", "venv", str(venv)])
    if feito.returncode != 0 or not python.exists():
        anotar("[1/4] FALHOU ao criar o ambiente do Python:")
        anotar(fim_do_texto(feito.stderr or feito.stdout))
        return None
    anotar(f"[1/4] Ambiente do Python criado em {venv}")
    return python


def instalar(python: Path, pacotes: list[str]) -> tuple[bool, str]:
    """Instala com o pip, mostrando o andamento na tela. Devolve (deu certo, fim da saída)."""
    comando = [str(python), "-m", "pip", "install", "--disable-pip-version-check", *pacotes]
    processo = subprocess.Popen(
        comando,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    saida: list[str] = []
    assert processo.stdout is not None
    for linha in processo.stdout:
        saida.append(linha.rstrip())
        if linha.startswith(("Collecting", "Downloading", "Installing", "Successfully")):
            dizer("      " + linha.strip()[:110])
    processo.wait()
    return processo.returncode == 0, "\n".join(saida[-8:])


def instalar_bibliotecas(python: Path, venv: Path) -> tuple[bool, bool]:
    """Devolve (essenciais instaladas, biblioteca da janela instalada)."""
    essenciais, da_janela = dependencias()
    marca = venv / "moleka-bibliotecas.txt"
    pedido = "\n".join([sys.version.split()[0], *essenciais, *da_janela])
    if marca.exists() and marca.read_text(encoding="utf-8") == pedido:
        anotar("[2/4] Bibliotecas: já estavam instaladas")
        return True, True

    dizer("[2/4] Instalando as bibliotecas (precisa de internet; leva de 1 a 3 minutos) ...")
    certo, fim = instalar(python, essenciais)
    if not certo:
        anotar("[2/4] FALHOU ao instalar as bibliotecas essenciais:")
        anotar(fim)
        return False, False
    janela_ok = True
    if da_janela:
        janela_ok, fim = instalar(python, da_janela)
        if not janela_ok:
            anotar(
                "[2/4] A biblioteca da janela própria não instalou; o sistema abrirá no navegador."
            )
            anotar(fim)
    if janela_ok:
        marca.write_text(pedido, encoding="utf-8")
    anotar("[2/4] Bibliotecas instaladas")
    return True, janela_ok


def conferir_essenciais(python: Path) -> bool:
    """O Windows deixa o Python carregar as bibliotecas? (É aqui que um bloqueio aparece.)"""
    dizer("[3/4] Conferindo se o Windows deixa carregar as bibliotecas ...")
    for modulo in MODULOS_ESSENCIAIS:
        feito = rodar([str(python), "-c", f"import {modulo}"])
        if feito.returncode != 0:
            erro = fim_do_texto(feito.stderr, 3)
            if parece_bloqueio(feito.stderr):
                anotar(
                    f"[3/4] BLOQUEADO PELO WINDOWS: a biblioteca {modulo} não pôde ser carregada."
                )
                anotar("      Com o Controle Inteligente ligado, este caminho não serve.")
            else:
                anotar(f"[3/4] FALHOU ao carregar a biblioteca {modulo}:")
            anotar(erro)
            return False
    anotar("[3/4] Bibliotecas essenciais carregam normalmente")
    return True


def janela_disponivel(python: Path) -> bool:
    """Testa, sem abrir nada, se a janela própria (WebView2) pode ser usada. Só no Windows."""
    if os.name != "nt":
        return True
    # Este módulo carrega o .NET e as bibliotecas do WebView2, sem criar janela nenhuma.
    teste = "import webview.platforms.winforms"
    feito = rodar([str(python), "-c", teste], pasta=RAIZ)
    if feito.returncode == 0:
        anotar("      Janela própria: disponível")
        return True
    motivo = "bloqueada pelo Windows" if parece_bloqueio(feito.stderr) else "não carregou"
    anotar(f"      Janela própria: {motivo}; o sistema abrirá no navegador.")
    anotar(fim_do_texto(feito.stderr, 3))
    return False


def porta_ocupada() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", PORTA)) == 0


def abrir_na_janela(python: Path) -> int:
    dizer("[4/4] Abrindo o sistema na janela própria ...")
    dizer("      Esta janela do PowerShell precisa ficar aberta enquanto o sistema estiver em uso.")
    return subprocess.call([str(python), "main.py"], cwd=RAIZ)


def abrir_no_navegador(python: Path, *, abrir: bool = True) -> int:
    endereco = f"http://127.0.0.1:{PORTA}/"
    dizer(f"[4/4] Abrindo o sistema no navegador ({endereco}) ...")
    servidor = subprocess.Popen(
        [str(python), "main.py", "--sem-janela", "--porta", str(PORTA)], cwd=RAIZ
    )
    limite = time.monotonic() + 40
    while time.monotonic() < limite and servidor.poll() is None and not porta_ocupada():
        time.sleep(0.3)
    if servidor.poll() is not None:
        anotar(f"[4/4] FALHOU: o sistema fechou ao iniciar (código {servidor.returncode}).")
        return servidor.returncode or 1
    if not porta_ocupada():
        servidor.terminate()
        anotar("[4/4] FALHOU: o sistema não respondeu em 40 segundos.")
        return 1
    anotar(f"[4/4] Sistema no ar em {endereco} (aberto no navegador)")
    if abrir:
        webbrowser.open(endereco)
    dizer()
    dizer("      O sistema fica no ar enquanto esta janela do PowerShell estiver aberta.")
    dizer("      Para encerrar: clique nesta janela e aperte Ctrl+C (ou feche a janela).")
    try:
        return servidor.wait()
    except KeyboardInterrupt:
        servidor.terminate()
        dizer("      Sistema encerrado.")
        return 0


def copiar_para_a_area_de_transferencia(texto: str) -> bool:
    if os.name != "nt":
        return False
    try:
        subprocess.run(["clip"], input=texto.encode("utf-16"), check=True)
    except (OSError, subprocess.CalledProcessError):
        return False
    return True


def mostrar_resumo(titulo: str) -> None:
    texto = "\n".join([f"=== RESUMO MOLEKA: {titulo} ===", *resumo, "=== FIM ==="])
    dizer()
    dizer(texto)
    if copiar_para_a_area_de_transferencia(texto):
        dizer("(resumo copiado: é só colar na conversa com Ctrl+V)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Abre o Moleka PDV direto do código.")
    # Código baixado em zip: o ambiente fica ao lado, e serve para as próximas versões.
    # Código clonado com o git: fica dentro, em ".venv" (já ignorado pelo .gitignore).
    padrao = RAIZ / ".venv" if (RAIZ / ".git").exists() else RAIZ.parent / "venv"
    parser.add_argument("--venv", type=Path, default=padrao, help="pasta do ambiente do Python")
    parser.add_argument("--navegador", action="store_true", help="abre no navegador")
    parser.add_argument("--so-preparar", action="store_true", help="prepara e confere, sem abrir")
    args = parser.parse_args(argv)

    anotar(f"Python {sys.version.split()[0]} em {sys.executable}")
    anotar(f"Código em {RAIZ}")
    # Quem roda este arquivo é o Python do computador, que pode ser mais antigo que o do projeto.
    if sys.version_info < (3, 12):  # noqa: UP036
        anotar("FALTA o Python 3.12 ou mais novo (este é mais antigo).")
        mostrar_resumo("não preparado")
        return 2

    python = criar_ambiente(args.venv)
    if python is None:
        mostrar_resumo("não preparado")
        return 2
    essenciais_ok, janela_instalada = instalar_bibliotecas(python, args.venv)
    if not essenciais_ok:
        mostrar_resumo("não preparado")
        return 2
    if not conferir_essenciais(python):
        mostrar_resumo("bloqueado ou com falha")
        return 3
    usar_janela = not args.navegador and janela_instalada and janela_disponivel(python)

    if args.so_preparar:
        anotar("Preparado. Não abri o sistema (pedido: só preparar).")
        mostrar_resumo("preparado")
        return 0
    if porta_ocupada():
        anotar(
            f"O Moleka PDV já está aberto neste computador (porta {PORTA} em uso). Feche-o antes."
        )
        mostrar_resumo("já estava aberto")
        return 2

    if usar_janela:
        mostrar_resumo("preparado; abrindo na janela própria")
        codigo = abrir_na_janela(python)
        if codigo == 0:
            dizer("      Sistema fechado normalmente.")
            return 0
        resumo.clear()
        anotar(f"A janela própria fechou com o código {codigo}; abrindo no navegador.")
    mostrar_resumo("preparado; abrindo no navegador")
    return abrir_no_navegador(python)


if __name__ == "__main__":
    raise SystemExit(main())

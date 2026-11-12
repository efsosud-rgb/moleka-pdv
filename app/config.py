"""Configuração do aplicativo: nome, versão, pastas e porta.

Dados do usuário (banco, backups, logs, certificado) ficam FORA da pasta do programa:
- Windows: %APPDATA%\\MolekaPDV
- Linux/macOS (desenvolvimento): ~/.molekapdv
A variável de ambiente MOLEKA_PDV_DADOS sobrescreve a pasta (útil em testes).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NOME = "Moleka PDV"
VERSAO = "0.6.0"
PORTA_PADRAO = 8765


def raiz_projeto() -> Path:
    """Pasta do código (ou do executável, quando empacotado pelo PyInstaller)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def pasta_dados() -> Path:
    env = os.environ.get("MOLEKA_PDV_DADOS")
    if env:
        pasta = Path(env)
    elif os.name == "nt":
        pasta = Path(os.environ.get("APPDATA", Path.home())) / "MolekaPDV"
    else:
        pasta = Path.home() / ".molekapdv"
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "backups").mkdir(exist_ok=True)
    (pasta / "logs").mkdir(exist_ok=True)
    (pasta / "xml").mkdir(exist_ok=True)
    return pasta


def caminho_banco() -> Path:
    return pasta_dados() / "moleka.db"


def porta() -> int:
    return int(os.environ.get("MOLEKA_PDV_PORTA", PORTA_PADRAO))


def pasta_ui() -> Path:
    return raiz_projeto() / "ui"


def pasta_assets() -> Path:
    return raiz_projeto() / "assets"

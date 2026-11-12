# -*- mode: python ; coding: utf-8 -*-
# Empacota o Moleka PDV numa pasta (dist/MolekaPDV) com o executável MolekaPDV.exe.
# Uso, na raiz do repositório:  pyinstaller packaging/moleka.spec --noconfirm
# Pasta em vez de arquivo único: o PC do caixa tem HD, e o arquivo único se descompacta a cada
# abertura, o que deixaria a partida lenta.

import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

RAIZ = os.path.abspath(os.path.join(SPECPATH, ".."))

a = Analysis(
    [os.path.join(RAIZ, "main.py")],
    pathex=[RAIZ],
    datas=[
        (os.path.join(RAIZ, "ui"), "ui"),
        (os.path.join(RAIZ, "assets", "brand"), os.path.join("assets", "brand")),
        # Base de fusos horários: o Windows não tem a do sistema, e sem ela o programa não abre.
        *collect_data_files("tzdata"),
    ],
    hiddenimports=collect_submodules("uvicorn")
    + collect_submodules("app")
    + ["tzdata", "cryptography.x509", "cryptography.hazmat.primitives.serialization.pkcs12"],
    excludes=["tkinter", "pytest", "IPython", "mypy", "ruff"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MolekaPDV",
    console=False,  # sem janela preta de terminal; os erros vão para o log e para uma caixa de aviso
    icon=os.path.join(RAIZ, "assets", "brand", "moleka.ico"),
)
coll = COLLECT(exe, a.binaries, a.datas, name="MolekaPDV")

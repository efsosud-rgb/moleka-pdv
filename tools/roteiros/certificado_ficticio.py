"""Gera um certificado digital A1 FICTÍCIO (.pfx) para os roteiros de teste.

É autoassinado por uma "AC" inventada e não vale para nada fora dos testes (ver
tests/certificado_ficticio.py). O arquivo gerado não entra no repositório (.gitignore: *.pfx).

Uso: python tools/roteiros/certificado_ficticio.py <arquivo.pfx> <senha> [CNPJ] [dias de validade]
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "tests"))

from certificado_ficticio import CNPJ, gerar  # noqa: E402


def main() -> None:
    destino = Path(sys.argv[1])
    senha = sys.argv[2]
    cnpj = sys.argv[3] if len(sys.argv) > 3 else CNPJ
    dias = int(sys.argv[4]) if len(sys.argv) > 4 else 365
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(gerar(cnpj=cnpj, senha=senha, dias_de_validade=dias))
    print(destino)


if __name__ == "__main__":
    main()

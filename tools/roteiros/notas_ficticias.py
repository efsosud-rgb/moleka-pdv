"""Gera os arquivos XML de notas FICTÍCIAS usados pelo roteiro de navegador do estoque, da
entrada de nota e do financeiro. Nenhuma destas notas, empresas ou produtos existe.

Uso: python tools/roteiros/notas_ficticias.py <pasta de saída>
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

from nota_ficticia import item, nota_xml  # noqa: E402


def main() -> None:
    pasta = Path(sys.argv[1])
    pasta.mkdir(parents=True, exist_ok=True)
    # Nota 123: a mesma dos testes (contas feitas em tests/nota_ficticia.py). Total 580,60.
    (pasta / "nota-ficticia-123.xml").write_text(nota_xml(), encoding="utf-8")
    # Nota 140, sem parcelas. Total 62,40 + 36,00 + 111,00 + 58,80 = 268,20.
    itens = [
        item(
            "PIC-24",
            "PICOLE FICTICIO DE TESTE CX 24",
            "CX",
            1,
            "62.40",
            unidade_trib="UN",
            quantidade_trib=24,
        ),
        item(
            "AGUA-12",
            "AGUA FICTICIA DE TESTE 500 ML FARDO 12",
            "FD",
            2,
            "36.00",
            unidade_trib="UN",
            quantidade_trib=24,
        ),
        item("COB-CHOC", "COBERTURA FICTICIA DE TESTE CHOCOLATE", "UN", 6, "111.00"),
        item("LEITE-1L", "LEITE FICTICIO DE TESTE INTEGRAL 1 L", "UN", 12, "58.80"),
    ]
    (pasta / "nota-ficticia-140.xml").write_text(
        nota_xml(140, itens, parcelas=None), encoding="utf-8"
    )
    (pasta / "nao-e-nota.xml").write_text("<pedido><item>1</item></pedido>", encoding="utf-8")
    print(f"notas fictícias gravadas em {pasta}")


if __name__ == "__main__":
    main()

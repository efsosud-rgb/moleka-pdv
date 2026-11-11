"""Redesenha em vetor a logo oval da Moleka a partir do arquivo de 254x124 px.

A logo que o cliente enviou tem 447 px; ampliada, fica borrada. Este script gera uma versão
PROVISÓRIA em vetor, até chegar o arquivo vetorial oficial (SVG/PDF/CDR/AI):

1. amplia 8x e separa as cores chapadas (amarelo, amarelo da faixa, vermelho, vinho);
2. corta a silhueta no contorno vinho (o amarelo que sobra do lado de fora vira transparente);
3. traça as formas com o vtracer;
4. recoloca "SORVETES" como contorno da fonte Inter ExtraBold, letra por letra, nas colunas
   medidas no arquivo original (o texto original tem 8 px de altura e não dá para traçar).

Uso (na raiz do repositório):
    pip install vtracer fonttools brotli pillow
    python tools/design/vetoriza_logo.py assets/brand/logo_oval.png <inter-800.woff2> \
        assets/brand/logo_oval_vetor.svg
    node tools/design/svg2png.js assets/brand/logo_oval_vetor.svg \
        assets/brand/logo_oval_1016px.png 1016
"""

import re
import sys
import tempfile
from pathlib import Path

import vtracer
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFilter

ESCALA = 8
CHAVE = (255, 0, 255)  # cor que marca o lado de fora da logo durante o traçado
# Cores chapadas da logo (amostradas do arquivo) -> classe
PALETA = [
    ((252, 240, 12), "amarelo"),
    ((240, 228, 36), "faixa"),
    ((236, 64, 64), "vermelho"),
    ((216, 48, 48), "vermelho"),
    ((190, 44, 50), "vermelho"),
    ((84, 36, 36), "vinho"),
    ((0, 0, 37), "vinho"),
]
COR = {
    "amarelo": (252, 240, 12),
    "faixa": (240, 228, 36),
    "vermelho": (228, 48, 48),
    "vinho": (84, 36, 36),
}
# "SORVETES" no arquivo original: linhas do topo e da base e centro de cada letra (px)
TEXTO_TOPO, TEXTO_BASE = 93.5, 102.4
TEXTO_CENTROS = [93.0, 103.0, 113.5, 123.0, 132.5, 142.0, 151.5, 161.0]
TEXTO_CAIXA = (86, 91, 168, 105)  # área apagada antes do traçado (x0, y0, x1, y1)


def distancia(a: tuple[int, int, int], b: tuple[int, int, int]) -> int:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2


def rotular(origem: Path) -> Image.Image:
    """Devolve a logo ampliada com uma cor chapada por região e CHAVE do lado de fora."""
    src = Image.open(origem).convert("RGBA")
    largura, altura = src.width * ESCALA, src.height * ESCALA
    grande = src.resize((largura, altura), Image.LANCZOS)
    rgb = grande.convert("RGB").filter(ImageFilter.MedianFilter(9))
    alfa = (
        grande.split()[3].filter(ImageFilter.GaussianBlur(2)).point(lambda v: 255 if v > 127 else 0)
    )
    alfa = alfa.filter(ImageFilter.MinFilter(9))  # tira a franja alaranjada da borda

    px, al = rgb.load(), alfa.load()
    rotulos = Image.new("RGB", (largura, altura), CHAVE)
    saida = rotulos.load()
    for y in range(altura):
        for x in range(largura):
            if al[x, y]:
                classe = min(PALETA, key=lambda p: distancia(p[0], px[x, y]))[1]
                saida[x, y] = COR[classe]
    x0, y0, x1, y1 = (v * ESCALA for v in TEXTO_CAIXA)
    for y in range(y0, y1):
        for x in range(x0, x1):
            if al[x, y]:
                saida[x, y] = COR["amarelo"]
    rotulos = rotulos.filter(ImageFilter.ModeFilter(7))  # tira pontinhos soltos

    # A silhueta termina no contorno vinho: o amarelo de fora do contorno vira transparente.
    amarelos = (COR["amarelo"], COR["faixa"])
    passa = Image.new("L", (largura, altura), 0)
    pp, rr = passa.load(), rotulos.load()
    for y in range(altura):
        for x in range(largura):
            if rr[x, y] == CHAVE or rr[x, y] in amarelos:
                pp[x, y] = 255

    def amostras_amarelas() -> int:
        return sum(
            1 for y in range(0, altura, 4) for x in range(0, largura, 4) if rr[x, y] in amarelos
        )

    antes = amostras_amarelas()
    ImageDraw.floodfill(passa, (0, 0), 128)
    for y in range(altura):
        for x in range(largura):
            if pp[x, y] == 128:
                rr[x, y] = CHAVE
    depois = amostras_amarelas()
    if depois <= antes * 0.8:
        raise SystemExit(
            f"O contorno vinho tem falha: o amarelo de dentro vazou ({antes} -> {depois})."
        )
    return rotulos


def perto(hexa: str, cor: tuple[int, int, int], tolerancia: int = 40) -> bool:
    r, g, b = int(hexa[1:3], 16), int(hexa[3:5], 16), int(hexa[5:7], 16)
    return abs(r - cor[0]) + abs(g - cor[1]) + abs(b - cor[2]) <= tolerancia


def tracar(rotulos: Image.Image) -> list[tuple[str, str, str]]:
    """Traça a imagem rotulada e devolve (caminho, cor, transformação) de cada forma."""
    with tempfile.TemporaryDirectory() as pasta:
        entrada, saida = Path(pasta) / "rotulos.png", Path(pasta) / "rotulos.svg"
        rotulos.save(entrada)
        vtracer.convert_image_to_svg_py(
            str(entrada),
            str(saida),
            colormode="color",
            hierarchical="stacked",
            mode="spline",
            filter_speckle=40,
            color_precision=8,
            layer_difference=8,
            corner_threshold=60,
            length_threshold=8.0,
            max_iterations=10,
            splice_threshold=45,
            path_precision=1,
        )
        svg = saida.read_text(encoding="utf-8")
    return re.findall(r'<path d="([^"]*)" fill="(#[0-9A-Fa-f]{6})" transform="([^"]*)"/>', svg)


def contornos_do_texto(fonte: Path) -> list[str]:
    """Contornos de "SORVETES" na fonte dada, posicionados como no arquivo original."""
    tt = TTFont(fonte)
    glifos, mapa = tt.getGlyphSet(), tt.getBestCmap()
    escala = (TEXTO_BASE - TEXTO_TOPO) * ESCALA / tt["OS/2"].sCapHeight
    caminhos = []
    for letra, centro in zip("SORVETES", TEXTO_CENTROS, strict=True):
        nome = mapa[ord(letra)]
        limites = BoundsPen(glifos)
        glifos[nome].draw(limites)
        x0, _, x1, _ = limites.bounds
        caneta = SVGPathPen(glifos)
        glifos[nome].draw(caneta)
        dx = centro * ESCALA - (x0 + x1) / 2 * escala
        caminhos.append(
            f'<path d="{caneta.getCommands()}" transform="translate({dx:.1f},'
            f'{TEXTO_BASE * ESCALA:.1f}) scale({escala:.4f},{-escala:.4f})"/>'
        )
    return caminhos


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    origem, fonte, destino = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    rotulos = rotular(origem)
    largura, altura = rotulos.size
    formas = tracar(rotulos)

    fora = [f for f in formas if perto(f[1], CHAVE)]
    if len(fora) != 1:
        raise SystemExit(f"Esperava 1 forma de fundo, achei {len(fora)}.")
    corpo = []
    for caminho, cor, transformacao in formas:
        if perto(cor, CHAVE):
            continue
        if perto(cor, COR["vermelho"]):
            preenchimento = "url(#letras)"
        elif perto(cor, COR["vinho"]):
            preenchimento = "#542424"
        elif perto(cor, COR["faixa"], 30):
            preenchimento = "#F0E424"
        else:
            preenchimento = "#FCF00C"
        corpo.append(f'<path d="{caminho}" fill="{preenchimento}" transform="{transformacao}"/>')

    partes = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {largura} {altura}" '
        f'width="{largura}" height="{altura}">',
        "<title>Moleka Sorvetes</title>",
        f'<defs><mask id="oval"><rect width="{largura}" height="{altura}" fill="#fff"/>'
        f'<path d="{fora[0][0]}" fill="#000" transform="{fora[0][2]}"/></mask>',
        '<linearGradient id="letras" gradientUnits="userSpaceOnUse" x1="0" '
        f'y1="{26 * ESCALA}" x2="0" y2="{90 * ESCALA}">'
        '<stop offset="0" stop-color="#EE4242"/><stop offset=".55" stop-color="#DC3232"/>'
        '<stop offset="1" stop-color="#BE282C"/></linearGradient></defs>',
        '<g mask="url(#oval)">',
        *corpo,
        '<g fill="#14142E">',
        *contornos_do_texto(fonte),
        "</g></g></svg>",
    ]
    destino.write_text("\n".join(partes), encoding="utf-8")
    print(f"ok {destino} ({destino.stat().st_size} bytes; {len(corpo)} formas)")


if __name__ == "__main__":
    main()

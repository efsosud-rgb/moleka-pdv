"""Gera o ícone do programa (assets/brand/moleka.ico) a partir da arte 3D da capa.

O ícone é o rosto da mascote num círculo com aro amarelo e contorno vinho, para continuar
legível nos tamanhos pequenos da barra de tarefas.

Uso (na raiz do repositório):
    python tools/design/gera_icone.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

RAIZ = Path(__file__).resolve().parents[2]
ARTE = RAIZ / "assets" / "brand" / "capa_logo_3d.jpg"
SAIDA = RAIZ / "assets" / "brand" / "moleka.ico"
CENTRO, RAIO = (1190, 212), 196  # rosto da mascote na arte de 1672x941 px
LADO = 1024  # desenha grande e reduz, para as bordas ficarem lisas


def main() -> None:
    arte = Image.open(ARTE).convert("RGB")
    cx, cy = CENTRO
    rosto = arte.crop((cx - RAIO, cy - RAIO, cx + RAIO, cy + RAIO)).resize(
        (LADO, LADO), Image.LANCZOS
    )

    icone = Image.new("RGBA", (LADO, LADO), (0, 0, 0, 0))
    desenho = ImageDraw.Draw(icone)
    desenho.ellipse((0, 0, LADO - 1, LADO - 1), fill="#542424")  # contorno vinho
    aro = int(LADO * 0.035)
    desenho.ellipse((aro, aro, LADO - 1 - aro, LADO - 1 - aro), fill="#FCF00C")  # aro amarelo
    miolo = int(LADO * 0.11)
    mascara = Image.new("L", (LADO, LADO), 0)
    ImageDraw.Draw(mascara).ellipse((miolo, miolo, LADO - 1 - miolo, LADO - 1 - miolo), fill=255)
    icone.paste(rosto, (0, 0), mascara)

    tamanhos = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (24, 24), (16, 16)]
    icone.resize((256, 256), Image.LANCZOS).save(SAIDA, format="ICO", sizes=tamanhos)
    print(f"ok {SAIDA} ({SAIDA.stat().st_size} bytes)")


if __name__ == "__main__":
    main()

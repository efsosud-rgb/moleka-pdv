"""Converte os artboards .dc.html do canvas em páginas HTML estáticas e independentes.

Uso: python tools/design/exporta_prototipo.py <pasta_project_do_canvas> <pasta_destino> <prefixo>
Ex.:  python tools/design/exporta_prototipo.py canvas/project docs/prototipo ../../assets/brand/
"""

import re
import sys
from pathlib import Path

SRC = Path(sys.argv[1])
DST = Path(sys.argv[2])
PREFIXO = sys.argv[3]
DST.mkdir(parents=True, exist_ok=True)

PAGINAS = [
    ("Main.dc.html", "index.html", "1 · Abertura / Login"),
    ("Inicio.dc.html", "inicio.html", "2 · Início"),
    ("Caixa.dc.html", "caixa.html", "3 · Caixa (PDV)"),
    ("Financeiro.dc.html", "financeiro.html", "4 · Financeiro / DRE"),
    ("Produtos.dc.html", "produtos.html", "5 · Produtos"),
]
LINKS = {origem: destino for origem, destino, _ in PAGINAS}
PAGINAS = [p for p in PAGINAS if (SRC / p[0]).exists()]

BLOBS = {
    "/_blob/35f684cf9b6c7bf68d835c6066766300": PREFIXO + "logo_oval_1016px.png",
    "/_blob/d9c04d28c9de079e7e1cd5d106c26d24": PREFIXO + "capa_logo_3d.jpg",
    "/_blob/6c246524b2664fb7f75017e2e33a60ea": PREFIXO + "capa_loja.jpg",
    "/_blob/6c5c731a39b136f4a00a3d97a96ed88a": PREFIXO + "capa_animacao_tira.jpg",
    "/_blob/2ba4079417cb3362e0725cc3abe7b685": PREFIXO + "logo_oval.png",
    "/_blob/51ac92e99bb98cb19194672c302dd754": PREFIXO + "mascote.png",
}

# Marcadores do canvas -> valor fixo ou <span> preenchido pelo script abaixo.
HOLES = {
    "rootClass": "anim",
    "rx": "0",
    "ry": "0",
    "duracaoFilme": "9",
    "hoje": '<span data-auto="hoje"></span>',
    "mesAno": '<span data-auto="mesAno"></span>',
}

NAV_CSS = """
.proto-nav{position:fixed;right:0;top:50%;transform:translateY(-50%);z-index:99;display:flex;flex-direction:column;gap:4px;align-items:center;padding:6px 3px;border-radius:12px 0 0 12px;background:rgba(59,24,24,.92);box-shadow:0 6px 18px rgba(0,0,0,.35);font:800 11px/1 Inter,system-ui,sans-serif}
.proto-nav a{display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;border-radius:50%;background:#6E2E2E;color:#FCF00C;text-decoration:none}
.proto-nav a:hover,.proto-nav a.atual{background:#FCF00C;color:#542424}
"""

NAV_HTML = """
<nav class="proto-nav" aria-label="Telas do protótipo" title="Protótipo — clique para trocar de tela">{links}</nav>
"""

COMUM_JS = """
(function () {
  var d = new Date();
  var auto = {
    hoje: d.toLocaleDateString('pt-BR', { weekday: 'long', day: '2-digit', month: '2-digit', year: 'numeric' }),
    mesAno: d.toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' })
  };
  document.querySelectorAll('[data-auto]').forEach(function (el) { el.textContent = auto[el.getAttribute('data-auto')] || ''; });
})();
"""

WIRING = {
    "index.html": """
(function () {
  // A arte da vitrine se inclina de leve acompanhando o mouse.
  var vitrine = document.querySelector('.vitrine'), arte = document.querySelector('.arte');
  if (vitrine && arte) {
    vitrine.addEventListener('mousemove', function (e) {
      var r = vitrine.getBoundingClientRect();
      var x = (e.clientX - r.left) / r.width - 0.5, y = (e.clientY - r.top) / r.height - 0.5;
      arte.style.transform = 'rotateX(' + (-y * 4).toFixed(1) + 'deg) rotateY(' + (x * 5).toFixed(1) + 'deg)';
    });
    vitrine.addEventListener('mouseleave', function () { arte.style.transform = 'rotateX(0deg) rotateY(0deg)'; });
  }
  document.addEventListener('keydown', function (e) { if (e.key === 'Enter') location.href = 'inicio.html'; });
})();""",
    "inicio.html": """
document.addEventListener('keydown', function (e) {
  if (e.key === 'F2') { e.preventDefault(); location.href = 'caixa.html'; }
  if (e.key === 'F5') { e.preventDefault(); location.href = 'produtos.html'; }
});""",
    "caixa.html": """
document.addEventListener('keydown', function (e) { if (e.key === 'Escape') location.href = 'inicio.html'; });""",
    "financeiro.html": """
document.addEventListener('keydown', function (e) { if (e.key === 'Escape') location.href = 'inicio.html'; });""",
    "produtos.html": """
document.addEventListener('keydown', function (e) { if (e.key === 'Escape') location.href = 'inicio.html'; });""",
}


def converter(origem: Path, destino_nome: str) -> str:
    html = origem.read_text(encoding="utf-8")
    html = html.replace('<script src="./support.js"></script>\n', "")
    # Move o conteúdo do <helmet> para o <head>
    m = re.search(r"<helmet>(.*?)</helmet>\s*", html, flags=re.S)
    helmet = m.group(1).strip() if m else ""
    html = html[: m.start()] + html[m.end() :] if m else html
    helmet = helmet.replace("</style>", NAV_CSS + "</style>", 1)
    html = html.replace("</head>", helmet + "\n</head>", 1)
    html = html.replace("<x-dc>\n", "").replace("</x-dc>\n", "")
    # Eventos do canvas (onMouseMove="{{mover}}") saem; a página estática usa o script acima.
    html = re.sub(r'\s+on[A-Z][A-Za-z]*="\{\{\s*\w+\s*\}\}"', "", html)
    html = re.sub(r"\{\{\s*(\w+)\s*\}\}", lambda mo: HOLES[mo.group(1)], html)
    for blob, caminho in BLOBS.items():
        html = html.replace(blob, caminho)
    for origem_nome, destino in LINKS.items():
        html = html.replace(f'href="{origem_nome}"', f'href="{destino}"')
    html = re.sub(r'<script type="text/x-dc".*?</script>\s*', "", html, flags=re.S)
    links = "".join(
        f'<a href="{arq}" class="{"atual" if arq == destino_nome else ""}" title="{titulo}">{i + 1}</a>'
        for i, (_, arq, titulo) in enumerate(PAGINAS)
    )
    script = "<script>" + COMUM_JS + WIRING[destino_nome] + "\n</script>"
    html = html.replace("</body>", NAV_HTML.format(links=links) + script + "\n</body>", 1)
    assert "{{" not in html, f"sobrou marcador em {destino_nome}"
    assert "/_blob/" not in html, f"sobrou blob em {destino_nome}"
    assert ".dc.html" not in html, f"sobrou link de canvas em {destino_nome}"
    return html


for origem, destino_nome, _ in PAGINAS:
    saida = DST / destino_nome
    saida.write_text(converter(SRC / origem, destino_nome), encoding="utf-8")
    print(f"ok {saida} ({saida.stat().st_size} bytes)")

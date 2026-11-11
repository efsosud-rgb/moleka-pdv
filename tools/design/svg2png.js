// Gera PNG com fundo transparente a partir de um SVG. Uso: node svg2png.js <entrada.svg> <saida.png> <largura_px>
const { chromium } = require('playwright');
const fs = require('fs');
(async () => {
  const [,, svg, out, w] = process.argv;
  const data = fs.readFileSync(svg, 'utf8');
  const m = data.match(/viewBox="0 0 (\d+) (\d+)"/);
  const h = Math.round(Number(w) * Number(m[2]) / Number(m[1]));
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: Number(w), height: h }, deviceScaleFactor: 1 });
  await p.setContent(`<body style="margin:0;background:transparent">${data.replace('<svg', '<svg style="width:' + w + 'px;height:' + h + 'px;display:block"')}</body>`);
  await p.screenshot({ path: out, omitBackground: true });
  console.log('ok', out, w + 'x' + h);
  await b.close();
})();
